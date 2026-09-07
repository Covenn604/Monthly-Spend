"""Persistent local accounts for Spearmint; server administrators remain trusted."""
import hashlib
import hmac
import re
import secrets
import sqlite3
from contextlib import contextmanager

@contextmanager
def connection(data_dir):
    c=sqlite3.connect(data_dir/'users.sqlite3',timeout=15)
    c.row_factory=sqlite3.Row
    try:
        with c: yield c
    finally: c.close()

def username(value):
    value=str(value or '').strip().lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,39}',value):
        raise ValueError('Username must be 3–40 characters: letters, numbers, dots, underscores or hyphens.')
    return value

def password_hash(password,salt=None):
    if not isinstance(password,str) or not 12<=len(password)<=1024:
        raise ValueError('Password must be between 12 and 1,024 characters.')
    salt=salt or secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex()
    return salt+':'+digest

def verify(password,encoded):
    try:
        salt,_=encoded.split(':',1)
        return hmac.compare_digest(password_hash(password,salt),encoded)
    except (ValueError,TypeError): return False

def public(row):
    return {k:row[k] for k in ('id','username','is_admin','enabled','version')}

def init(data_dir,password,admin_username='admin'):
    data_dir.mkdir(parents=True,exist_ok=True)
    with connection(data_dir) as c:
        c.execute('CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,is_admin INTEGER NOT NULL DEFAULT 0,enabled INTEGER NOT NULL DEFAULT 1,version INTEGER NOT NULL DEFAULT 1)')
        if not c.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            c.execute('INSERT INTO users(id,username,password_hash,is_admin) VALUES (1,?,?,1)',(username(admin_username),password_hash(password)))

def authenticate(data_dir,name,password):
    with connection(data_dir) as c:
        row=c.execute('SELECT * FROM users WHERE username=?',(str(name or '').strip().lower(),)).fetchone()
    encoded=row['password_hash'] if row else '0'*32+':'+'0'*64
    valid=verify(password,encoded)
    return public(row) if row and row['enabled'] and valid else None

def get(data_dir,key):
    with connection(data_dir) as c: row=c.execute('SELECT * FROM users WHERE id=?',(key,)).fetchone()
    return public(row) if row else None

def list_users(data_dir):
    with connection(data_dir) as c: return [public(r) for r in c.execute('SELECT * FROM users ORDER BY id')]

def create(data_dir,name,password):
    name=username(name)
    encoded=password_hash(password)
    with connection(data_dir) as c:
        key=c.execute('INSERT INTO users(username,password_hash) VALUES (?,?)',(name,encoded)).lastrowid
    return get(data_dir,key)

def change_password(data_dir,key,current,new):
    encoded=password_hash(new)
    with connection(data_dir) as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM users WHERE id=?',(key,)).fetchone()
        if not row or not row['enabled'] or not verify(current,row['password_hash']):
            raise ValueError('Current password is incorrect.')
        c.execute('UPDATE users SET password_hash=?,version=version+1 WHERE id=?',(encoded,key))

def manage(data_dir,key,action,password=None):
    if action not in ('disable','enable','reset_password'):
        raise ValueError('Unknown user action.')
    encoded=password_hash(password) if action=='reset_password' else None
    with connection(data_dir) as c:
        row=c.execute('SELECT * FROM users WHERE id=?',(key,)).fetchone()
        if not row: raise ValueError('User not found.')
        if row['is_admin']: raise ValueError('Use your own password settings to manage the administrator.')
        if action=='reset_password': c.execute('UPDATE users SET password_hash=?,version=version+1 WHERE id=?',(encoded,key))
        else: c.execute('UPDATE users SET enabled=?,version=version+1 WHERE id=?',(int(action=='enable'),key))
