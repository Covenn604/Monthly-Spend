import test_app
import app


class BulkDeleteTests(test_app.DatabaseFixture):
    def test_all_kinds_and_linked_counterpart_deleted_balances_recalculate(self):
        with app.db() as c:
            first=self.tx(c,-100)
            income=self.tx(c,200,'income')
            transfer=app.insert(c,dict(account_id=1,date='2026-08-05',payee='Move',amount=-300,kind='transfer',category_id=None,note='',transfer_id='pair'))
            app.insert(c,dict(account_id=2,date='2026-07-05',payee='Move',amount=300,kind='transfer',category_id=None,note='',transfer_id='pair'))
            kept=self.tx(c,-400)
        with app.db() as c:
            result=app.delete_transactions(c,{'ids':[first,income,transfer],'confirmed':True})
            self.assertEqual(result['deleted'],4)
        with app.db() as c:
            self.assertEqual([r[0] for r in c.execute('SELECT id FROM transactions')],[kept])
            self.assertEqual(c.execute('SELECT SUM(amount) FROM transactions WHERE account_id=1').fetchone()[0],-400)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM accounts').fetchone()[0],2)
            self.assertEqual(app.summary(c,'2026-08')['expenses'],400)

    def test_confirmation_invalid_and_stale_selection_never_partially_delete(self):
        with app.db() as c: key=self.tx(c,-100)
        for data in [{'ids':[key]}, {'ids':[key],'confirmed':'true'}, {'ids':[],'confirmed':True}, {'ids':[True],'confirmed':True}, {'ids':[key,key],'confirmed':True}, {'ids':[key,999999],'confirmed':True}]:
            with self.assertRaises(app.Invalid):
                with app.db() as c: app.delete_transactions(c,data)
            with app.db() as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],1)

    def test_large_selection_and_both_transfer_sides_counted_once(self):
        with app.db() as c:
            for i in range(1200): self.tx(c,-100)
            c.execute("UPDATE transactions SET transfer_id='pair',kind='transfer' WHERE id IN (1,2)")
            ids=[r[0] for r in c.execute('SELECT id FROM transactions')]
        with app.db() as c:
            self.assertEqual(app.delete_transactions(c,{'ids':ids,'confirmed':True})['deleted'],1200)
        with app.db() as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],0)
