"""Opt-in Windows updates from this project's published GitHub Releases."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from urllib.parse import urlsplit, unquote
from urllib.request import Request, urlopen

API = 'https://api.github.com/repos/Covenn604/spearmint/releases/latest'
ASSET_PREFIX = '/Covenn604/spearmint/releases/download/'
MAX_INSTALLER = 250 * 1024 * 1024
SNOOZE_SECONDS = 24 * 60 * 60


def version_tuple(value):
    match = re.fullmatch(r'(?:Spearmint-)?v?(\d+)\.(\d+)\.(\d+)', str(value), re.I)
    return tuple(map(int, match.groups())) if match else None


def release_installer(release, current):
    version = version_tuple(release.get('tag_name'))
    if release.get('draft') or release.get('prerelease') or not version or version <= version_tuple(current):
        return None
    name = 'Spearmint-' + '.'.join(map(str, version)) + '-Windows-x64-Setup.exe'
    for asset in release.get('assets', []):
        if asset.get('name') != name or asset.get('state') != 'uploaded':
            continue
        url = asset.get('browser_download_url', '')
        parsed = urlsplit(url)
        expected = ASSET_PREFIX + release['tag_name'] + '/' + name
        digest = asset.get('digest', '')
        size = asset.get('size')
        if (parsed.scheme != 'https' or parsed.netloc != 'github.com' or unquote(parsed.path) != expected
                or parsed.query or parsed.fragment or not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', digest or '')
                or type(size) is not int or not 0 < size <= MAX_INSTALLER):
            raise ValueError('The release installer has incomplete or invalid verification details.')
        return {'version': '.'.join(map(str, version)), 'name': name, 'url': url,
                'sha256': digest[7:].lower(), 'size': size}
    raise ValueError('The newer release does not yet have a Windows installer attached.')


def open_download(url):
    response = urlopen(Request(url, headers={'User-Agent': 'Spearmint-Windows-Updater',
        'Accept': 'application/vnd.github+json' if url == API else 'application/octet-stream',
        'X-GitHub-Api-Version': '2022-11-28'}), timeout=20)
    final = urlsplit(response.geturl())
    if final.scheme != 'https' or final.hostname not in {
        'api.github.com', 'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'
    }:
        response.close()
        raise ValueError('GitHub returned an unexpected download location.')
    return response


class UpdateManager:
    def __init__(self, folder, version, executable, opener=open_download, clock=time.time):
        self.folder = Path(folder)
        self.version = version
        self.executable = Path(executable)
        self.opener = opener
        self.clock = clock
        self.window = None
        self.pending = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._started = False
        self._snooze = 0
        try:
            self._snooze = float(json.loads((self.folder/'update-state.json').read_text())['snooze_until'])
        except (OSError, ValueError, TypeError, KeyError):
            pass

    def notify(self, message, busy=False):
        if self.window and not self._stop.is_set():
            self.window.evaluate_js('window.dispatchEvent(new CustomEvent("spearmint-update-status",{detail:' + json.dumps({'message': message, 'busy': busy}) + '}))')

    def decline(self):
        self._snooze = self.clock() + SNOOZE_SECONDS
        self.folder.mkdir(parents=True, exist_ok=True)
        temporary = self.folder/'update-state.tmp'
        temporary.write_text(json.dumps({'snooze_until': self._snooze}), encoding='utf-8')
        os.replace(temporary, self.folder/'update-state.json')

    def download(self, asset):
        self.folder.mkdir(parents=True, exist_ok=True)
        partial = self.folder/(asset['name']+'.part')
        target = self.folder/asset['name']
        digest = hashlib.sha256()
        size = 0
        try:
            with self.opener(asset['url']) as response, partial.open('wb') as output:
                while chunk := response.read(256 * 1024):
                    if self._stop.is_set(): raise InterruptedError('Update canceled because Spearmint closed.')
                    size += len(chunk)
                    if size > asset['size'] or size > MAX_INSTALLER: raise ValueError('Installer size did not match the release.')
                    digest.update(chunk)
                    output.write(chunk)
            if size != asset['size'] or digest.hexdigest() != asset['sha256']:
                raise ValueError('Installer verification failed. No update was installed.')
            os.replace(partial, target)
            return target
        finally:
            partial.unlink(missing_ok=True)

    def check(self, manual=False):
        if self._stop.is_set() or self.pending or not self._lock.acquire(blocking=False): return
        accepted = False
        try:
            if not manual and self.clock() < self._snooze: return
            if manual: self.notify('Checking for Windows updates…')
            with self.opener(API) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024: raise ValueError('Release response was too large.')
                release = json.loads(raw)
            asset = release_installer(release, self.version)
            if self._stop.is_set(): return
            if not asset:
                if manual: self.notify('Spearmint is up to date (v'+self.version+').')
                return
            accepted = self.window.create_confirmation_dialog('Spearmint update available',
                'Spearmint '+asset['version']+' is available. You are using '+self.version+'.\n\n'
                'Install this update now? Spearmint will download and verify the installer, close, '
                'and reopen after installation. Your saved data will be kept. Any unsaved form changes will be lost.\n\n'
                'Declining silences automatic update prompts for 24 hours.')
            if self._stop.is_set(): return
            if not accepted:
                self.decline()
                self.notify('Update postponed. Automatic prompts are silenced for 24 hours.')
                return
            self.notify('Downloading and verifying Spearmint '+asset['version']+'… Please wait.', busy=True)
            installer = self.download(asset)
            if self._stop.is_set(): return
            self.pending = (installer, asset['sha256'])
            self.notify('Update verified. Closing Spearmint to install…', busy=True)
            self.window.destroy()
        except Exception as error:
            if manual or accepted:
                self.notify('Could not update Spearmint: '+str(error)+'. You can retry with Check for updates.')
        finally:
            self._lock.release()

    def request_check(self):
        threading.Thread(target=self.check, kwargs={'manual': True}, daemon=True).start()
        return {'ok': True}

    def start(self, window):
        if self._started: return
        self._started = True
        self.window = window
        def loop():
            while not self._stop.is_set():
                self.check()
                if self._stop.wait(3600): break
        threading.Thread(target=loop, daemon=True).start()

    def stop(self):
        self._stop.set()

    def launch_pending(self):
        """Called only after the local server and single-instance lock are closed."""
        if not self.pending: return
        installer, digest = self.pending
        # Recheck staged bytes immediately before handing them to Windows.
        if hashlib.sha256(installer.read_bytes()).hexdigest() != digest:
            raise ValueError('The staged installer changed. Download the update again.')
        subprocess.Popen([str(installer), '/SP-', '/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NORESTARTAPPLICATIONS',
                          '/CLOSEAPPLICATIONS', '/SPEARMINTUPDATE=1',
                          '/DIR='+str(self.executable.parent), '/LOG='+str(self.folder/'install.log')],
                         cwd=str(self.folder), close_fds=True)
