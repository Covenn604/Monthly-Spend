from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from desktop.export_api import ExportApi


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.api = ExportApi()
        self.window = self.api._window = Mock()
        self.webview = patch.dict(sys.modules, {'webview': SimpleNamespace(FileDialog=SimpleNamespace(SAVE=30))})
        self.webview.start()

    def tearDown(self):
        self.webview.stop()
        self.temp.cleanup()

    def test_cancel_then_save_exact_csv_to_chosen_destination(self):
        target = self.folder / 'Chosen transactions.csv'
        self.window.create_file_dialog.return_value = None
        self.assertEqual(self.api.save_export('unused'), {'saved': False})
        self.assertEqual(list(self.folder.iterdir()), [])
        self.window.create_file_dialog.return_value = (str(target),)
        csv = 'Date,Account,Payee,Amount\r\n2026-09-11,Card,Café,-12.34\r\n'
        result = self.api.save_export(csv)
        self.assertTrue(result['saved'])
        self.assertEqual(target.read_bytes(), csv.encode('utf-8'))
        self.assertEqual(self.window.create_file_dialog.call_args.kwargs['save_filename'], 'spearmint-transactions.csv')

    def test_failed_replace_preserves_existing_file_and_cleans_up(self):
        target = self.folder / 'existing.csv'
        target.write_bytes(b'existing data')
        self.window.create_file_dialog.return_value = str(target)
        with patch('desktop.export_api.os.replace', side_effect=PermissionError('File in use')):
            with self.assertRaises(PermissionError):
                self.api.save_export('replacement')
        self.assertEqual(target.read_bytes(), b'existing data')
        self.assertEqual(list(self.folder.iterdir()), [target])
        self.assertTrue(self.api.save_export('replacement')['saved'])

    def test_second_request_cannot_open_another_dialog(self):
        self.api._lock.acquire()
        try:
            with self.assertRaises(ValueError): self.api.save_export('CSV')
            self.window.create_file_dialog.assert_not_called()
        finally:
            self.api._lock.release()
