import test_app
import app


class CsvCategoryTests(test_app.DatabaseFixture):
    def preview(self,c,body,mapped=True):
        mapping={'date':'0','payee':'1','amount':'2'}
        if mapped: mapping['category']='3'
        return app.preview(c,{'account_id':1,'mapping':mapping,'text':'Date,Merchant,Amount,Category\n'+body})

    def test_matching_blank_and_unmapped_categories(self):
        with app.db() as c:
            c.execute("INSERT INTO categories(name) VALUES ('Special Coffee')")
            category=c.execute("SELECT id FROM categories WHERE name='Special Coffee'").fetchone()[0]
            c.execute("INSERT INTO rules(contains_text,category_id) VALUES ('Cafe',1)")
            p=self.preview(c,'2026-09-01,Cafe,-10, special   COFFEE \n2026-09-02,Cafe,-11,\n2026-09-03,Cafe,-12,Uncategorized')
            self.assertEqual([r['tx']['category_id'] for r in p['rows']],[category,1,None])
            self.assertEqual(self.preview(c,'2026-09-04,Cafe,-13,Unknown',False)['rows'][0]['tx']['category_id'],1)
            self.assertFalse(any(r['tx'].get('new_category') for r in p['rows']))

    def test_create_only_selected_categories_and_reuse_names(self):
        with app.db() as c:
            before=c.execute('SELECT COUNT(*) FROM categories').fetchone()[0]
            p=self.preview(c,'2026-09-01,A,-10,Riding Gear\n2026-09-02,B,-20,riding gear\n2026-09-03,C,-30,Unselected\n2026-09-04,D,40,Income Only\n2026-09-05,E,-50,Overridden')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM categories').fetchone()[0],before)
        with app.db() as c:
            app.commit_import(c,{'token':p['token'],'selected':[{'index':i,'category_id':'__csv__'} for i in (0,1,3)]+[{'index':4,'category_id':1}]})
        with app.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM categories').fetchone()[0],before+1)
            rows=c.execute('SELECT category_id FROM transactions ORDER BY id').fetchall()
            self.assertEqual(rows[0][0],rows[1][0]);self.assertIsNone(rows[2][0]);self.assertEqual(rows[3][0],1)

    def test_refund_and_category_created_between_preview_and_commit(self):
        with app.db() as c:
            p=self.preview(c,'2026-09-01,A,10,Refund Category')
            key=c.execute("INSERT INTO categories(name) VALUES ('refund category')").lastrowid
        with app.db() as c:
            app.commit_import(c,{'token':p['token'],'selected':[{'index':0,'kind':'refund','category_id':'__csv__'}]})
        with app.db() as c:
            self.assertEqual(c.execute('SELECT category_id FROM transactions').fetchone()[0],key)

    def test_invalid_names_and_rollback(self):
        with app.db() as c:
            p=self.preview(c,'2026-09-01,A,-10,'+'x'*81)
            self.assertEqual(p['rows'][0]['status'],'invalid')
            p=self.preview(c,'2026-09-01,A,-10,Rollback Category\n2026-09-02,B,-20,Other Category')
        with self.assertRaises(app.Invalid):
            with app.db() as c:
                app.commit_import(c,{'token':p['token'],'selected':[{'index':0,'category_id':'__csv__'},{'index':1,'category_id':999999}]})
        with app.db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM categories WHERE name='Rollback Category'").fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],0)
