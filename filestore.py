"""Civora AI v3.7.0 - uploaded drawings that survive server restarts.

SQLite mode: files live only in data/uploads (as before).
PostgreSQL mode: every file is ALSO stored in the database (table civora_files). The local
uploads folder is just a cache: at start-up missing files are downloaded again, and
ensure() fetches a single file on demand. So a Render restart never loses a drawing.
"""
import time
from pathlib import Path

import dbcompat


def save(files_dir, stored_name, data):
    path = Path(files_dir) / Path(stored_name).name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if dbcompat.is_postgres():
        with dbcompat.pg_session() as c:
            c.execute('INSERT INTO civora_files(stored_name,data,created) VALUES(?,?,?) '
                      'ON CONFLICT(stored_name) DO UPDATE SET data=excluded.data', (path.name, bytes(data), int(time.time())))
    return path


def delete(files_dir, stored_name):
    """v3.8.0: the file is KEPT - its database row went to the Recycle Bin and may be restored.
    It is removed only by purge() when the site owner empties that Recycle Bin entry."""
    return Path(files_dir) / Path(stored_name).name


def purge(files_dir, stored_name):
    path = Path(files_dir) / Path(stored_name).name
    path.unlink(missing_ok=True)
    if dbcompat.is_postgres():
        with dbcompat.pg_session() as c:
            c.execute('DELETE FROM civora_files WHERE stored_name=?', (path.name,))


def ensure(files_dir, stored_name):
    """Path to the file, downloading it from the database when the local copy is missing."""
    path = Path(files_dir) / Path(stored_name).name
    if not path.is_file() and dbcompat.is_postgres():
        with dbcompat.pg_session() as c:
            r = c.execute('SELECT data FROM civora_files WHERE stored_name=?', (path.name,)).fetchone()
        if r:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(bytes(r['data']))
    return path


def sync_down(files_dir):
    """Start-up: bring back every stored file that is not in the local cache. Returns the count."""
    if not dbcompat.is_postgres():
        return 0
    folder = Path(files_dir)
    folder.mkdir(parents=True, exist_ok=True)
    have = {p.name for p in folder.iterdir() if p.is_file()}
    with dbcompat.pg_session() as c:
        names = [r['stored_name'] for r in c.execute('SELECT stored_name FROM civora_files').fetchall()]
    n = 0
    for name in names:
        if name not in have:
            ensure(folder, name)
            n += 1
    return n


def sync_up(files_dir):
    """Copy local files that are not yet in the database (used once by the migration script)."""
    if not dbcompat.is_postgres():
        return 0
    folder = Path(files_dir)
    with dbcompat.pg_session() as c:
        have = {r['stored_name'] for r in c.execute('SELECT stored_name FROM civora_files').fetchall()}
    n = 0
    for p in sorted(folder.glob('*')):
        if p.is_file() and p.name not in have:
            save(folder, p.name, p.read_bytes())
            n += 1
    return n
