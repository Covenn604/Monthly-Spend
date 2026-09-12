import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from desktop.updater import UpdateManager, release_installer, version_tuple, API, SNOOZE_SECONDS

DATA = b'MZ synthetic installer bytes'
DIGEST = hashlib.sha256(DATA).hexdigest()


def release(tag='Spearmint-v0.5.5'):
    name='Spearmint-0.5.5-Windows-x64-Setup.exe'
    return {'tag_name':tag,'draft':False,'prerelease':False,'assets':[{'name':name,'state':'uploaded',
        'browser_download_url':'https://github.com/Covenn604/spearmint/releases/download/'+tag+'/'+name,
        'digest':'sha256:'+DIGEST,'size':len(DATA)}]}


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.now=1000.;self.metadata=release();self.bytes=DATA;self.requests=[]
        self.manager=self.new_manager()
    def tearDown(self): self.temp.cleanup()
    def open(self,url):
        self.requests.append(url)
        return io.BytesIO(json.dumps(self.metadata).encode() if url==API else self.bytes)
    def new_manager(self):
        m=UpdateManager(self.root/'updates','0.5.4',self.root/'Programs'/'Spearmint.exe',opener=self.open,clock=lambda:self.now)
        m.window=Mock();m.window.create_confirmation_dialog.return_value=False
        return m
    def test_versions_stable_only_and_expected_installer(self):
        for tag in ['0.5.5','v0.5.5','Spearmint-v0.5.5']:
            self.assertEqual(version_tuple(tag),(0,5,5));self.assertIsNotNone(release_installer(release(tag),'0.5.4'))
        for tag in ['0.5.4','0.4.99','0.5.5-beta','not a version']:
            r=release();r['tag_name']=tag;self.assertIsNone(release_installer(r,'0.5.4'))
        for flag in ['draft','prerelease']:
            r=release();r[flag]=True;self.assertIsNone(release_installer(r,'0.5.4'))
        self.assertEqual(version_tuple('0.10.0'),(0,10,0))
    def test_snooze_persists_across_restart_and_silences_newer_releases(self):
        self.manager.check();self.assertEqual(self.requests,[API])
        reopened=self.new_manager();self.requests.clear()
        self.now+=SNOOZE_SECONDS-1;reopened.check();self.assertEqual(self.requests,[])
        self.now+=1;reopened.check();self.assertEqual(self.requests,[API])
    def test_manual_check_bypasses_snooze_without_installing_without_consent(self):
        self.manager.decline();self.manager.check(manual=True)
        self.assertEqual(self.requests,[API]);self.manager.window.create_confirmation_dialog.assert_called_once()
        self.assertIsNone(self.manager.pending);self.manager.window.destroy.assert_not_called()
    def test_verified_download_staged_then_launched_without_shell(self):
        self.manager.window.create_confirmation_dialog.return_value=True
        self.manager.check()
        installer,digest=self.manager.pending
        self.assertEqual(installer.read_bytes(),DATA);self.assertEqual(digest,DIGEST)
        self.manager.window.destroy.assert_called_once()
        with patch('desktop.updater.subprocess.Popen') as launch:
            self.manager.launch_pending()
            args=launch.call_args.args[0]
            self.assertEqual(args[0],str(installer));self.assertIn('/SPEARMINTUPDATE=1',args)
            self.assertIn('/DIR='+str(self.manager.executable.parent),args)
            self.assertNotIn('shell',launch.call_args.kwargs)
    def test_invalid_metadata_never_downloaded(self):
        for field,value in [('digest',None),('size',0),('size',999999999),('browser_download_url','https://evil.example/update.exe')]:
            r=release();r['assets'][0][field]=value
            with self.assertRaises(ValueError): release_installer(r,'0.5.4')
        with self.assertRaises(ValueError): release_installer({**release(),'assets':[]},'0.5.4')
    def test_bad_hash_or_truncated_download_keeps_app_open(self):
        for data in [b'bad',b'x'*len(DATA),DATA+b'extra']:
            self.bytes=data;self.manager.window.create_confirmation_dialog.return_value=True
            self.manager.check();self.assertIsNone(self.manager.pending)
            self.manager.window.destroy.assert_not_called()
            self.assertEqual(list((self.root/'updates').glob('*.part')),[])
            self.assertEqual(list((self.root/'updates').glob('*.exe')),[])
    def test_staged_tampering_rejected_before_launch(self):
        self.manager.window.create_confirmation_dialog.return_value=True;self.manager.check()
        self.manager.pending[0].write_bytes(b'tampered')
        with patch('desktop.updater.subprocess.Popen') as launch:
            with self.assertRaises(ValueError): self.manager.launch_pending()
            launch.assert_not_called()
    def test_network_failure_stopped_app_and_concurrent_check(self):
        self.manager.opener=Mock(side_effect=OSError('offline'))
        self.manager.check();self.manager.window.destroy.assert_not_called()
        self.manager.window.evaluate_js.assert_not_called()
        self.manager.check(manual=True);self.manager.window.evaluate_js.assert_called()
        self.manager.opener.reset_mock();self.manager._lock.acquire()
        self.manager.check(manual=True);self.manager.opener.assert_not_called();self.manager._lock.release()
        self.manager.stop();self.manager.check(manual=True);self.manager.opener.assert_not_called()
    def test_corrupt_state_and_cancel_during_download(self):
        self.manager.folder.mkdir();(self.manager.folder/'update-state.json').write_text('bad json')
        m=self.new_manager();m.stop()
        with self.assertRaises(InterruptedError): m.download(release_installer(release(),'0.5.4'))
        self.assertEqual(list(m.folder.glob('*.part')),[])
