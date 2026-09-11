"""Persistent local accounts for Spearmint; server administrators remain trusted."""
import hashlib
import hmac
import json
import time
import unicodedata
import re
import secrets
import shutil
import sqlite3
from contextlib import contextmanager

@contextmanager
def connection(data_dir):
    c=sqlite3.connect(data_dir/'users.sqlite3',timeout=15)
    c.row_factory=sqlite3.Row
    try:
        with c: yield c
    finally: c.close()

def username(value):
    value=str(value or '').strip().lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,39}',value):
        raise ValueError('Username must be 3–40 characters: letters, numbers, dots, underscores or hyphens.')
    return value

def password_hash(password,salt=None):
    if not isinstance(password,str) or not 12<=len(password)<=1024:
        raise ValueError('Password must be between 12 and 1,024 characters.')
    salt=salt or secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex()
    return salt+':'+digest

def verify(password,encoded):
    try:
        salt,_=encoded.split(':',1)
        return hmac.compare_digest(password_hash(password,salt),encoded)
    except (ValueError,TypeError): return False

def public(row):
    return {k:row[k] for k in ('id','username','is_admin','enabled','version','setup_required')}

def init(data_dir,password,admin_username='admin'):
    data_dir.mkdir(parents=True,exist_ok=True)
    with connection(data_dir) as c:
        c.execute('CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,is_admin INTEGER NOT NULL DEFAULT 0,enabled INTEGER NOT NULL DEFAULT 1,version INTEGER NOT NULL DEFAULT 1)')
        columns={r['name'] for r in c.execute('PRAGMA table_info(users)')}
        if 'setup_required' not in columns: c.execute('ALTER TABLE users ADD COLUMN setup_required INTEGER NOT NULL DEFAULT 1')
        if 'recovery_answers' not in columns: c.execute('ALTER TABLE users ADD COLUMN recovery_answers TEXT')
        c.execute('CREATE TABLE IF NOT EXISTS recovery_tokens(token TEXT PRIMARY KEY,user_id INTEGER,version INTEGER,questions TEXT,expires REAL,verified INTEGER NOT NULL DEFAULT 0,name_key TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS recovery_attempts(scope TEXT,created REAL)')
        c.execute('CREATE INDEX IF NOT EXISTS recovery_attempt_scope ON recovery_attempts(scope,created)')
        if not c.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            c.execute('INSERT INTO users(id,username,password_hash,is_admin) VALUES (1,?,?,1)',(username(admin_username),password_hash(password)))

def authenticate(data_dir,name,password):
    with connection(data_dir) as c:
        row=c.execute('SELECT * FROM users WHERE username=?',(str(name or '').strip().lower(),)).fetchone()
    encoded=row['password_hash'] if row else '0'*32+':'+'0'*64
    valid=verify(password,encoded)
    return public(row) if row and row['enabled'] and valid else None

def get(data_dir,key):
    with connection(data_dir) as c: row=c.execute('SELECT * FROM users WHERE id=?',(key,)).fetchone()
    return public(row) if row else None

def list_users(data_dir):
    with connection(data_dir) as c: return [public(r) for r in c.execute('SELECT * FROM users ORDER BY id')]

def create(data_dir,name,password):
    name=username(name)
    encoded=password_hash(password)
    with connection(data_dir) as c:
        key=c.execute('INSERT INTO users(username,password_hash) VALUES (?,?)',(name,encoded)).lastrowid
    return get(data_dir,key)

def change_password(data_dir,key,current,new):
    encoded=password_hash(new)
    with connection(data_dir) as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM users WHERE id=?',(key,)).fetchone()
        if not row or not row['enabled'] or not verify(current,row['password_hash']):
            raise ValueError('Current password is incorrect.')
        c.execute('UPDATE users SET password_hash=?,version=version+1 WHERE id=?',(encoded,key))

def manage(data_dir,key,action,password=None):
    if action not in ('disable','enable','reset_password'):
        raise ValueError('Unknown user action.')
    encoded=password_hash(password) if action=='reset_password' else None
    with connection(data_dir) as c:
        row=c.execute('SELECT * FROM users WHERE id=?',(key,)).fetchone()
        if not row: raise ValueError('User not found.')
        if row['is_admin']: raise ValueError('Use your own password settings to manage the administrator.')
        if action=='reset_password': c.execute('UPDATE users SET password_hash=?,version=version+1,setup_required=1 WHERE id=?',(encoded,key))
        else: c.execute('UPDATE users SET enabled=?,version=version+1 WHERE id=?',(int(action=='enable'),key))


def delete_user(data_dir,key,confirmation):
    # Caller holds the user's data lock until filesystem cleanup is complete.
    with connection(data_dir) as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM users WHERE id=?',(key,)).fetchone()
        if not row: raise ValueError('User not found.')
        if key==1 or row['is_admin']: raise ValueError('The administrator cannot be deleted.')
        if confirmation != row['username']:
            raise ValueError('Type the username exactly to confirm deletion.')
        c.execute('UPDATE users SET enabled=0,version=version+1 WHERE id=?',(key,))
    # Disable first so a failed cleanup or restart cannot expose partially deleted data.
    folder=data_dir/'users'/str(key)
    try:
        if folder.exists() or folder.is_symlink(): shutil.rmtree(folder)
    except OSError as error:
        raise ValueError('Data deletion could not finish. The user is disabled. Check data-folder permissions and retry deleting the user.') from error
    with connection(data_dir) as c:
        c.execute('DELETE FROM users WHERE id=?',(key,))


QUESTIONS = ["What is your mother's middle name?", "What was the name of the town or city where you were born?", "What was the first and last name of your childhood best friend?"]


def answer_hash(answer,salt=None):
    if not isinstance(answer,str) or not 1<=len(answer)<=256 or not answer.strip():
        raise ValueError('Each security answer must contain between 1 and 256 characters.')
    normalized=unicodedata.normalize('NFKC',answer).strip().casefold()
    salt=salt or secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac('sha256',normalized.encode(),bytes.fromhex(salt),600000).hex()
    return salt+':'+digest


def finish_setup(data_dir,key,version,password,answers):
    encoded=password_hash(password)
    if not isinstance(answers,list) or len(answers)!=3: raise ValueError('Answer all three security questions.')
    hashes=[answer_hash(a) for a in answers]
    with connection(data_dir) as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM users WHERE id=?',(key,)).fetchone()
        if not row or not row['enabled'] or row['version']!=version or not row['setup_required']:
            raise ValueError('Setup session expired. Sign in again.')
        c.execute('UPDATE users SET password_hash=?,recovery_answers=?,setup_required=0,version=version+1 WHERE id=?',(encoded,json.dumps(hashes),key))
        c.execute('DELETE FROM recovery_tokens WHERE user_id=?',(key,))


def _limit(c,scope,limit):
    now=time.time()
    c.execute('DELETE FROM recovery_attempts WHERE created<?',(now-900,))
    if c.execute('SELECT COUNT(*) FROM recovery_attempts WHERE scope=?',(scope,)).fetchone()[0]>=limit:
        raise ValueError('Too many recovery attempts. Try again in 15 minutes.')
    c.execute('INSERT INTO recovery_attempts VALUES (?,?)',(scope,now))


def _token_key(token):
    return hashlib.sha256(str(token or '').encode()).hexdigest()


def recovery_start(data_dir,name,ip):
    name=str(name or '').strip().lower()[:100]
    name_key=_token_key(name)
    token=secrets.token_urlsafe(32)
    questions=secrets.SystemRandom().sample(range(3),2)
    with connection(data_dir) as c:
        c.execute('BEGIN IMMEDIATE')
        _limit(c,'ip:'+ip,20)
        _limit(c,'name:'+name_key,5)
        c.execute('DELETE FROM recovery_tokens WHERE expires<?',(time.time(),))
        row=c.execute('SELECT * FROM users WHERE username=?',(name,)).fetchone()
        valid=row and row['enabled'] and row['recovery_answers']
        # Identical response shape for missing, disabled, and unenrolled accounts.
        c.execute('INSERT INTO recovery_tokens VALUES (?,?,?,?,?,?,?)',(_token_key(token),row['id'] if valid else None,row['version'] if valid else None,json.dumps(questions),time.time()+600,0,name_key))
    return {'token':token,'questions':[{'id':q,'text':QUESTIONS[q]} for q in questions]}


def recovery_verify(data_dir,token,answers,ip):
    reset=secrets.token_urlsafe(32)
    success=False
    with connection(data_dir) as c:
        c.execute('BEGIN IMMEDIATE')
        _limit(c,'verify-ip:'+ip,20)
        challenge=c.execute('SELECT * FROM recovery_tokens WHERE token=? AND verified=0',(_token_key(token),)).fetchone()
        if challenge:
            _limit(c,'verify-name:'+challenge['name_key'],5)
            c.execute('DELETE FROM recovery_tokens WHERE token=?',(_token_key(token),))
        row=c.execute('SELECT * FROM users WHERE id=?',(challenge['user_id'],)).fetchone() if challenge else None
        valid=bool(challenge and challenge['expires']>time.time() and row and row['enabled'] and row['version']==challenge['version'] and row['recovery_answers'])
        hashes=json.loads(row['recovery_answers']) if valid else ['0'*32+':'+'0'*64]*3
        questions=json.loads(challenge['questions']) if challenge else [0,1]
        checks=[]
        for q in questions:
            answer=answers.get(str(q),'') if isinstance(answers,dict) else ''
            try: checks.append(hmac.compare_digest(answer_hash(answer,hashes[q].split(':')[0]),hashes[q]))
            except (ValueError,TypeError): checks.append(False)
        success=valid and all(checks)
        if success:
            c.execute('INSERT INTO recovery_tokens VALUES (?,?,?,?,?,?,?)',(_token_key(reset),row['id'],row['version'],'[]',time.time()+300,1,challenge['name_key']))
    if not success: raise ValueError('Recovery could not be verified. Start again and check both answers.')
    return {'reset_token':reset}


def recovery_reset(data_dir,token,password):
    encoded=password_hash(password)
    with connection(data_dir) as c:
        c.execute('BEGIN IMMEDIATE')
        ticket=c.execute('SELECT * FROM recovery_tokens WHERE token=? AND verified=1',(_token_key(token),)).fetchone()
        row=c.execute('SELECT * FROM users WHERE id=?',(ticket['user_id'],)).fetchone() if ticket else None
        if not ticket or ticket['expires']<time.time() or not row or not row['enabled'] or row['version']!=ticket['version']:
            raise ValueError('Password reset expired. Start recovery again.')
        c.execute('UPDATE users SET password_hash=?,setup_required=0,version=version+1 WHERE id=?',(encoded,row['id']))
        c.execute('DELETE FROM recovery_tokens WHERE user_id=?',(row['id'],))
