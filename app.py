"""Spearmint: independent, self-hosted spending tracker inspired by Mint."""
import auth
from contextvars import ContextVar
import calendar
import csv
import hashlib
import hmac
import io
import json
import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
DATA = Path(os.environ.get('DATA_DIR', ROOT / 'data'))
CURRENCY = os.environ.get('CURRENCY', 'CAD').upper()
PASSWORD = os.environ.get('APP_PASSWORD', '')
SESSIONS = {}
ATTEMPTS = {}
LOCK = threading.Lock()
CURRENT_USER = ContextVar('current_user', default=1)
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')

class Invalid(ValueError):
    pass

@contextmanager
def db():
    user_id = CURRENT_USER.get()
    folder = DATA if user_id == 1 else DATA / 'users' / str(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(folder / 'monthly-spend.sqlite3', timeout=15)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    try:
        with con:
            yield con
    finally:
        con.close()

def init():
    DATA.mkdir(parents=True, exist_ok=True)
    with db() as c:
        fresh_categories = not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='categories'").fetchone()
        c.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, opening INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS transactions(
          id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id),
          date TEXT NOT NULL, payee TEXT NOT NULL, amount INTEGER NOT NULL,
          kind TEXT NOT NULL CHECK(kind IN ('expense','income','refund','transfer')),
          category_id INTEGER REFERENCES categories(id), note TEXT NOT NULL DEFAULT '',
          imported_id TEXT, transfer_id TEXT, batch_id TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS import_id ON transactions(account_id,imported_id) WHERE imported_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS tx_date ON transactions(date);
        CREATE TABLE IF NOT EXISTS previews(id TEXT PRIMARY KEY, created REAL NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS profiles(name TEXT PRIMARY KEY, mapping TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS rules(id INTEGER PRIMARY KEY, contains_text TEXT NOT NULL UNIQUE, category_id INTEGER NOT NULL REFERENCES categories(id));
        ''')
        if fresh_categories:
            c.executemany('INSERT INTO categories(name) VALUES (?)', [(v,) for v in ['Housing','Groceries','Dining out','Transportation','Utilities','Shopping','Health','Entertainment','Subscriptions','Travel','Other']])

def money(value, decimal_comma=False):
    raw = str(value).strip().replace('$','').replace(' ','').replace('\u00a0','')
    if raw.startswith('(') and raw.endswith(')'):
        raw = '-' + raw[1:-1]
    if decimal_comma:
        raw = raw.replace('.','').replace(',','.')
    else:
        raw = raw.replace(',','')
    try:
        n = Decimal(raw)
        if not n.is_finite() or abs(n) > 100000000 or n * 100 != (n * 100).to_integral_value():
            raise Invalid('Use an amount with at most two decimal places, under 100 million.')
        return int(n * 100)
    except InvalidOperation:
        raise Invalid('Invalid amount: ' + str(value)[:60])

def clean(value, limit=200):
    value = str(value or '').strip()
    if len(value) > limit:
        raise Invalid('Text is too long.')
    return value

def valid_date(value):
    try:
        result = date.fromisoformat(str(value))
        if result.isoformat() != value:
            raise ValueError()
        return value
    except (ValueError, TypeError):
        raise Invalid('Use a valid YYYY-MM-DD date.')

def existing(c, table, key):
    if table not in ('accounts','categories'):
        raise Invalid('Invalid lookup.')
    if not c.execute(f'SELECT 1 FROM {table} WHERE id=?', (key,)).fetchone():
        raise Invalid('Choose an existing ' + table[:-1] + '.')

def merchant_key(payee):
    return ' '.join(payee.casefold().split())

def category_context(c):
    rules=[dict(r) for r in c.execute('SELECT r.* FROM rules r JOIN categories c ON c.id=r.category_id ORDER BY r.id')]
    history={}
    for row in c.execute("SELECT DISTINCT t.payee,t.category_id FROM transactions t JOIN categories c ON c.id=t.category_id WHERE t.kind='expense'"):
        key=merchant_key(row['payee'])
        if key: history.setdefault(key,set()).add(row['category_id'])
    return rules,{key:next(iter(ids)) if len(ids)==1 else None for key,ids in history.items()}

def category(c, payee, context=None):
    rules,history=context if context is not None else category_context(c)
    for rule in rules:
        if rule['contains_text'].casefold() in payee.casefold():
            return rule['category_id']
    return history.get(merchant_key(payee))

def transaction(c, data):
    account = int(data.get('account_id') or 0)
    existing(c, 'accounts', account)
    day = valid_date(data.get('date'))
    payee = clean(data.get('payee'))
    if not payee:
        raise Invalid('Enter a payee or description.')
    kind = data.get('kind')
    if kind not in ('expense','income','refund','transfer'):
        raise Invalid('Choose a transaction type.')
    amount = abs(money(data.get('amount', '')))
    if not amount:
        raise Invalid('Amount must be greater than zero.')
    if kind in ('expense','transfer'):
        amount = -amount
    cat = int(data['category_id']) if data.get('category_id') else category(c, payee)
    if cat:
        existing(c, 'categories', cat)
    if kind in ('income','transfer'):
        cat = None
    return dict(account_id=account, date=day, payee=payee, amount=amount, kind=kind, category_id=cat, note=clean(data.get('note'),1000))

def insert(c, tx, **extras):
    record = {**tx, **extras}
    cols = ','.join(record)
    return c.execute(f'INSERT INTO transactions({cols}) VALUES ({",".join("?" for _ in record)})', tuple(record.values())).lastrowid

def shift_month(day, offset):
    i = day.year * 12 + day.month - 1 + offset
    return date(i // 12, i % 12 + 1, 1)

def summary(c, month):
    try:
        start = date.fromisoformat(month + '-01')
    except ValueError:
        raise Invalid('Invalid month.')
    end = shift_month(start,1)
    today = date.today()
    partial = start.year == today.year and start.month == today.month
    cutoff = today.day if partial else 31
    rows = [dict(r) for r in c.execute('SELECT * FROM transactions WHERE date>=? AND date<?', (start.isoformat(),end.isoformat()))]
    current_rows = [r for r in rows if not partial or int(r['date'][-2:]) <= cutoff]
    def totals(items):
        income = sum(r['amount'] for r in items if r['kind']=='income')
        expenses = -sum(r['amount'] for r in items if r['kind'] in ('expense','refund'))
        return income, expenses
    income, expenses = totals(current_rows)
    earliest = c.execute('SELECT MIN(date) FROM transactions WHERE kind != "transfer"').fetchone()[0]
    periods = []
    historical = []
    for offset in (-3,-2,-1):
        prev = shift_month(start,offset)
        if earliest and prev.strftime('%Y-%m') >= earliest[:7]:
            last = date(prev.year,prev.month,min(cutoff,calendar.monthrange(prev.year,prev.month)[1]))
            periods.append(prev.strftime('%Y-%m'))
            historical.extend(dict(r) for r in c.execute('SELECT * FROM transactions WHERE date>=? AND date<=?',(prev.isoformat(),last.isoformat())))
    cats = {r['id']:r['name'] for r in c.execute('SELECT * FROM categories')}
    cats[None] = 'Uncategorized'
    comparisons = []
    for key,name in cats.items():
        spend = -sum(r['amount'] for r in current_rows if r['category_id']==key and r['kind'] in ('expense','refund'))
        previous = -sum(r['amount'] for r in historical if r['category_id']==key and r['kind'] in ('expense','refund'))
        avg = round(previous/len(periods)) if periods else None
        if spend or previous:
            comparisons.append(dict(id=key,name=name,spent=spend,average=avg,difference=spend-avg if avg is not None else None))
    comparisons.sort(key=lambda r:r['spent'],reverse=True)
    trend=[]
    for offset in range(-5,1):
        p=shift_month(start,offset)
        q=shift_month(p,1)
        items=[dict(r) for r in c.execute('SELECT * FROM transactions WHERE date>=? AND date<? AND date<=?',(p.isoformat(),q.isoformat(),today.isoformat() if offset==0 and partial else '9999-12-31'))]
        inc,exp=totals(items)
        trend.append(dict(month=p.strftime('%Y-%m'),income=inc,expenses=exp,has_data=bool(items)))
    return dict(income=income,expenses=expenses,remaining=income-expenses,categories=comparisons,trend=trend,periods=periods,partial=partial,day=cutoff,scheduled=sum(r['amount'] for r in rows if partial and int(r['date'][-2:])>cutoff),count=len(current_rows))

def duplicate(c, tx):
    if tx.get('imported_id') and c.execute('SELECT 1 FROM transactions WHERE account_id=? AND imported_id=?',(tx['account_id'],tx['imported_id'])).fetchone():
        return 'duplicate'
    for r in c.execute('SELECT payee FROM transactions WHERE account_id=? AND date=? AND amount=?',(tx['account_id'],tx['date'],tx['amount'])):
        if ' '.join(r['payee'].casefold().split()) == ' '.join(tx['payee'].casefold().split()):
            return 'possible'
    return 'new'

def parse_csv(text, delimiter=','):
    if delimiter not in (',',';','\t'):
        raise Invalid('Unsupported delimiter.')
    try:
        rows=list(csv.reader(io.StringIO(text.lstrip('\ufeff')),delimiter=delimiter,strict=True))
    except csv.Error as e:
        raise Invalid('CSV could not be read: '+str(e))
    rows=[r for r in rows if any(x.strip() for x in r)]
    if not rows or not rows[0] or len(rows)>5001:
        raise Invalid('Use a CSV with a header and at most 5,000 transactions.')
    if len(rows[0])>100:
        raise Invalid('CSV has too many columns.')
    return rows

def preview(c, data):
    account=int(data.get('account_id') or 0)
    existing(c,'accounts',account)
    mapping=data.get('mapping',{})
    rows=parse_csv(data.get('text',''),mapping.get('delimiter',','))
    result=[]
    suggestions=category_context(c)
    seen=set()
    seen_ids=set()
    def cell(row,key,required=False):
        idx=mapping.get(key)
        if idx is None or idx=='':
            if required: raise Invalid('Map the '+key+' column.')
            return ''
        idx=int(idx)
        if idx<0 or idx>=len(row): raise Invalid('Column missing in this row.')
        return row[idx].strip()
    formats={'iso':'%Y-%m-%d','dmy':'%d/%m/%Y','mdy':'%m/%d/%Y'}
    if mapping.get('date_format','iso') not in formats:
        raise Invalid('Invalid date format.')
    for i,row in enumerate(rows[1:]):
        item={'index':i,'line':i+2}
        try:
            if len(row)!=len(rows[0]): raise Invalid('Column count differs from header.')
            day=datetime.strptime(cell(row,'date',True),formats[mapping.get('date_format','iso')]).date().isoformat()
            payee=clean(cell(row,'payee',True))
            if not payee: raise Invalid('Description is empty.')
            comma=bool(mapping.get('decimal_comma'))
            if mapping.get('mode','signed')=='split':
                debit=abs(money(cell(row,'debit') or '0',comma))
                credit=abs(money(cell(row,'credit') or '0',comma))
                if debit and credit: raise Invalid('Both debit and credit contain amounts.')
                amount=credit-debit
            else:
                amount=money(cell(row,'amount',True),comma)
                if mapping.get('invert'): amount=-amount
            if not amount: raise Invalid('Zero amount.')
            ref=clean(cell(row,'imported_id')) or None
            tx=dict(account_id=account,date=day,payee=payee,amount=amount,kind='expense' if amount<0 else 'income',category_id=category(c,payee,suggestions) if amount<0 else None,note='',imported_id=ref)
            status=duplicate(c,tx)
            key=(day,' '.join(payee.casefold().split()),amount)
            if ref and ref in seen_ids: status='duplicate'
            elif key in seen and status=='new': status='possible'
            seen.add(key)
            if ref: seen_ids.add(ref)
            item.update(tx=tx,status=status)
        except (ValueError,TypeError) as e:
            item.update(status='invalid',error=str(e))
        result.append(item)
    token=secrets.token_urlsafe(24)
    c.execute('DELETE FROM previews WHERE created<?',(time.time()-3600,))
    c.execute('INSERT INTO previews VALUES (?,?,?)',(token,time.time(),json.dumps(result)))
    return dict(token=token,rows=result)

def commit_import(c,data):
    c.execute('BEGIN IMMEDIATE')
    rec=c.execute('SELECT * FROM previews WHERE id=?',(data.get('token'),)).fetchone()
    if not rec or rec['created']<time.time()-3600: raise Invalid('Preview expired. Preview this file again.')
    rows=json.loads(rec['payload'])
    selected=data.get('selected',[])
    if not selected: raise Invalid('Select at least one row.')
    if len(selected)!=len({int(s['index']) for s in selected}): raise Invalid('Repeated selection.')
    batch=secrets.token_urlsafe(18)
    count=0
    for pick in selected:
        index=int(pick['index'])
        if index<0 or index>=len(rows): raise Invalid('Invalid row selection.')
        row=rows[index]
        if row['status'] in ('invalid','duplicate'): raise Invalid('A selected row cannot be imported.')
        tx=row['tx']
        status=duplicate(c,tx)
        if status=='duplicate': raise Invalid('A transaction ID now exists. Preview again.')
        if (row['status']=='possible' or status=='possible') and not pick.get('allow_possible'):
            raise Invalid('A possible duplicate needs explicit approval. Preview again.')
        kind=pick.get('kind',tx['kind'])
        if kind not in ('expense','income','refund','transfer'): raise Invalid('Invalid type.')
        if (kind=='expense' and tx['amount']>=0) or (kind in ('income','refund') and tx['amount']<=0): raise Invalid('Type conflicts with the amount sign.')
        tx['kind']=kind
        cat=int(pick['category_id']) if pick.get('category_id') else None
        if cat: existing(c,'categories',cat)
        tx['category_id']=cat if kind in ('expense','refund') else None
        insert(c,tx,batch_id=batch)
        count+=1
    c.execute('DELETE FROM previews WHERE id=?',(data['token'],))
    return dict(imported=count,batch_id=batch)

def categorize_transactions(c, data):
    ids = data.get('ids')
    if not isinstance(ids, list) or not ids or len(ids) > 5000:
        raise Invalid('Select between 1 and 5,000 transactions.')
    if any(type(key) is not int or key <= 0 for key in ids) or len(set(ids)) != len(ids):
        raise Invalid('Invalid transaction selection.')
    if 'category_id' not in data:
        raise Invalid('Choose a category.')
    cat = data['category_id']
    if cat is not None and (type(cat) is not int or cat <= 0):
        raise Invalid('Invalid category.')
    c.execute('BEGIN IMMEDIATE')
    if cat is not None:
        existing(c, 'categories', cat)
    for key in ids:
        row = c.execute('SELECT kind FROM transactions WHERE id=?', (key,)).fetchone()
        if not row:
            raise Invalid('A selected transaction no longer exists. Refresh and select again.')
        if row['kind'] not in ('expense', 'refund'):
            raise Invalid('Only expenses and refunds can have spending categories. Refresh and select again.')
    c.executemany('UPDATE transactions SET category_id=? WHERE id=?', [(cat, key) for key in ids])
    return {'updated': len(ids)}

class Handler(BaseHTTPRequestHandler):
    server_version='Spearmint'
    def setup(self):
        super().setup()
        self.connection.settimeout(30)
    def log_message(self,fmt,*args):
        # Do not log request bodies, credentials or financial records.
        pass
    def send(self,status,body,ctype='application/json',cookie=None):
        if ctype=='application/json': body=json.dumps(body).encode()
        elif isinstance(body,str): body=body.encode()
        self.send_response(status)
        self.send_header('Content-Type',ctype)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie: self.send_header('Set-Cookie',cookie)
        self.end_headers()
        self.wfile.write(body)
    def authenticated(self):
        cookie=SimpleCookie()
        try: cookie.load(self.headers.get('Cookie',''))
        except Exception: return False
        token=cookie.get('session')
        with LOCK:
            session = SESSIONS.get(token.value) if token else None
        if not session or session['expires'] <= time.time(): return False
        user = auth.get(DATA, session['user_id'])
        if not user or not user['enabled'] or user['version'] != session['version']: return False
        self.user = user
        return True
    def do_GET(self): self.handle_request('GET')
    def do_POST(self): self.handle_request('POST')
    def do_PUT(self): self.handle_request('PUT')
    def do_DELETE(self): self.handle_request('DELETE')
    def handle_request(self,method):
        token=CURRENT_USER.set(1)
        try: self.dispatch(method)
        finally: CURRENT_USER.reset(token)
    def dispatch(self,method):
        from urllib.parse import urlsplit,parse_qs
        url=urlsplit(self.path)
        path=url.path
        try:
            if method=='GET' and path in ('/','/app.js','/style.css','/spearmint-logo.png'):
                filename={'/':'index.html','/app.js':'app.js','/style.css':'style.css','/spearmint-logo.png':'spearmint-logo.png'}[path]
                ctype={'/':'text/html; charset=utf-8','/app.js':'application/javascript','/style.css':'text/css','/spearmint-logo.png':'image/png'}[path]
                return self.send(200,(ROOT/'static'/filename).read_bytes(),ctype)
            if method=='GET' and path=='/health': return self.send(200,{'ok':True})
            data={}
            if method!='GET':
                if self.headers.get('X-Requested-With')!='MonthlySpend':
                    return self.send(403,{'error':'Request rejected.'})
                length=int(self.headers.get('Content-Length','0'))
                if length<0 or length>4_000_000: return self.send(413,{'error':'Request exceeds 4 MB.'})
                data=json.loads(self.rfile.read(length) or b'{}')
                if not isinstance(data,dict): raise Invalid('Expected an object.')
            if path=='/api/login' and method=='POST':
                now=time.time()
                ip=self.client_address[0]
                with LOCK:
                    ATTEMPTS[ip]=[t for t in ATTEMPTS.get(ip,[]) if t>now-300]
                    if len(ATTEMPTS[ip])>=10: return self.send(429,{'error':'Too many attempts. Try again in five minutes.'})
                    ATTEMPTS[ip].append(now)
                user=auth.authenticate(DATA,data.get('username'),data.get('password'))
                if not user:
                    return self.send(401,{'error':'Incorrect username or password.'})
                CURRENT_USER.set(user['id'])
                init()
                token=secrets.token_urlsafe(32)
                with LOCK:
                    for old in list(SESSIONS):
                        if SESSIONS[old]['expires']<now: del SESSIONS[old]
                    SESSIONS[token]={'user_id':user['id'],'version':user['version'],'expires':now+43200}
                    ATTEMPTS.pop(ip,None)
                secure='; Secure' if os.environ.get('COOKIE_SECURE')=='true' else ''
                return self.send(200,{'ok':True},cookie=f'session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200{secure}')
            if not self.authenticated(): return self.send(401,{'error':'Please sign in.'})
            CURRENT_USER.set(self.user['id'])
            if path=='/api/password' and method=='POST':
                auth.change_password(DATA,self.user['id'],data.get('current_password'),data.get('new_password'))
                return self.send(200,{'ok':True},cookie='session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            if path=='/api/users' or path.startswith('/api/users/'):
                if not self.user['is_admin']: return self.send(403,{'error':'Administrator access required.'})
                if path=='/api/users' and method=='GET': return self.send(200,{'users':auth.list_users(DATA)})
                if path=='/api/users' and method=='POST':
                    created=auth.create(DATA,data.get('username'),data.get('password'))
                    return self.send(200,{'user':created})
                if path.startswith('/api/users/') and method=='POST':
                    auth.manage(DATA,int(path.rsplit('/',1)[1]),data.get('action'),data.get('password'))
                    return self.send(200,{'ok':True})
                return self.send(404,{'error':'Not found.'})
            if path=='/api/logout' and method=='POST':
                ck=SimpleCookie(self.headers.get('Cookie',''))
                with LOCK: SESSIONS.pop(ck['session'].value,None)
                return self.send(200,{'ok':True},cookie='session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            with db() as c:
                if path=='/api/state' and method=='GET':
                    accounts=[dict(r) for r in c.execute('SELECT a.*, a.opening+COALESCE(SUM(t.amount),0) balance FROM accounts a LEFT JOIN transactions t ON t.account_id=a.id GROUP BY a.id ORDER BY a.name')]
                    return self.send(200,dict(user=self.user,currency=CURRENCY,accounts=accounts,categories=[dict(r) for r in c.execute('SELECT * FROM categories ORDER BY name')],profiles=[dict(name=r['name'],mapping=json.loads(r['mapping'])) for r in c.execute('SELECT * FROM profiles ORDER BY name')],rules=[dict(r) for r in c.execute('SELECT r.*, c.name category FROM rules r JOIN categories c ON c.id=r.category_id ORDER BY r.id')]))
                if path=='/api/month' and method=='GET':
                    month=parse_qs(url.query).get('month',[date.today().strftime('%Y-%m')])[0]
                    report=summary(c,month)
                    report['transactions']=[dict(r) for r in c.execute('SELECT t.*,a.name account,COALESCE(c.name,"Uncategorized") category FROM transactions t JOIN accounts a ON a.id=t.account_id LEFT JOIN categories c ON c.id=t.category_id WHERE substr(t.date,1,7)=? ORDER BY t.date DESC,t.id DESC',(month,))]
                    return self.send(200,report)
                if path=='/api/transactions' and method=='GET':
                    rows=[dict(r) for r in c.execute('SELECT t.*,a.name account,COALESCE(c.name,"Uncategorized") category FROM transactions t JOIN accounts a ON a.id=t.account_id LEFT JOIN categories c ON c.id=t.category_id ORDER BY t.date DESC,t.id DESC')]
                    return self.send(200,{'transactions':rows})
                if path=='/api/transactions/category' and method=='POST':
                    result=categorize_transactions(c,data)
                    c.commit()
                    return self.send(200,result)
                if path=='/api/accounts' and method=='POST':
                    name=clean(data.get('name'),80)
                    if not name: raise Invalid('Enter an account name.')
                    c.execute('INSERT INTO accounts(name,opening) VALUES (?,?)',(name,money(data.get('opening','0'))))
                elif path.startswith('/api/accounts/') and method=='PUT':
                    key=int(path.rsplit('/',1)[1])
                    existing(c,'accounts',key)
                    opening=money(data.get('opening',''))
                    c.execute('UPDATE accounts SET opening=? WHERE id=?',(opening,key))
                elif path=='/api/categories' and method=='POST':
                    name=clean(data.get('name'),80)
                    if not name: raise Invalid('Enter a category name.')
                    c.execute('INSERT INTO categories(name) VALUES (?)',(name,))
                elif path.startswith('/api/categories/') and method in ('PUT','DELETE'):
                    key=int(path.rsplit('/',1)[1])
                    existing(c,'categories',key)
                    if method=='PUT':
                        name=clean(data.get('name'),80)
                        if not name: raise Invalid('Enter a category name.')
                        c.execute('UPDATE categories SET name=? WHERE id=?',(name,key))
                    else:
                        c.execute('BEGIN IMMEDIATE')
                        tx_count=c.execute('SELECT COUNT(*) FROM transactions WHERE category_id=?',(key,)).fetchone()[0]
                        rule_count=c.execute('SELECT COUNT(*) FROM rules WHERE category_id=?',(key,)).fetchone()[0]
                        if (tx_count or rule_count) and 'replacement_id' not in data:
                            raise Invalid('Choose where to move the transactions and merchant rules.')
                        replacement=int(data['replacement_id']) if data.get('replacement_id') else None
                        if replacement==key: raise Invalid('Choose a different replacement category.')
                        if replacement: existing(c,'categories',replacement)
                        if rule_count and replacement is None:
                            raise Invalid('This category has merchant rules. Choose a replacement category or remove those rules first.')
                        c.execute('UPDATE transactions SET category_id=? WHERE category_id=?',(replacement,key))
                        if replacement: c.execute('UPDATE rules SET category_id=? WHERE category_id=?',(replacement,key))
                        c.execute('DELETE FROM categories WHERE id=?',(key,))
                elif path=='/api/rules' and method=='POST':
                    value=clean(data.get('contains_text'),100).casefold()
                    if not value: raise Invalid('Enter merchant text.')
                    cat=int(data.get('category_id') or 0)
                    existing(c,'categories',cat)
                    c.execute('INSERT INTO rules(contains_text,category_id) VALUES (?,?)',(value,cat))
                elif path.startswith('/api/rules/') and method=='DELETE':
                    c.execute('DELETE FROM rules WHERE id=?',(int(path.rsplit('/',1)[1]),))
                elif path=='/api/transactions' and method in ('POST','PUT'):
                    tx=transaction(c,data)
                    if method=='PUT':
                        old=c.execute('SELECT * FROM transactions WHERE id=?',(int(data.get('id') or 0),)).fetchone()
                        if not old: raise Invalid('Transaction not found.')
                        if old['transfer_id']: raise Invalid('Delete and recreate a linked transfer to change it.')
                        if tx['kind']=='transfer':
                            # Imported transfer rows can retain their signed amount; no synthetic counterpart.
                            tx['amount']=money(data.get('amount'))
                        c.execute('UPDATE transactions SET '+','.join(k+'=?' for k in tx)+' WHERE id=?',(*tx.values(),old['id']))
                    else:
                        if tx['kind']=='transfer':
                            dest=int(data.get('destination_id') or 0)
                            existing(c,'accounts',dest)
                            if dest==tx['account_id']: raise Invalid('Choose a different destination account.')
                            group=secrets.token_urlsafe(16)
                            insert(c,tx,transfer_id=group)
                            insert(c,{**tx,'account_id':dest,'amount':-tx['amount']},transfer_id=group)
                        else: insert(c,tx)
                elif path.startswith('/api/transactions/') and method=='DELETE':
                    key=int(path.rsplit('/',1)[1])
                    row=c.execute('SELECT * FROM transactions WHERE id=?',(key,)).fetchone()
                    if not row: raise Invalid('Transaction not found.')
                    if row['transfer_id']: c.execute('DELETE FROM transactions WHERE transfer_id=?',(row['transfer_id'],))
                    else: c.execute('DELETE FROM transactions WHERE id=?',(key,))
                elif path=='/api/csv/headers' and method=='POST':
                    return self.send(200,{'headers':parse_csv(data.get('text',''),data.get('delimiter',','))[0]})
                elif path=='/api/csv/preview' and method=='POST':
                    result=preview(c,data)
                    c.commit()
                    return self.send(200,result)
                elif path=='/api/csv/commit' and method=='POST':
                    result=commit_import(c,data)
                    c.commit()
                    return self.send(200,result)
                elif path.startswith('/api/imports/') and method=='DELETE':
                    c.execute('DELETE FROM transactions WHERE batch_id=?',(path.rsplit('/',1)[1],))
                elif path=='/api/profiles' and method=='POST':
                    name=clean(data.get('name'),80)
                    if not name: raise Invalid('Enter a profile name.')
                    c.execute('INSERT INTO profiles VALUES (?,?) ON CONFLICT(name) DO UPDATE SET mapping=excluded.mapping',(name,json.dumps(data.get('mapping',{}))))
                elif path=='/api/export' and method=='GET':
                    out=io.StringIO()
                    w=csv.writer(out)
                    w.writerow(['Date','Account','Payee','Amount','Type','Category','Note','Imported ID'])
                    for r in c.execute('SELECT t.*,a.name account,COALESCE(c.name,"") category FROM transactions t JOIN accounts a ON a.id=t.account_id LEFT JOIN categories c ON c.id=t.category_id ORDER BY date,id'):
                        def safe(v):
                            s=str(v or '')
                            return "'"+s if s.startswith(('=','+','-','@','\t','\r')) else s
                        w.writerow([r['date'],safe(r['account']),safe(r['payee']),f"{r['amount']/100:.2f}",r['kind'],safe(r['category']),safe(r['note']),safe(r['imported_id'])])
                    return self.send(200,out.getvalue(),'text/csv; charset=utf-8')
                else: return self.send(404,{'error':'Not found.'})
            return self.send(200,{'ok':True})
        except sqlite3.IntegrityError:
            self.send(400,{'error':'That name or transaction reference already exists.'})
        except (Invalid,ValueError,TypeError,KeyError,OverflowError) as e:
            self.send(400,{'error':str(e)[:200]})
        except Exception:
            self.send(500,{'error':'The request failed. Please retry.'})

if __name__=='__main__':
    if len(PASSWORD)<12:
        raise SystemExit('Set APP_PASSWORD to at least 12 characters before starting.')
    init()
    auth.init(DATA,PASSWORD,ADMIN_USERNAME)
    server=ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','8080'))),Handler)
    server.timeout=30
    print('Spearmint listening on port '+str(server.server_port),flush=True)
    server.serve_forever()
