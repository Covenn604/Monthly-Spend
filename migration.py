"""Preserve existing SQLite records while adopting the Spearmint filename."""
import sqlite3
from pathlib import Path


def financial_database(folder):
    folder = Path(folder)
    old, new = folder/'monthly-spend.sqlite3', folder/'spearmint.sqlite3'
    if old.exists() and new.exists():
        raise ValueError('Both monthly-spend.sqlite3 and spearmint.sqlite3 exist. Stop Spearmint and resolve the duplicate databases from a backup before restarting.')
    if old.exists():
        # Recover and checkpoint journals using SQLite, never rename a live WAL separately.
        con = sqlite3.connect(old, timeout=15)
        try:
            checkpoint = con.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
            if checkpoint[0]: raise ValueError('Database is busy. Stop other Spearmint instances before upgrading.')
            con.execute('PRAGMA journal_mode=DELETE')
        finally:
            con.close()
        old.rename(new)
    elif any((folder/('monthly-spend.sqlite3'+suffix)).exists() for suffix in ('-wal','-journal')):
        raise ValueError('Legacy SQLite journal found without its database. Restore a complete backup before starting.')
    return new


def migrate_all(data):
    financial_database(data)
    users = data/'users'
    if users.exists():
        for folder in users.iterdir():
            if folder.is_dir() and folder.name.isdigit(): financial_database(folder)
