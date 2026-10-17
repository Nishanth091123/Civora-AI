"""Civora AI v3.7.0 - copy your existing SQLite data (users, projects, estimates, drawings ...)
into the PostgreSQL database used by the online app. Safe to run more than once: rows that are
already there are skipped. Your SQLite file is only READ, never changed.

    cd /d C:\\Civora_AI
    set DATABASE_URL=postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require
    .venv\\Scripts\\python.exe migrate_to_postgres.py

Optional:  migrate_to_postgres.py path\\to\\buildquant.db  path\\to\\uploads
"""
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(argv):
    import dbcompat
    if not dbcompat.is_postgres():
        print('Set DATABASE_URL to your PostgreSQL connection string first (see the top of this file).')
        return 1
    src = Path(argv[1]) if len(argv) > 1 else HERE / 'data' / 'buildquant.db'
    uploads = Path(argv[2]) if len(argv) > 2 else src.parent / 'uploads'
    if not src.is_file():
        print(f'SQLite database not found: {src}')
        return 1
    print(f'From: {src}\nTo:   {dbcompat.backend_label()}')
    print('Creating the Civora tables in PostgreSQL ...')
    import app  # noqa: F401  - importing the app creates every table (idempotent)
    lite = sqlite3.connect(f'file:{src}?mode=ro', uri=True)
    lite.row_factory = sqlite3.Row
    tables = [r[0] for r in lite.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    with dbcompat.pg_session() as pg:
        pg_tables = {r['name'] for r in pg.execute('SELECT name FROM sqlite_master').fetchall()}
    first = ['users', 'projects', 'uploads']
    tables = [t for t in first if t in tables] + [t for t in tables if t not in first]
    pending = {}
    for t in tables:
        if t not in pg_tables:
            print(f'  skip {t}: not used by this version')
            continue
        with dbcompat.pg_session() as pg:
            pg_cols = [r['name'] for r in pg.execute(f'PRAGMA table_info("{t}")').fetchall()]
        cols = [r[1] for r in lite.execute(f'PRAGMA table_info("{t}")').fetchall() if r[1] in pg_cols]
        rows = [tuple(r[c] for c in cols) for r in lite.execute(f'SELECT {",".join(chr(34) + c + chr(34) for c in cols)} FROM "{t}"').fetchall()]
        pending[t] = (cols, rows)
    # several passes so rows that depend on other tables (foreign keys) go in after them
    totals = {t: [0, 0] for t in pending}
    for _ in range(5):
        progress = False
        for t, (cols, rows) in list(pending.items()):
            left = []
            sql = f'INSERT OR IGNORE INTO "{t}"({",".join(chr(34) + c + chr(34) for c in cols)}) VALUES({",".join("?" * len(cols))})'
            with dbcompat.pg_session() as pg:
                for row in rows:
                    try:
                        cur = pg.execute(sql, row)
                        totals[t][0 if cur.rowcount else 1] += 1
                        progress = True
                    except sqlite3.Error:
                        left.append(row)
            pending[t] = (cols, left)
        if not progress or not any(r for _, r in pending.values()):
            break
    with dbcompat.pg_session() as pg:
        for t in totals:
            cols = pending[t][0]
            if 'id' in cols:
                r = pg.execute(f"SELECT pg_get_serial_sequence('{t}','id') AS s").fetchone()
                if r and r['s']:
                    pg.execute(f"SELECT setval('{r['s']}', COALESCE((SELECT MAX(id) FROM \"{t}\"),0)+1, false)")
    for t, (added, existing) in totals.items():
        failed = len(pending[t][1])
        print(f'  {t:32} added {added:5}   already there {existing:5}' + (f'   NOT COPIED {failed}' if failed else ''))
    import filestore
    if uploads.is_dir():
        n = filestore.sync_up(uploads)
        print(f'Drawings copied into the database: {n}')
    print('Done. Open the online Civora and sign in with your usual username and password.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
