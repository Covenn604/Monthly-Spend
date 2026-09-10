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

VERSION = '0.4.9'


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
    return not auth.list_users(folder)


def setup_account(folder):
    import tkinter as tk
    from tkinter import ttk, messagebox
    window = tk.Tk()
    window.title('Welcome to Spearmint')
    window.resizable(False, False)
    frame = ttk.Frame(window, padding=24)
    frame.pack()
    ttk.Label(frame, text='Set up your private spending tracker', font=('Segoe UI', 15, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='Create your administrator login. Your finances will be saved on this PC.\nNo Docker or separate server is required.', wraplength=440).pack(anchor='w', pady=(10, 18))
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
    from threading import Event
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        auth.init(folder, 'smoke-only-password-123', 'admin')
        with local_server(folder) as server:
            window = webview.create_window('Spearmint UI check', f'http://127.0.0.1:{server.server_port}')
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
    folder = data_path()
    with single_instance(folder.parent):
        if needs_setup(folder) and not setup_account(folder):
            return 0
        import webview
        with local_server(folder) as server:
            webview.create_window('Spearmint', f'http://127.0.0.1:{server.server_port}', width=1280, height=900, min_size=(780, 600))
            # Ephemeral browser session; the financial data remains in SQLite.
            webview.start(gui='edgechromium', private_mode=True)
    return 0


if __name__ == '__main__':
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
        messagebox.showerror('Spearmint could not start', 'Check that Microsoft Edge WebView2 Runtime is installed and your Spearmint data folder is writable.\n\n' + str(sys.exc_info()[1]))
        root.destroy()
        sys.exit(1)
