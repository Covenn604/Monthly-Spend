import unittest
from test_app import DatabaseFixture
import app

class MerchantHistoryTests(DatabaseFixture):
    def add(self,c,payee,cat,kind='expense'):
        return app.insert(c,dict(account_id=1,date='2026-01-01',payee=payee,amount=-500 if kind=='expense' else 500,kind=kind,category_id=cat,note=''))
    def test_normalized_history_rules_and_conflicts(self):
        with app.db() as c:
            self.add(c,'  Coffee  Shop #12 ',2)
            self.add(c,'COFFEE SHOP #12',2)
            self.assertEqual(app.category(c,'coffee shop #12'),2)
            self.assertIsNone(app.category(c,'coffee shop #13'))
            self.add(c,'Coffee shop #12',3)
            self.assertIsNone(app.category(c,'coffee shop #12'))
            c.execute("INSERT INTO rules(contains_text,category_id) VALUES ('coffee',4)")
            self.assertEqual(app.category(c,'coffee shop #12'),4)
    def test_income_refund_transfer_and_uncategorized_do_not_train(self):
        with app.db() as c:
            for kind in ('income','refund','transfer'):self.add(c,'Not a purchase',2,kind)
            self.add(c,'Uncategorized merchant',None)
            self.assertIsNone(app.category(c,'Not a purchase'))
            self.assertIsNone(app.category(c,'Uncategorized merchant'))
    def test_bulk_assignment_rename_reassignment_and_removal(self):
        with app.db() as c:
            key=self.add(c,'Example merchant',None)
        with app.db() as c:app.categorize_transactions(c,{'ids':[key],'category_id':2})
        with app.db() as c:
            self.assertEqual(app.category(c,'example merchant'),2)
            c.execute("UPDATE categories SET name='Coffee' WHERE id=2")
            self.assertEqual(app.category(c,'Example merchant'),2)
            c.execute('UPDATE transactions SET category_id=3 WHERE category_id=2')
            c.execute('DELETE FROM categories WHERE id=2')
            self.assertEqual(app.category(c,'Example merchant'),3)
            c.execute('UPDATE transactions SET category_id=NULL WHERE id=?',(key,))
            self.assertIsNone(app.category(c,'Example merchant'))
    def test_preview_suggests_negative_only_and_respects_override(self):
        with app.db() as c:self.add(c,'Example merchant',2)
        with app.db() as c:
            preview=app.preview(c,{'account_id':1,'text':'Date,Payee,Amount\n2026-02-01,EXAMPLE MERCHANT,-12\n2026-02-02,Example merchant,10\n','mapping':{'date':'0','payee':'1','amount':'2'}})
            self.assertEqual(preview['rows'][0]['tx']['category_id'],2)
            self.assertIsNone(preview['rows'][1]['tx']['category_id'])
        with app.db() as c:
            app.commit_import(c,{'token':preview['token'],'selected':[{'index':0,'category_id':3}]})
        with app.db() as c:self.assertEqual(c.execute("SELECT category_id FROM transactions WHERE date='2026-02-01'").fetchone()[0],3)
    def test_history_is_scoped_to_user_database(self):
        with app.db() as c:self.add(c,'Private merchant',2)
        token=app.CURRENT_USER.set(999)
        try:
            app.init()
            with app.db() as c:self.assertIsNone(app.category(c,'Private merchant'))
        finally:app.CURRENT_USER.reset(token)
        with app.db() as c:self.assertEqual(app.category(c,'Private merchant'),2)
