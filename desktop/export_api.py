"""Native save operation for CSV bytes fetched by the signed-in web UI."""
from pathlib import Path
import os
import tempfile
import threading


class ExportApi:
    def __init__(self):
        self._window = None
        self._lock = threading.Lock()

    def save_export(self, csv_text):
        import webview
        if not isinstance(csv_text, str):
            raise ValueError('The transaction export is not valid text.')
        if not self._lock.acquire(blocking=False):
            raise ValueError('An export dialog is already open.')
        temporary = None
        try:
            selected = self._window.create_file_dialog(
                webview.FileDialog.SAVE, save_filename='spearmint-transactions.csv',
                file_types=('CSV files (*.csv)',),
            )
            if not selected:
                return {'saved': False}
            destination = Path(selected if isinstance(selected, str) else selected[0])
            # Replace only after the complete CSV has been written successfully.
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='',
                                             dir=destination.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(csv_text)
            os.replace(temporary, destination)
            return {'saved': True, 'filename': destination.name}
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
            self._lock.release()


class DesktopApi(ExportApi):
    def __init__(self, updater):
        super().__init__()
        self._updater = updater

    def check_updates(self):
        return self._updater.request_check()
