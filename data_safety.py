"""Civora v2.4.2 data safety: backups, migration versions, integrity check, restore.

Used two ways:
  * by app.py at start-up  -> one automatic backup per day, before any table changes
  * from CMD (backup.bat / restore.bat):
        python data_safety.py backup            make a manual backup now
        python data_safety.py list              list backups (newest first)
        python data_safety.py check             SQLite integrity check + migration history
        python data_safety.py restore <file>    restore a backup (server must be stopped)

Backups use SQLite's own online-backup API, so they are consistent even if the
database is in use. Restore always backs up the CURRENT database first.
"""
import datetime as _dt
import socket
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
try:                               # v3.6.0: same data folder as the app (CIVORA_DATA_DIR on a persistent disk)
    import persistence_v360 as _pv
    _DATA = _pv.data_dir()
except Exception:
    _DATA = BASE / 'data'
DB = _DATA / 'buildquant.db'
BACKUP_DIR = (_DATA / 'backups' / 'db') if _DATA != BASE / 'data' else (BASE / 'backups' / 'db')
KEEP_AUTO = 365                    # automatic daily backups kept (one year); manual/pre-restore never pruned


def _stamp():
    return _dt.datetime.now().strftime('%Y%m%d_%H%M%S')


def backup_database(db=DB, folder=BACKUP_DIR, reason='manual'):
    """Consistent copy of the database. Returns the backup path (None if no DB yet)."""
    db, folder = Path(db), Path(folder)
    if not db.is_file():
        return None
    folder.mkdir(parents=True, exist_ok=True)
    reason = ''.join(ch for ch in str(reason) if ch.isalnum() or ch in '-_')[:30] or 'manual'
    dest = folder / f'buildquant_{_stamp()}_{reason}.db'
    n = 1
    while dest.exists():                                   # two backups in the same second
        dest = folder / f'buildquant_{_stamp()}_{reason}_{n}.db'; n += 1
    src = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    out = sqlite3.connect(dest)
    try:
        with out:
            src.backup(out)
    finally:
        src.close(); out.close()
    return dest


def list_backups(folder=BACKUP_DIR):
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(folder.glob('buildquant_*.db'), key=lambda p: p.name, reverse=True)


def prune_auto_backups(folder=BACKUP_DIR, keep=KEEP_AUTO):
    autos = [p for p in list_backups(folder) if '_auto' in p.stem]
    removed = []
    for old in autos[keep:]:
        old.unlink(); removed.append(old)
    return removed


def daily_startup_backup(db=DB, folder=BACKUP_DIR, today=None):
    """At most one automatic backup per calendar day. Never raises: a backup problem
    must not stop the app from starting; it is printed instead."""
    try:
        today = today or _dt.date.today().strftime('%Y%m%d')
        if any(p.name.startswith(f'buildquant_{today}_') and '_auto' in p.stem for p in list_backups(folder)):
            return None
        made = backup_database(db, folder, 'auto')
        prune_auto_backups(folder)
        if made:
            print(f'[Civora] Daily database backup: {made}')
        return made
    except Exception as ex:                                # pragma: no cover - reported, not fatal
        print(f'[Civora] WARNING: daily database backup failed: {ex}')
        return None


def ensure_migration_table(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS schema_migrations (
        version TEXT PRIMARY KEY, description TEXT NOT NULL, applied_at TEXT NOT NULL)''')


def record_migration(conn, version, description):
    """Idempotent: a version is recorded once, with the time it was first applied."""
    ensure_migration_table(conn)
    conn.execute('INSERT OR IGNORE INTO schema_migrations(version,description,applied_at) VALUES(?,?,?)',
                 (version, description, _dt.datetime.now().isoformat(timespec='seconds')))


def migration_history(conn):
    ensure_migration_table(conn)
    return conn.execute('SELECT version,description,applied_at FROM schema_migrations ORDER BY applied_at,version').fetchall()


def integrity_check(db=DB):
    conn = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    try:
        result = conn.execute('PRAGMA integrity_check').fetchone()[0]
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    finally:
        conn.close()
    return result, tables


def server_running(port=8000):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(('127.0.0.1', port)) == 0


def restore_database(backup, db=DB, folder=BACKUP_DIR, check_server=True):
    """Replace the live database with a backup. The current database is backed up first."""
    backup, db = Path(backup), Path(db)
    if not backup.is_file():
        raise FileNotFoundError(f'Backup not found: {backup}')
    if check_server and server_running():
        raise RuntimeError('Civora is still running on port 8000. Stop it (Ctrl+C) before restoring.')
    ok, tables = integrity_check(backup)
    if ok != 'ok':
        raise RuntimeError(f'Backup failed the integrity check ({ok}); restore cancelled.')
    if 'projects' not in tables or 'users' not in tables:
        raise RuntimeError('This file does not look like a Civora database; restore cancelled.')
    safety = backup_database(db, folder, 'before-restore')
    src = sqlite3.connect(f'file:{backup}?mode=ro', uri=True)
    out = sqlite3.connect(db)
    try:
        with out:
            src.backup(out)
    finally:
        src.close(); out.close()
    return safety


def _main(argv):
    cmd = argv[1] if len(argv) > 1 else ''
    if cmd == 'backup':
        made = backup_database(reason='manual')
        print(f'Backup created: {made}' if made else f'No database found at {DB}')
        return 0 if made else 1
    if cmd == 'list':
        items = list_backups()
        if not items:
            print('No backups yet.'); return 0
        for i, p in enumerate(items, 1):
            print(f'{i:3}. {p.name}   {p.stat().st_size/1024:,.0f} KB')
        return 0
    if cmd == 'check':
        ok, tables = integrity_check()
        print(f'Integrity: {ok}   Tables: {len(tables)}')
        conn = sqlite3.connect(DB)
        try:
            for v, d, at in migration_history(conn):
                print(f'  {v:8} {at}  {d}')
        finally:
            conn.close()
        return 0 if ok == 'ok' else 1
    if cmd == 'restore' and len(argv) == 3:
        target = Path(argv[2])
        if not target.is_absolute() and not target.exists():
            items = list_backups()
            if argv[2].isdigit() and 1 <= int(argv[2]) <= len(items):
                target = items[int(argv[2]) - 1]          # restore by number from "list"
            else:
                target = BACKUP_DIR / argv[2]
        print(f'Restoring {target.name} ...')
        safety = restore_database(target)
        print(f'Restored. The database you had before is saved as: {safety}')
        return 0
    print(__doc__)
    return 1


if __name__ == '__main__':
    try:
        sys.exit(_main(sys.argv))
    except Exception as ex:
        print(f'ERROR: {ex}')
        sys.exit(1)
