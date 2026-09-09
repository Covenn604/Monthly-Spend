from test_app import DatabaseFixture
import app

class CsvFormatTests(DatabaseFixture):
    def preview(self,text,**options):
        with app.db() as c:
            return app.preview(c,{'account_id':1,'text':text,'mapping':{'date':'0','payee':'1','amount':'2',**options}})
    def test_skip_physical_lines_and_report_source_lines(self):
        text='Export details\n\nDate,Description,Amount,Ignored\n20260115,"Example\nShop",25,anything\n\nnot-a-date,Other,10,anything\n'
        rows,lines=app.parse_csv(text,skip_lines=2,with_lines=True)
        self.assertEqual(lines,[3,4,7])
        p=self.preview(text,skip_lines=2,date_format='compact')
        self.assertEqual(p['rows'][0]['line'],4)
        self.assertEqual(p['rows'][0]['tx']['date'],'2026-01-15')
        self.assertEqual(p['rows'][1]['line'],7)
        self.assertEqual(p['rows'][1]['status'],'invalid')
    def test_formats_and_user_controlled_signs(self):
        for fmt,day in [('dmy_short_month','15 Jan 2026'),('compact','20260115'),('ymd_slash','2026/01/15'),('dmy_dash','15-01-2026'),('mdy_dash','01-15-2026'),('iso','2026-01-15')]:
            for invert in (False,True):
                p=self.preview('Date,Description,Amount\n'+day+',Shop,25\n'+day+',Payment,-10\n',date_format=fmt,invert=invert)
                self.assertEqual([r['tx']['amount'] for r in p['rows']],[-2500,1000] if invert else [2500,-1000])
                self.assertEqual(p['rows'][0]['tx']['date'],'2026-01-15')
        for day in ['2026115','20260230','202601150','abcdefgh']:
            self.assertEqual(self.preview('Date,Description,Amount\n'+day+',Shop,25\n',date_format='compact')['rows'][0]['status'],'invalid')
    def test_unmapped_fields_and_legacy_id_mapping_are_ignored(self):
        p=self.preview('Date,Description,Amount,Extra\n2026-01-15,Shop,-25,same\n2026-01-16,Other,-30,same\n2026-01-17,Third,-40\n',imported_id='3')
        self.assertEqual([r['status'] for r in p['rows']],['new','new','new'])
        self.assertTrue(all(r['tx']['imported_id'] is None for r in p['rows']))
    def test_overlap_uses_content_not_row_ids(self):
        p=self.preview('Date,Description,Amount,Extra\n2026-01-15,Shop,-25,1\n',imported_id='3')
        with app.db() as c:app.commit_import(c,{'token':p['token'],'selected':[{'index':0}]})
        p=self.preview('Date,Description,Amount,Extra\n2026-01-15,Shop,-25,99\n',imported_id='3')
        self.assertEqual(p['rows'][0]['status'],'possible')
    def test_split_amounts_with_preamble_and_blank_lines(self):
        p=self.preview('Notes\nDate,Description,Debit,Credit\n20260115,Shop,25,\n20260116,Deposit,,10\n',skip_lines=1,date_format='compact',mode='split',debit='2',credit='3')
        self.assertEqual([r['tx']['amount'] for r in p['rows']],[-2500,1000])

    def test_text_month_validation_and_split_amounts(self):
        for day in ['31 Feb 2026','07 Xxx 2026']:
            self.assertEqual(self.preview('Date,Description,Amount\n'+day+',Shop,25\n',date_format='dmy_short_month')['rows'][0]['status'],'invalid')
        p=self.preview('Date,Description,Debit,Credit\n07 Sep 2026,Shop,-$25.00,\n08 Sep 2026,Deposit,,$10.00\n',date_format='dmy_short_month',mode='split',debit='2',credit='3')
        self.assertEqual([r['tx']['amount'] for r in p['rows']],[-2500,1000])
        self.assertEqual(p['rows'][0]['tx']['date'],'2026-09-07')

    def test_similar_new_confirmation_and_single_selection(self):
        text='Date,Description,Amount\n2026-01-15,Example Shop,-25\n2026-01-15,example shop,-25\n2026-01-16,Example Shop,-25\n2026-01-15,Other Shop,-25\n2026-01-15,Example Shop,-30\n'
        p=self.preview(text)
        self.assertTrue(all(r['status']=='new' for r in p['rows']))
        self.assertEqual([r.get('similar_group') for r in p['rows']],[0,0,None,None,None])
        with self.assertRaises(app.Invalid):
            with app.db() as c:
                app.commit_import(c,{'token':p['token'],'selected':[{'index':0},{'index':1}],'confirmed_similar_groups':[99]})
        with app.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],0)
            result=app.commit_import(c,{'token':p['token'],'selected':[{'index':1}]})
            self.assertEqual(result['imported'],1)
        again=self.preview(text)
        self.assertEqual([r['status'] for r in again['rows'][:2]],['possible','possible'])
        self.assertTrue(all('similar_group' not in r for r in again['rows']))

    def test_similar_confirmation_does_not_override_changed_ledger(self):
        text='Date,Description,Amount\n2026-01-15,Shop,-25\n2026-01-15,Shop,-25\n'
        p=self.preview(text)
        with app.db() as c:
            app.insert(c,dict(account_id=1,date='2026-01-15',payee='Shop',amount=-2500,kind='expense',category_id=None,note=''))
        with self.assertRaises(app.Invalid):
            with app.db() as c:
                app.commit_import(c,{'token':p['token'],'selected':[{'index':0},{'index':1}],'confirmed_similar_groups':[0]})
        with app.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],1)
