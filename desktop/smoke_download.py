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

    window.evaluate_js("document.querySelector('#export').click()")
    dialog = wait_for(find_dialog)
    user32.PostMessageW(dialog, 0x0111, 2, 0)  # Cancel
    wait_for(lambda: not find_dialog())

    window.evaluate_js("document.querySelector('#export').click()")
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
    value = ctypes.create_unicode_buffer(str(destination))
    user32.SendMessageW(edits[0], 0x000C, 0, ctypes.cast(value, ctypes.c_void_p).value)  # WM_SETTEXT
    user32.PostMessageW(dialog, 0x0111, 1, 0)  # Save
    wait_for(lambda: not find_dialog())
    wait_for(lambda: destination.exists() and destination.stat().st_size > 0)
    if not destination.read_text(encoding='utf-8-sig').startswith('Date,Account,Payee,Amount,'):
        raise RuntimeError('The downloaded file is not the transaction CSV.')
