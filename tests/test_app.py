import http.client
import json
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path
import app

class DatabaseFixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        app.DATA=Path(self.temp.name)
        app.init()
        with app.db() as c:
            c.execute("INSERT INTO accounts(id,name,opening) VALUES (1,'Chequing',10000),(2,'Visa',-5000)")
    def tearDown(self): self.temp.cleanup()
    def tx(self,c,amount,kind='expense',day='2026-08-05',cat=1):
        return app.insert(c,dict(account_id=1,date=day,payee='Store',amount=amount,kind=kind,category_id=cat,note=''))

class FinanceTests(DatabaseFixture):
    def test_exact_money(self):
        self.assertEqual(app.money('0.29'),29)
        self.assertEqual(app.money('(1,234.56)'),-123456)
        self.assertEqual(app.money('1.234,56',True),123456)
        for value in ('NaN','Infinity','0.001','abc'):
            with self.assertRaises(app.Invalid): app.money(value)
    def test_income_expenses_refunds_and_transfers(self):
        with app.db() as c:
            self.tx(c,500000,'income');self.tx(c,-12000);self.tx(c,2000,'refund');self.tx(c,-50000,'transfer');self.tx(c,50000,'transfer')
            s=app.summary(c,'2026-08')
            self.assertEqual((s['income'],s['expenses'],s['remaining']),(500000,10000,490000))
            self.assertEqual(s['categories'][0]['spent'],10000)
    def test_history_includes_zero_months_after_start(self):
        with app.db() as c:
            self.tx(c,-30000,day='2026-05-01');self.tx(c,-20000,day='2026-08-01')
            s=app.summary(c,'2026-08')
            self.assertEqual(len(s['periods']),3)
            self.assertEqual(s['categories'][0]['average'],10000)
    def test_partial_month_uses_same_day(self):
        today=date.today();prev=app.shift_month(today,-1)
        with app.db() as c:
            self.tx(c,-10000,day=prev.isoformat())
            last=app.calendar.monthrange(prev.year,prev.month)[1]
            if today.day<last:self.tx(c,-80000,day=prev.replace(day=last).isoformat())
            self.tx(c,-15000,day=today.isoformat())
            s=app.summary(c,today.strftime('%Y-%m'))
            self.assertTrue(s['partial']);self.assertEqual(s['categories'][0]['average'],10000)
    def test_no_history_does_not_invent_baseline(self):
        with app.db() as c:
            self.tx(c,-200)
            self.assertIsNone(app.summary(c,'2026-08')['categories'][0]['average'])
    def test_csv_quoted_bom_and_decimal(self):
        with app.db() as c:
            p=app.preview(c,{'account_id':1,'text':'\ufeffDate;Description;Amount\n05/08/2026;"Coffee; lunch";-12,34\n','mapping':{'delimiter':';','date':'0','payee':'1','amount':'2','date_format':'dmy','decimal_comma':True}})
            self.assertEqual(p['rows'][0]['tx']['amount'],-1234)
            self.assertEqual(p['rows'][0]['tx']['payee'],'Coffee; lunch')
    def test_split_columns_and_invalid_rows(self):
        with app.db() as c:
            p=app.preview(c,{'account_id':1,'text':'Date,Payee,Debit,Credit\n2026-08-01,Shop,12.34,\n2026-08-02,Pay,,100\n2026-08-03,Bad,10,20\n','mapping':{'date':'0','payee':'1','mode':'split','debit':'2','credit':'3'}})
            self.assertEqual([r['status'] for r in p['rows']],['new','new','invalid'])
            self.assertEqual(p['rows'][1]['tx']['amount'],10000)
    def preview_ids(self,c):
        return app.preview(c,{'account_id':1,'text':'Date,Payee,Amount,ID\n2026-08-01,Shop,-12.34,bank-1\n2026-08-01,Shop,-12.34,bank-2\n','mapping':{'date':'0','payee':'1','amount':'2','imported_id':'3'}})
    def test_import_atomic_duplicate_choice_and_replay(self):
        with app.db() as c:
            p=self.preview_ids(c)
            self.assertEqual([r['status'] for r in p['rows']],['new','possible'])
        with self.assertRaises(app.Invalid):
            with app.db() as c: app.commit_import(c,{'token':p['token'],'selected':[{'index':0},{'index':1}]})
        with app.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],0)
            result=app.commit_import(c,{'token':p['token'],'selected':[{'index':0},{'index':1,'allow_possible':True}]})
            self.assertEqual(result['imported'],2)
        with app.db() as c:
            with self.assertRaises(app.Invalid):app.commit_import(c,{'token':p['token'],'selected':[{'index':0}]})
            p2=self.preview_ids(c)
            self.assertEqual([r['status'] for r in p2['rows']],['possible','possible'])
    def test_duplicate_id_scoped_to_account(self):
        with app.db() as c:
            self.tx(c,-100)
            tx={'account_id':2,'date':'2026-08-05','amount':-100,'payee':'Store','imported_id':None}
            self.assertEqual(app.duplicate(c,tx),'new')
    def test_rules_case_insensitive(self):
        with app.db() as c:
            c.execute("INSERT INTO rules(contains_text,category_id) VALUES ('coffee',2)")
            self.assertEqual(app.category(c,'BIG COFFEE SHOP'),2)
    def test_empty_csv_and_bad_date(self):
        for raw in ('','\n\n'):
            with self.assertRaises(app.Invalid):app.parse_csv(raw)
        with self.assertRaises(app.Invalid):app.valid_date('2026-02-30')

class CategorizationTests(DatabaseFixture):
    def test_changes_only_categories_across_months_and_can_clear(self):
        with app.db() as c:
            first=self.tx(c,-5000,day='2026-01-10',cat=1)
            second=self.tx(c,1000,kind='refund',day='2026-08-10',cat=1)
            untouched=self.tx(c,-700,day='2026-08-11',cat=1)
            before=[dict(r) for r in c.execute('SELECT * FROM transactions ORDER BY id')]
        with app.db() as c:
            self.assertEqual(app.categorize_transactions(c,{'ids':[first,second],'category_id':2}),{'updated':2})
        with app.db() as c:
            after=[dict(r) for r in c.execute('SELECT * FROM transactions ORDER BY id')]
            for old,new in zip(before,after):
                expected=2 if old['id'] in (first,second) else 1
                self.assertEqual(new['category_id'],expected)
                self.assertEqual({k:v for k,v in old.items() if k!='category_id'},{k:v for k,v in new.items() if k!='category_id'})
            self.assertEqual(app.summary(c,'2026-01')['categories'][0]['id'],2)
        with app.db() as c: app.categorize_transactions(c,{'ids':[first,second],'category_id':None})
        with app.db() as c:
            self.assertIsNone(c.execute('SELECT category_id FROM transactions WHERE id=?',(first,)).fetchone()[0])
    def test_rejects_invalid_selection_without_partial_changes(self):
        with app.db() as c:
            expense=self.tx(c,-5000)
            transfer=self.tx(c,-5000,kind='transfer',cat=None)
            income=self.tx(c,5000,kind='income',cat=None)
        invalid=[{'ids':[expense,transfer],'category_id':2},{'ids':[expense,income],'category_id':2},
                 {'ids':[expense,99999],'category_id':2},{'ids':[expense],'category_id':99999},
                 {'ids':[expense,expense],'category_id':2},{'ids':[],'category_id':2},
                 {'ids':[True],'category_id':2},{'ids':[expense]}, {'ids':[expense],'category_id':''}]
        for payload in invalid:
            with self.assertRaises(app.Invalid):
                with app.db() as c:app.categorize_transactions(c,payload)
            with app.db() as c:self.assertEqual(c.execute('SELECT category_id FROM transactions WHERE id=?',(expense,)).fetchone()[0],1)

class HttpTests(DatabaseFixture):
    def test_login_crud_transfer_export_and_persistence(self):
        app.PASSWORD='test-password-long'
        app.auth.init(app.DATA,app.PASSWORD)
        app.SESSIONS.clear();app.ATTEMPTS.clear()
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        cookie=''
        def request(path,method='GET',body=None,csrf=True):
            nonlocal cookie
            con=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            headers={'Cookie':cookie}
            if csrf:headers['X-Requested-With']='MonthlySpend'
            payload=json.dumps(body) if body is not None else None
            con.request(method,path,payload,headers)
            response=con.getresponse();raw=response.read()
            if response.getheader('Set-Cookie'):cookie=response.getheader('Set-Cookie').split(';')[0]
            status=response.status;con.close()
            try: return status,json.loads(raw)
            except ValueError:return status,raw.decode()
        try:
            self.assertEqual(request('/api/state')[0],401)
            self.assertEqual(request('/api/login','POST',{'username':'admin','password':app.PASSWORD},False)[0],403)
            self.assertEqual(request('/api/login','POST',{'username':'admin','password':app.PASSWORD})[0],200)
            tx={'account_id':1,'date':'2026-08-12','payee':'Visa payment','amount':'20.00','kind':'transfer','destination_id':2}
            self.assertEqual(request('/api/transactions','POST',tx)[0],200)
            s=request('/api/month?month=2026-08')[1]
            self.assertEqual(len(s['transactions']),2);self.assertEqual(s['expenses'],0)
            self.assertEqual(request('/api/transactions/'+str(s['transactions'][0]['id']),'DELETE',{})[0],200)
            tx.update(kind='expense',payee='=EVIL()',category_id=1)
            self.assertEqual(request('/api/transactions','POST',tx)[0],200)
            s=request('/api/month?month=2026-08')[1]
            tx.update(id=s['transactions'][0]['id'],amount='15.50')
            self.assertEqual(request('/api/transactions','PUT',tx)[0],200)
            self.assertEqual(request('/api/month?month=2026-08')[1]['expenses'],1550)
            self.assertIn("'=EVIL()",request('/api/export')[1])
            app.init()
            self.assertEqual(request('/api/month?month=2026-08')[1]['expenses'],1550)
            august_id=tx['id']
            older={**tx,'date':'2026-01-10','payee':'Same merchant','amount':'9.00'}
            self.assertEqual(request('/api/transactions','POST',older)[0],200)
            rows=request('/api/transactions')[1]['transactions']
            self.assertEqual(len(rows),2)
            self.assertEqual([r['date'] for r in rows],['2026-08-12','2026-01-10'])
            ids=[r['id'] for r in rows]
            self.assertEqual(request('/api/transactions/category','POST',{'ids':ids,'category_id':2},False)[0],403)
            self.assertEqual(request('/api/transactions/category','POST',{'ids':ids,'category_id':2}),(200,{'updated':2}))
            self.assertTrue(all(r['category_id']==2 for r in request('/api/transactions')[1]['transactions']))
            self.assertEqual(request('/api/month?month=2026-08')[1]['expenses'],1550)
            self.assertEqual(len(request('/api/month?month=2026-01')[1]['transactions']),1)
            self.assertEqual(request('/api/logout','POST',{})[0],200)
            self.assertEqual(request('/api/state')[0],401)
            self.assertEqual(request('/api/transactions')[0],401)
            self.assertEqual(request('/api/transactions/category','POST',{'ids':ids,'category_id':1})[0],401)
        finally:
            server.shutdown();server.server_close();thread.join()

if __name__=='__main__': unittest.main()
