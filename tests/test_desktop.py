import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import app
import auth
from desktop.launcher import data_path, needs_setup, local_server


class DesktopTests(unittest.TestCase):
    def test_storage_and_setup_preserve_existing_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {'LOCALAPPDATA': tmp}):
                folder = data_path()
                self.assertEqual(folder, Path(tmp) / 'Spearmint' / 'data')
                self.assertTrue(needs_setup(folder))
                auth.init(folder, 'desktop-password-123', 'owner')
                self.assertFalse(needs_setup(folder))
                self.assertIsNotNone(auth.authenticate(folder, 'owner', 'desktop-password-123'))

    def test_local_server_stops_and_keeps_data(self):
        import http.client
        old_data = app.DATA
        try:
            with tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                auth.init(folder, 'desktop-password-123')
                with local_server(folder) as server:
                    self.assertEqual(server.server_address[0], '127.0.0.1')
                    client = http.client.HTTPConnection(*server.server_address, timeout=5)
                    client.request('GET', '/health')
                    response = client.getresponse()
                    self.assertEqual(response.status, 200)
                    response.read()
                    client.close()
                self.assertEqual(server.fileno(), -1)
                self.assertTrue((folder / 'monthly-spend.sqlite3').exists())
        finally:
            app.DATA = old_data
