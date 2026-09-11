"""Windows entry point. The Docker entry point remains app.py."""
import argparse
import contextlib
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import auth

VERSION = '0.5.1'

def icon_path():
    return app.ROOT/'static'/'spearmint.ico' if getattr(sys,'frozen',False) else Path(__file__).parent/'spearmint.ico'

def window_icon(window):
    # WinForms uses the executable icon; explicitly set the window icon too.
    def apply():
        from System.Drawing import Icon
        window.native.Icon = Icon(str(icon_path()))
    window.events.before_show += apply



def data_path():
    return Path(os.environ['LOCALAPPDATA']) / 'Spearmint' / 'data'


@contextlib.contextmanager
def single_instance(folder):
    """OS-held file lock is released even if the process crashes."""
    import msvcrt
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'desktop.lock').open('a+b') as handle:
        handle.seek(0)
        if not handle.read(1):
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise RuntimeError('Spearmint is already running. Switch to its existing window.') from error
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def needs_setup(folder):
    database = folder / 'users.sqlite3'
    if not database.exists():
        return True
    with auth.connection(folder) as c:
        return not c.execute('SELECT 1 FROM users LIMIT 1').fetchone()


def setup_account(folder):
    import tkinter as tk
    from tkinter import ttk, messagebox
    window = tk.Tk()
    window.title('Welcome to Spearmint')
    if icon_path().exists(): window.iconbitmap(str(icon_path()))
    window.resizable(False, False)
    frame = ttk.Frame(window, padding=24)
    frame.pack()
    ttk.Label(frame, text='Set up your private spending tracker', font=('Segoe UI', 15, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='Create your initial administrator login. On first sign-in you will choose your password and recovery answers.\nYour finances will be saved on this PC.', wraplength=440).pack(anchor='w', pady=(10, 18))
    fields = {}
    for key, label in [('username', 'Username'), ('password', 'Password (at least 12 characters)'), ('confirm', 'Confirm password')]:
        ttk.Label(frame, text=label).pack(anchor='w')
        entry = ttk.Entry(frame, width=48, show='' if key == 'username' else '*')
        entry.pack(fill='x', pady=(3, 12))
        fields[key] = entry
    fields['username'].insert(0, 'admin')
    completed = False

    def create():
        nonlocal completed
        try:
            username = auth.username(fields['username'].get())
            password = fields['password'].get()
            if password != fields['confirm'].get():
                raise ValueError('The passwords do not match.')
            auth.password_hash(password)  # Validate before writing any setup data.
            auth.init(folder, password, username)
            app.DATA = folder
            app.init()
        except (ValueError, OSError) as error:
            messagebox.showerror('Setup could not finish', str(error), parent=window)
            return
        completed = True
        window.destroy()

    ttk.Button(frame, text='Create account and open Spearmint', command=create).pack(fill='x', pady=(5, 0))
    window.mainloop()
    return completed


@contextlib.contextmanager
def local_server(folder):
    app.DATA = folder
    # Desktop always uses loopback HTTP, regardless of Docker shell settings.
    os.environ['COOKIE_SECURE'] = 'false'
    app.migration.migrate_all(folder)
    if needs_setup(folder): raise RuntimeError('Create the administrator account before starting Spearmint.')
    auth.init(folder,'unused-existing-account-password')
    app.init()
    server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        with app.LOCK:
            app.SESSIONS.clear()


def smoke_test():
    """Exercise the bundled server and assets without touching real desktop data."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        auth.init(folder, 'smoke-only-password-123', 'admin')
        auth.finish_setup(folder,1,1,'smoke-only-password-123',['test answer one','test city','test friend'])
        with local_server(folder) as server:
            client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
            for path in ['/', '/app.js', '/csv-reader.js', '/style.css', '/spearmint-logo.png', '/health']:
                client.request('GET', path)
                response = client.getresponse()
                assert response.status == 200, path
                assert response.read(), path
            client.request('POST', '/api/login', json.dumps({'username': 'admin', 'password': 'smoke-only-password-123'}), {'X-Requested-With': 'MonthlySpend'})
            response = client.getresponse()
            assert response.status == 200
            cookie = response.getheader('Set-Cookie').split(';')[0]
            response.read()
            client.request('GET', '/api/state', headers={'Cookie': cookie})
            response = client.getresponse()
            assert response.status == 200
            assert json.loads(response.read())['user']['username'] == 'admin'
            client.close()
    return 0


def ui_smoke_test():
    import webview
    webview.settings['ALLOW_DOWNLOADS'] = True
    from threading import Event
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        auth.init(folder, 'smoke-only-password-123', 'admin')
        with local_server(folder) as server:
            window = webview.create_window('Spearmint UI check', f'http://127.0.0.1:{server.server_port}')
            window_icon(window)
            loaded = Event()
            outcome = []
            window.events.loaded += loaded.set
            def verify_window():
                try:
                    if not loaded.wait(45):
                        raise RuntimeError('Desktop page did not load.')
                    if window.evaluate_js('document.title') != 'Spearmint':
                        raise RuntimeError('Desktop title did not match.')
                    if not window.evaluate_js("!!document.querySelector('#login-form')"):
                        raise RuntimeError('Login form was not rendered.')
                    import time
                    def wait_for(script):
                        deadline=time.monotonic()+45
                        while time.monotonic()<deadline:
                            if window.evaluate_js(script): return
                            time.sleep(0.2)
                        raise RuntimeError('Desktop workflow timed out: '+script)
                    window.evaluate_js("document.querySelector('#login-form').elements.username.value='admin';document.querySelector('#login-form').elements.password.value='smoke-only-password-123';document.querySelector('#login-form').requestSubmit();")
                    wait_for("!document.querySelector('#account-setup').hidden")
                    window.evaluate_js("const f=document.querySelector('#setup-form');f.elements.password.value='chosen-password-123';f.elements.confirm.value='chosen-password-123';['Middle','City','Friend'].forEach((v,i)=>f.elements['answer'+i].value=v);f.requestSubmit();")
                    wait_for("!document.querySelector('#login').hidden")
                    window.evaluate_js("document.querySelector('#forgot-password').click();document.querySelector('#recovery-start').elements.username.value='admin';document.querySelector('#recovery-start').requestSubmit();")
                    wait_for("!document.querySelector('#recovery-verify').hidden")
                    window.evaluate_js("document.querySelectorAll('#recovery-questions input').forEach(e=>e.value=['MIDDLE','CITY','FRIEND'][Number(e.name)]);document.querySelector('#recovery-verify').requestSubmit();")
                    wait_for("!document.querySelector('#recovery-reset').hidden")
                    window.evaluate_js("const f=document.querySelector('#recovery-reset');f.elements.password.value='recovered-password-123';f.elements.confirm.value='recovered-password-123';f.requestSubmit();")
                    wait_for("!document.querySelector('#login').hidden")
                    window.evaluate_js("document.querySelector('#login-form').elements.username.value='admin';document.querySelector('#login-form').elements.password.value='recovered-password-123';document.querySelector('#login-form').requestSubmit();")
                    wait_for("!document.querySelector('#shell').hidden")
                    # Check the filter label at desktop and narrow window widths.
                    window.evaluate_js("setView('transactions');document.querySelector('#transaction-scope').value='all';document.querySelector('#transaction-scope').dispatchEvent(new Event('change'));")
                    wait_for("!document.querySelector('#show-completed-label').hidden")
                    for width in (1280, 780):
                        window.resize(width, 900)
                        time.sleep(0.3)
                        if not window.evaluate_js("(() => {const label=document.querySelector('#show-completed-label'),box=label.querySelector('input').getBoundingClientRect(),text=label.querySelector('span').getBoundingClientRect(),count=document.querySelector('#tx-count').getBoundingClientRect();return box.width<=24 && text.left>=box.right && (count.left>=text.right || count.top>=text.bottom);})()"):
                            raise RuntimeError('Transaction filter controls overlap.')
                    from desktop.smoke_download import check_export
                    check_export(window, folder)
                    outcome.append(True)
                finally:
                    window.destroy()
            webview.start(verify_window, gui='edgechromium', private_mode=True)
            if not outcome: raise RuntimeError('WebView2 UI smoke test failed.')
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--ui-smoke-test', action='store_true')
    args = parser.parse_args()
    if args.ui_smoke_test:
        return ui_smoke_test()
    if args.smoke_test:
        return smoke_test()
    if sys.platform != 'win32':
        raise RuntimeError('The desktop edition currently supports Windows 11 only.')
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Spearmint.Desktop')
    folder = data_path()
    with single_instance(folder.parent):
        if needs_setup(folder) and not setup_account(folder):
            return 0
        import webview
        # WebView2 opens a native Save As dialog for transaction downloads.
        webview.settings['ALLOW_DOWNLOADS'] = True
        with local_server(folder) as server:
            window = webview.create_window('Spearmint', f'http://127.0.0.1:{server.server_port}', width=1280, height=900, min_size=(780, 600))
            window_icon(window)
            # Ephemeral browser session; the financial data remains in SQLite.
            webview.start(gui='edgechromium', private_mode=True)
    return 0


if __name__ == '__main__':
    if ('--ui-smoke-test' in sys.argv or '--smoke-test' in sys.argv) and sys.stderr is None:
        sys.stdout = sys.stderr = open('spearmint-smoke.log', 'w', encoding='utf-8', buffering=1)
    try:
        sys.exit(main())
    except Exception:
        import traceback
        if '--smoke-test' in sys.argv or '--ui-smoke-test' in sys.argv:
            traceback.print_exc()
            sys.exit(1)
        from tkinter import Tk, messagebox
        root = Tk()
        root.withdraw()
        if icon_path().exists(): root.iconbitmap(str(icon_path()))
        messagebox.showerror('Spearmint could not start', 'Check that Microsoft Edge WebView2 Runtime is installed and your Spearmint data folder is writable.\n\n' + str(sys.exc_info()[1]))
        root.destroy()
        sys.exit(1)
