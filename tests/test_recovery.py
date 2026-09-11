from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
import auth
import test_users

ANSWERS=['Mary Ann','Example City','Alex Smith']
PASSWORD='new-private-password-123'

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.data=Path(self.temp.name)
        auth.init(self.data,'temporary-password-123')
    def tearDown(self): self.temp.cleanup()
    def enroll(self): auth.finish_setup(self.data,1,1,PASSWORD,ANSWERS)
    def verify(self,challenge):
        return auth.recovery_verify(self.data,challenge['token'],{str(q['id']):ANSWERS[q['id']].swapcase() for q in challenge['questions']},'test-ip')
    def test_setup_hashes_all_answers_and_two_question_recovery(self):
        self.enroll()
        with auth.connection(self.data) as c:
            stored=c.execute('SELECT recovery_answers FROM users').fetchone()[0]
            self.assertFalse(any(a in stored for a in ANSWERS))
        challenge=auth.recovery_start(self.data,'ADMIN','test-ip')
        self.assertEqual(len({q['id'] for q in challenge['questions']}),2)
        verified=self.verify(challenge)
        with self.assertRaises(ValueError): self.verify(challenge)
        auth.recovery_reset(self.data,verified['reset_token'],'replacement-password-123')
        self.assertIsNone(auth.authenticate(self.data,'admin',PASSWORD))
        self.assertIsNotNone(auth.authenticate(self.data,'admin','replacement-password-123'))
        with self.assertRaises(ValueError): auth.recovery_reset(self.data,verified['reset_token'],PASSWORD)
    def test_wrong_missing_expired_and_disabled_accounts(self):
        self.enroll()
        challenge=auth.recovery_start(self.data,'admin','ip')
        with self.assertRaises(ValueError): auth.recovery_verify(self.data,challenge['token'],{},'ip')
        challenge=auth.recovery_start(self.data,'missing','ip')
        self.assertEqual(len(challenge['questions']),2)
        with self.assertRaises(ValueError): self.verify(challenge)
        challenge=auth.recovery_start(self.data,'admin','ip')
        with auth.connection(self.data) as c: c.execute('UPDATE recovery_tokens SET expires=0')
        with self.assertRaises(ValueError): self.verify(challenge)
        challenge=auth.recovery_start(self.data,'admin','ip')
        with auth.connection(self.data) as c: c.execute('UPDATE users SET enabled=0')
        with self.assertRaises(ValueError): self.verify(challenge)
    def test_limits_persist_across_initialization_and_tokens_track_version(self):
        self.enroll()
        challenge=auth.recovery_start(self.data,'admin','ip')
        verified=self.verify(challenge)
        auth.change_password(self.data,1,PASSWORD,'another-password-123')
        with self.assertRaises(ValueError): auth.recovery_reset(self.data,verified['reset_token'],PASSWORD)
        for _ in range(4): auth.recovery_start(self.data,'admin','ip')
        auth.init(self.data,'not-used-password')
        with self.assertRaises(ValueError): auth.recovery_start(self.data,'admin','different-ip')
    def test_old_user_schema_preserved_and_requires_setup(self):
        other=self.data/'legacy';other.mkdir()
        with closing(sqlite3.connect(other/'users.sqlite3')) as c, c:
            c.execute('CREATE TABLE users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,is_admin INTEGER NOT NULL DEFAULT 0,enabled INTEGER NOT NULL DEFAULT 1,version INTEGER NOT NULL DEFAULT 1)')
            c.execute('INSERT INTO users VALUES (1,?,?,1,1,1)',('owner',auth.password_hash(PASSWORD)))
        auth.init(other,'unused-password-123')
        self.assertTrue(auth.authenticate(other,'owner',PASSWORD)['setup_required'])

class RecoveryApiTests(unittest.TestCase):
    setUp=test_users.MultiUserTests.setUp
    tearDown=test_users.MultiUserTests.tearDown
    req=test_users.MultiUserTests.req
    login=test_users.MultiUserTests.login
    def test_setup_gate_and_session_invalidation(self):
        import app
        password='temporary-password-123'
        status,result=self.req('/api/users','POST',{'username':'newuser','password':password})
        self.assertEqual(status,200)
        self.assertEqual(self.req('/api/login','POST',{'username':'newuser','password':password},'newuser')[0],200)
        for path in ['/api/state','/api/transactions','/api/export','/api/users']:
            self.assertEqual(self.req(path,who='newuser')[0],403)
        self.assertEqual(self.req('/api/complete-setup','POST',{'new_password':PASSWORD,'answers':ANSWERS},'newuser')[0],200)
        self.assertEqual(self.req('/api/state',who='newuser')[0],401)
        self.login('newuser',PASSWORD)
        self.assertEqual(self.req('/api/state',who='newuser')[0],200)
        challenge=self.req('/api/recovery/start','POST',{'username':'newuser'})[1]
        answers={str(q['id']):ANSWERS[q['id']].lower() for q in challenge['questions']}
        status,verified=self.req('/api/recovery/verify','POST',{'token':challenge['token'],'answers':answers})
        self.assertEqual(status,200)
        self.assertEqual(self.req('/api/recovery/reset','POST',{'reset_token':verified['reset_token'],'new_password':'replacement-password-123'})[0],200)
        self.assertEqual(self.req('/api/state',who='newuser')[0],401)
