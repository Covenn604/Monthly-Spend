import concurrent.futures
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
import app

PASSWORD='administrator-password-123'
USER_PASSWORD='user-password-long-123'

class MultiUserTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        app.DATA=Path(self.temp.name)
        app.CURRENT_USER.set(1)
        app.init()
        with app.db() as c:
            c.execute("INSERT INTO accounts(name,opening) VALUES ('Original bank',12300)")
            self.original=app.insert(c,dict(account_id=1,date='2026-01-01',payee='Private original',amount=-300,kind='expense',category_id=1,note='Legacy note'))
            c.execute("INSERT INTO rules(contains_text,category_id) VALUES ('private',1)")
            c.execute("INSERT INTO profiles VALUES ('Private profile','{}')")
        app.auth.init(app.DATA,PASSWORD)
        app.SESSIONS.clear();app.ATTEMPTS.clear()
        self.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.cookies={}
        self.login('admin',PASSWORD)
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def req(self,path,method='GET',data=None,who='admin'):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        c.request(method,path,json.dumps(data) if data is not None else None,{'X-Requested-With':'MonthlySpend','Cookie':self.cookies.get(who,'')})
        r=c.getresponse();body=r.read()
        if r.getheader('Set-Cookie'):self.cookies[who]=r.getheader('Set-Cookie').split(';')[0]
        status=r.status;c.close()
        try: return status,json.loads(body)
        except ValueError:return status,body.decode()
    def login(self,who,password):
        status,payload=self.req('/api/login','POST',{'username':who,'password':password},who)
        self.assertEqual(status,200)
        if payload.get('setup_required'):
            self.assertEqual(self.req('/api/complete-setup','POST',{'new_password':password,'answers':['test middle','test city','test friend']},who)[0],200)
            self.assertEqual(self.req('/api/login','POST',{'username':who,'password':password},who)[0],200)
    def add_user(self,who='alice'):
        status,payload=self.req('/api/users','POST',{'username':who,'password':USER_PASSWORD})
        self.assertEqual(status,200);self.login(who,USER_PASSWORD)
        return payload['user']['id']
    def test_upgrade_and_restart_preserve_owner_data_and_password(self):
        before=self.req('/api/state')[1]
        self.assertEqual(before['accounts'][0]['name'],'Original bank')
        self.assertEqual(before['accounts'][0]['balance'],12000)
        self.assertEqual(before['user']['id'],1)
        app.auth.init(app.DATA,'different-password-123','other-admin')
        self.assertIsNotNone(app.auth.authenticate(app.DATA,'admin',PASSWORD))
        self.assertIsNone(app.auth.authenticate(app.DATA,'other-admin','different-password-123'))
        with app.auth.connection(app.DATA) as c:
            stored=c.execute('SELECT password_hash FROM users').fetchone()[0]
            self.assertNotIn(PASSWORD,stored)
        self.assertEqual(self.req('/api/transactions')[1]['transactions'][0]['note'],'Legacy note')
    def test_users_isolated_for_reads_writes_imports_and_rules(self):
        alice=self.add_user()
        self.assertTrue((app.DATA/'users'/str(alice)/'spearmint.sqlite3').exists())
        personal=self.req('/api/state',who='alice')[1]
        self.assertEqual(personal['accounts'],[]);self.assertEqual(personal['profiles'],[]);self.assertEqual(personal['rules'],[])
        self.assertEqual(self.req('/api/transactions',who='alice')[1]['transactions'],[])
        self.assertNotIn('Private original',self.req('/api/export',who='alice')[1])
        self.assertEqual(self.req('/api/transactions/1','DELETE',{},'alice')[0],400)
        self.assertEqual(self.req('/api/transactions/delete','POST',{'ids':[1],'confirmed':True},'alice')[0],400)
        self.assertEqual(self.req('/api/transactions/category','POST',{'ids':[1],'category_id':2},'alice')[0],400)
        self.assertEqual(self.req('/api/accounts','POST',{'name':'Alice bank','opening':'0','user_id':1},'alice')[0],200)
        self.assertEqual(self.req('/api/state')[1]['accounts'][0]['name'],'Original bank')
        status,p=self.req('/api/csv/preview','POST',{'account_id':1,'text':'Date,Payee,Amount\n2026-02-01,Secret merchant,-42\n','mapping':{'date':'0','payee':'1','amount':'2'}})
        self.assertEqual(status,200)
        self.assertEqual(self.req('/api/csv/commit','POST',{'token':p['token'],'selected':[{'index':0}]},'alice')[0],400)
        self.assertEqual(self.req('/api/categories/1','PUT',{'name':'Alice housing'},'alice')[0],200)
        self.assertEqual(next(c['name'] for c in self.req('/api/state')[1]['categories'] if c['id']==1),'Housing')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda u:self.req('/api/state',who=u)[1],['admin','alice']*5))
        self.assertTrue(all(r['accounts'][0]['name']==('Original bank' if i%2==0 else 'Alice bank') for i,r in enumerate(results)))
    def test_admin_permissions_disable_reset_and_password_change(self):
        key=self.add_user()
        self.assertEqual(self.req('/api/users',who='alice')[0],403)
        self.assertEqual(self.req('/api/users','POST',{'username':'rogue','password':USER_PASSWORD},'alice')[0],403)
        self.assertEqual(self.req('/api/users/1','POST',{'action':'disable'})[0],400)
        self.assertEqual(self.req('/api/users/'+str(key),'POST',{'action':'disable'})[0],200)
        self.assertEqual(self.req('/api/state',who='alice')[0],401)
        self.assertEqual(self.req('/api/login','POST',{'username':'alice','password':USER_PASSWORD},'alice')[0],401)
        self.assertEqual(self.req('/api/users/'+str(key),'POST',{'action':'enable'})[0],200)
        self.login('alice',USER_PASSWORD)
        self.assertEqual(self.req('/api/users/'+str(key),'POST',{'action':'reset_password','password':'replacement-password-123'})[0],200)
        self.assertEqual(self.req('/api/state',who='alice')[0],401)
        self.login('alice','replacement-password-123')
        self.assertEqual(self.req('/api/password','POST',{'current_password':'wrong','new_password':'another-password-123'},'alice')[0],400)
        self.assertEqual(self.req('/api/password','POST',{'current_password':'replacement-password-123','new_password':'another-password-123'},'alice')[0],200)
        self.assertEqual(self.req('/api/state',who='alice')[0],401)
        self.login('alice','another-password-123')
    def test_category_rename_delete_move_and_reject_invalid(self):
        self.assertEqual(self.req('/api/categories/1','PUT',{'name':'Home costs'})[0],200)
        self.assertEqual(self.req('/api/transactions')[1]['transactions'][0]['category'],'Home costs')
        self.assertEqual(self.req('/api/categories/1','DELETE',{})[0],400)
        self.assertEqual(self.req('/api/categories/1','DELETE',{'replacement_id':None})[0],400)
        self.assertEqual(self.req('/api/categories/1','DELETE',{'replacement_id':1})[0],400)
        self.assertEqual(self.req('/api/categories/1','DELETE',{'replacement_id':9999})[0],400)
        self.assertEqual(self.req('/api/categories/1','DELETE',{'replacement_id':2})[0],200)
        records=self.req('/api/transactions')[1]['transactions']
        self.assertEqual(records[0]['category_id'],2);self.assertEqual(records[0]['amount'],-300)
        self.assertEqual(self.req('/api/state')[1]['rules'][0]['category_id'],2)
        self.assertEqual(self.req('/api/categories/3','DELETE',{})[0],200)
        self.assertEqual(self.req('/api/rules/1','DELETE',{})[0],200)
        self.assertEqual(self.req('/api/categories/2','DELETE',{'replacement_id':None})[0],200)
        self.assertIsNone(self.req('/api/transactions')[1]['transactions'][0]['category_id'])
        self.assertEqual(self.req('/api/categories/4','PUT',{'name':''})[0],400)
    def test_edit_opening_balance_preserves_activity_and_user_isolation(self):
        before=self.req('/api/transactions')[1]['transactions']
        monthly=self.req('/api/month?month=2026-01')[1]['expenses']
        # Existing fixture activity is -3.00; a -237.84 opening yields -240.84.
        self.assertEqual(self.req('/api/accounts/1','PUT',{'opening':'-237.84'})[0],200)
        self.assertEqual(self.req('/api/state')[1]['accounts'][0]['balance'],-24084)
        self.assertEqual(self.req('/api/transactions')[1]['transactions'],before)
        self.assertEqual(self.req('/api/month?month=2026-01')[1]['expenses'],monthly)
        self.assertEqual(self.req('/api/accounts/1','PUT',{'opening':'NaN'})[0],400)
        self.assertEqual(self.req('/api/accounts/99999','PUT',{'opening':'0'})[0],400)
        self.assertEqual(self.req('/api/state')[1]['accounts'][0]['balance'],-24084)
        self.add_user()
        self.assertEqual(self.req('/api/accounts/1','PUT',{'opening':'0'},'alice')[0],400)
        self.req('/api/accounts','POST',{'name':'Alice account','opening':'0'},'alice')
        self.assertEqual(self.req('/api/accounts/1','PUT',{'opening':'20'},'alice')[0],200)
        self.assertEqual(self.req('/api/state')[1]['accounts'][0]['balance'],-24084)
        self.assertEqual(self.req('/api/state',who='alice')[1]['accounts'][0]['balance'],2000)

    def test_deleted_categories_stay_deleted_on_login(self):
        self.add_user()
        for cat in self.req('/api/state',who='alice')[1]['categories']:
            self.assertEqual(self.req('/api/categories/'+str(cat['id']),'DELETE',{},'alice')[0],200)
        self.login('alice',USER_PASSWORD)
        self.assertEqual(self.req('/api/state',who='alice')[1]['categories'],[])

    def test_profile_management_defaults_and_isolation(self):
        before=self.req('/api/transactions')[1]
        # Existing mappings survive the new association table migration.
        with app.db() as c:
            c.execute("INSERT INTO profiles VALUES ('Legacy',?)",(json.dumps({'invert':True}),))
        app.init()
        self.assertEqual(self.req('/api/state')[1]['profiles'][0]['mapping'],{'invert':True})
        self.assertEqual(self.req('/api/profile-default','PUT',{'account_id':1,'name':'Legacy'})[0],200)
        for i in range(2,6):
            self.assertEqual(self.req('/api/accounts','POST',{'name':f'Account {i}','opening':'0'})[0],200)
        for i in range(1,6):
            self.assertEqual(self.req('/api/profiles','POST',{'name':f'Format {i}','mapping':{'invert':i%2==0,'skip_lines':i},'account_id':i})[0],200)
        self.login('admin',PASSWORD)
        current=self.req('/api/state')[1]
        self.assertEqual({a['id']:a['default_profile'] for a in current['accounts']},{i:f'Format {i}' for i in range(1,6)})
        self.assertEqual(self.req('/api/profiles','POST',{'name':'Format 1','mapping':{}})[0],400)
        self.assertEqual(self.req('/api/profiles','PUT',{'original_name':'Format 1','name':'Format 2'})[0],400)
        self.assertEqual(self.req('/api/profiles','PUT',{'original_name':'Format 1','name':'Renamed'})[0],200)
        current=self.req('/api/state')[1]
        self.assertEqual(next(a for a in current['accounts'] if a['id']==1)['default_profile'],'Renamed')
        self.assertEqual(next(p for p in current['profiles'] if p['name']=='Renamed')['mapping']['skip_lines'],1)
        self.assertEqual(self.req('/api/profiles','PUT',{'original_name':'Renamed','name':'Renamed','mapping':{'date_format':'compact'}})[0],200)
        self.add_user()
        self.assertEqual(self.req('/api/profiles','DELETE',{'name':'Renamed'},'alice')[0],400)
        self.assertEqual(self.req('/api/profile-default','PUT',{'account_id':1,'name':'Renamed'},'alice')[0],400)
        self.assertEqual(self.req('/api/profiles','POST',{'name':'Renamed','mapping':{}},'alice')[0],200)
        self.assertEqual(self.req('/api/profiles','DELETE',{'name':'Renamed'},'alice')[0],200)
        self.assertEqual(self.req('/api/profiles','DELETE',{'name':'Renamed'})[0],200)
        current=self.req('/api/state')[1]
        self.assertIsNone(next(a for a in current['accounts'] if a['id']==1)['default_profile'])
        self.assertEqual(next(a for a in current['accounts'] if a['id']==2)['default_profile'],'Format 2')
        self.assertEqual(self.req('/api/profile-default','PUT',{'account_id':2,'name':None})[0],200)
        self.assertEqual(self.req('/api/profile-default','PUT',{'account_id':2,'name':'missing'})[0],400)
        self.assertEqual(self.req('/api/profiles','POST',{'name':'Invalid account','mapping':{},'account_id':9999})[0],400)
        self.assertFalse(any(p['name']=='Invalid account' for p in self.req('/api/state')[1]['profiles']))
        self.assertEqual(self.req('/api/transactions')[1],before)

    def test_delete_user_requires_confirmation_and_preserves_other_users(self):
        key=self.add_user()
        self.req('/api/accounts','POST',{'name':'Private account','opening':'0'},'alice')
        self.req('/api/transactions','POST',{'account_id':1,'date':'2026-01-01','payee':'Private purchase','amount':'20','kind':'expense'},'alice')
        folder=app.DATA/'users'/str(key)
        self.assertTrue(folder.exists())
        before=self.req('/api/transactions')[1]
        for confirmation in [None,'','ALICE','alice ']:
            self.assertEqual(self.req('/api/users/'+str(key),'DELETE',{'confirm_username':confirmation})[0],400)
        self.assertTrue(folder.exists())
        self.assertEqual(self.req('/api/users/1','DELETE',{'confirm_username':'admin'})[0],400)
        self.assertEqual(self.req('/api/users/'+str(key),'DELETE',{'confirm_username':'alice'},'alice')[0],403)
        self.assertEqual(self.req('/api/users/'+str(key),'DELETE',{'confirm_username':'alice'})[0],200)
        self.assertFalse(folder.exists())
        self.assertIsNone(app.auth.get(app.DATA,key))
        self.assertEqual(self.req('/api/state',who='alice')[0],401)
        self.assertEqual(self.req('/api/login','POST',{'username':'alice','password':USER_PASSWORD},'alice')[0],401)
        self.assertEqual(self.req('/api/transactions')[1],before)
        # Requests already authenticated before deletion cannot recreate storage.
        token=app.CURRENT_USER.set(key)
        try:
            with self.assertRaises(app.Invalid):
                with app.db(): pass
        finally: app.CURRENT_USER.reset(token)
        self.assertFalse(folder.exists())
        new_key=self.add_user()
        self.assertGreater(new_key,key)
        self.assertEqual(self.req('/api/state',who='alice')[1]['accounts'],[])

    def test_delete_user_cleanup_failure_is_retryable(self):
        from unittest.mock import patch
        key=self.add_user()
        with patch('auth.shutil.rmtree',side_effect=PermissionError('test')):
            status,result=self.req('/api/users/'+str(key),'DELETE',{'confirm_username':'alice'})
        self.assertEqual(status,400)
        self.assertIn('disabled',result['error'])
        self.assertFalse(app.auth.get(app.DATA,key)['enabled'])
        self.assertEqual(self.req('/api/state',who='alice')[0],401)
        self.assertEqual(self.req('/api/users/'+str(key),'DELETE',{'confirm_username':'alice'})[0],200)
        self.assertFalse((app.DATA/'users'/str(key)).exists())
