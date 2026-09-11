"""Exercise native Save As dialogs in the isolated Windows UI smoke test."""
import ctypes
from ctypes import wintypes
import os
import time


def check_export(window, folder):
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = wintypes.LPARAM
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumChildWindows.argtypes = [wintypes.HWND, callback_type, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]

    def find_dialog():
        matches = []
        def visit(handle, _):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
            name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(handle, name, 256)
            if pid.value == os.getpid() and name.value == '#32770' and user32.IsWindowVisible(handle):
                matches.append(handle)
            return True
        user32.EnumWindows(callback_type(visit), 0)
        return matches[0] if matches else None

    def wait_for(check):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            result = check()
            if result: return result
            time.sleep(0.1)
        raise RuntimeError('Native CSV export check timed out.')

    def click_export():
        # A real mouse click supplies WebView2's user activation for repeat downloads.
        rect = window.evaluate_js("(() => {const b=document.querySelector('#export');b.scrollIntoView();const r=b.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()")
        point = wintypes.POINT(round(rect['x']), round(rect['y']))
        handle = window.native.Handle.ToInt64()
        user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow(handle)
        user32.ClientToScreen(handle, ctypes.byref(point))
        user32.SetCursorPos(point.x, point.y)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        user32.mouse_event(0x0004, 0, 0, 0, 0)

    window.resize(1000, 650)
    window.move(0, 0)
    time.sleep(0.5)
    click_export()
    dialog = wait_for(find_dialog)
    user32.PostMessageW(dialog, 0x0111, 2, 0)  # Cancel
    wait_for(lambda: not find_dialog())

    click_export()
    dialog = wait_for(find_dialog)
    edits = []
    def visit_edit(handle, _):
        name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(handle, name, 256)
        if name.value == 'Edit' and user32.IsWindowVisible(handle):
            edits.append(handle)
        return True
    user32.EnumChildWindows(dialog, callback_type(visit_edit), 0)
    if len(edits) != 1:
        raise RuntimeError('Could not identify the Save As filename field.')
    destination = folder / 'export-check.csv'
    # Type into the dialog as a user would so its filename-change handlers run.
    from System.Windows.Forms import SendKeys
    bounds = wintypes.RECT()
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect(edits[0], ctypes.byref(bounds))
    user32.SetForegroundWindow(dialog)
    user32.SetCursorPos((bounds.left + bounds.right) // 2, (bounds.top + bounds.bottom) // 2)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    SendKeys.SendWait('^a')
    SendKeys.SendWait(''.join('{'+c+'}' if c in '+^%~(){}[]' else c for c in str(destination)))
    SendKeys.SendWait('{ENTER}')
    wait_for(lambda: not find_dialog())
    try:
        wait_for(lambda: destination.exists() and destination.stat().st_size > 0)
    except RuntimeError as error:
        raise RuntimeError('CSV save failed: '+str(window.evaluate_js("document.querySelector('#notice').textContent"))) from error
    if not destination.read_text(encoding='utf-8-sig').startswith('Date,Account,Payee,Amount,'):
        raise RuntimeError('The downloaded file is not the transaction CSV.')
