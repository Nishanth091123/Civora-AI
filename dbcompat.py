"""Civora AI v3.7.0 - one database layer for SQLite (PC) and PostgreSQL (online).

  * No DATABASE_URL  -> SQLite file data/buildquant.db, exactly as before.
  * DATABASE_URL=postgresql://...  (Neon, Supabase, Render Postgres, any PostgreSQL 13+)
                     -> every module keeps its existing SQL; this layer translates the few
                        SQLite-only parts on the fly:
       ?                      -> %s placeholders (and a literal % -> %%)
       INSERT OR IGNORE       -> INSERT ... ON CONFLICT DO NOTHING
       rowid                  -> ctid (only used for "newest first" ordering)
       LIKE                   -> ILIKE (SQLite LIKE ignores case)
       PRAGMA table_info(t)   -> information_schema.columns (same column names: cid, name, type ...)
       PRAGMA foreign_keys    -> nothing (PostgreSQL always enforces foreign keys)
       sqlite_master          -> a view over information_schema.tables (created once)
       CREATE TABLE types     -> INTEGER→BIGINT, REAL→DOUBLE PRECISION, AUTOINCREMENT→BIGSERIAL
    Rows behave like sqlite3.Row (row['col'], row[0], keys(), dict(row)); NUMERIC comes back as
    int/float; errors are raised as sqlite3.IntegrityError / sqlite3.OperationalError so existing
    "except sqlite3.IntegrityError" code keeps working. Each INSERT runs inside a SAVEPOINT so a
    caught duplicate does not abort the whole transaction (PostgreSQL behaviour).
  Connections are pooled and re-opened automatically when the server dropped an idle one
  (Neon closes idle connections after a few minutes).
"""
import decimal
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager

_ROLLBACK_SP = 'ROLLBACK TO SAVEPOINT civora_sp'


def database_url():
    url = (os.environ.get('DATABASE_URL') or '').strip()
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    return url if url.startswith('postgresql://') else ''


def is_postgres():
    return bool(database_url())


def backend_label():
    if not is_postgres():
        return 'SQLite'
    m = re.match(r'postgresql://[^@]*@([^/:?]+)', database_url())
    return f'PostgreSQL ({m.group(1)})' if m else 'PostgreSQL'


# ------------------------------------------------------------------ SQL translation (pure, unit tested)
def _split_literals(sql):
    """[(is_literal, text)] - single-quoted strings ('' escapes) kept intact."""
    out, i, n = [], 0, len(sql)
    buf = []
    while i < n:
        ch = sql[i]
        if ch == "'":
            if buf:
                out.append((False, ''.join(buf))); buf = []
            j = i + 1
            while j < n:
                if sql[j] == "'" and j + 1 < n and sql[j + 1] == "'":
                    j += 2; continue
                if sql[j] == "'":
                    break
                j += 1
            out.append((True, sql[i:j + 1])); i = j + 1
            continue
        buf.append(ch); i += 1
    if buf:
        out.append((False, ''.join(buf)))
    return out


_TABLE_INFO = re.compile(r'^\s*PRAGMA\s+table_info\s*\(\s*["\']?([A-Za-z0-9_]+)["\']?\s*\)\s*;?\s*$', re.I)


def translate(sql):
    """SQLite SQL -> PostgreSQL SQL with %s placeholders. Returns None for statements to skip."""
    s = sql.strip()
    up = s.upper()
    if up.startswith('PRAGMA'):
        m = _TABLE_INFO.match(s)
        if m:
            return ("SELECT ordinal_position-1 AS cid, column_name AS name, data_type AS type, "
                    "CASE WHEN is_nullable='NO' THEN 1 ELSE 0 END AS notnull, column_default AS dflt_value, 0 AS pk "
                    "FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='%s' "
                    "ORDER BY ordinal_position" % m.group(1).lower())
        if 'INTEGRITY_CHECK' in up or 'QUICK_CHECK' in up:
            return "SELECT 'ok' AS integrity_check"
        return None                                   # foreign_keys, journal_mode ... nothing to do
    if re.search(r'\bINSERT\s+OR\s+REPLACE\b', up):
        raise sqlite3.OperationalError('INSERT OR REPLACE is not portable; use ON CONFLICT DO UPDATE')
    ddl = up.startswith('CREATE TABLE')
    ignore = bool(re.match(r'INSERT\s+OR\s+IGNORE\b', up))
    parts = []
    for lit, text in _split_literals(s):
        if lit:
            parts.append(text.replace('%', '%%'))
            continue
        t = text.replace('%', '%%').replace('?', '%s')
        t = re.sub(r'\bINSERT\s+OR\s+IGNORE\s+INTO\b', 'INSERT INTO', t, flags=re.I)
        t = re.sub(r'\browid\b', 'ctid', t, flags=re.I)
        t = re.sub(r'(?<![A-Za-z_])LIKE\b', 'ILIKE', t)
        t = re.sub(r'(?<![A-Za-z_])like\b', 'ILIKE', t)
        if ddl:
            t = re.sub(r'\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b', 'BIGSERIAL PRIMARY KEY', t, flags=re.I)
            t = re.sub(r'\bINTEGER\b', 'BIGINT', t, flags=re.I)
            t = re.sub(r'\bREAL\b', 'DOUBLE PRECISION', t, flags=re.I)
        parts.append(t)
    out = ''.join(parts).rstrip().rstrip(';')
    if ignore:
        out += ' ON CONFLICT DO NOTHING'
    return out


def split_script(script):
    """executescript: statements separated by ; outside string literals."""
    stmts, cur = [], []
    for lit, text in _split_literals(script):
        if lit:
            cur.append(text); continue
        pieces = text.split(';')
        for k, p in enumerate(pieces):
            cur.append(p)
            if k < len(pieces) - 1:
                stmts.append(''.join(cur)); cur = []
    stmts.append(''.join(cur))
    return [x.strip() for x in stmts if x.strip()]


# ------------------------------------------------------------------ rows and cursors
class Row(tuple):
    """sqlite3.Row look-alike."""
    def __new__(cls, values, index):
        r = super().__new__(cls, values)
        r._index = index
        return r

    def __getitem__(self, k):
        if isinstance(k, str):
            try:
                return tuple.__getitem__(self, self._index[k])
            except KeyError:
                return tuple.__getitem__(self, self._index[k.lower()])
        return tuple.__getitem__(self, k)

    def keys(self):
        return list(self._index)

    def get(self, k, default=None):
        try:
            return self[k]
        except (KeyError, IndexError):
            return default


def _plain(v):
    if isinstance(v, decimal.Decimal):
        return int(v) if v == v.to_integral_value() and abs(v) < 2 ** 63 else float(v)
    if isinstance(v, memoryview):
        return bytes(v)
    return v


class Cursor:
    def __init__(self, cur=None):
        self._cur = cur
        self._index = {}
        if cur is not None and cur.description:
            for i, d in enumerate(cur.description):
                self._index.setdefault(getattr(d, 'name', d[0] if isinstance(d, tuple) else str(d)), i)
        self.rowcount = getattr(cur, 'rowcount', -1) if cur is not None else -1
        self.description = getattr(cur, 'description', None)

    def _wrap(self, t):
        return None if t is None else Row(tuple(_plain(v) for v in t), self._index)

    def fetchone(self):
        if self._cur is None or not self._index:
            return None
        return self._wrap(self._cur.fetchone())

    def fetchall(self):
        if self._cur is None or not self._index:
            return []
        return [self._wrap(t) for t in self._cur.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


def _map_error(ex):
    import psycopg
    msg = str(ex).strip().splitlines()[0] if str(ex).strip() else type(ex).__name__
    if isinstance(ex, psycopg.errors.IntegrityError):
        return sqlite3.IntegrityError(msg)
    return sqlite3.OperationalError(msg)


class Connection:
    """sqlite3.Connection look-alike over a psycopg 3 connection."""
    row_factory = None

    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=()):
        import psycopg
        q = translate(sql)
        if q is None:
            return Cursor()
        params = tuple(params or ())
        is_insert = q.lstrip().upper().startswith('INSERT')
        try:
            if is_insert:
                self._raw.execute('SAVEPOINT civora_sp')
            cur = self._raw.execute(q, params)
            if is_insert:
                self._raw.execute('RELEASE SAVEPOINT civora_sp')
            return Cursor(cur)
        except psycopg.Error as ex:
            if is_insert:
                try:
                    self._raw.execute(_ROLLBACK_SP)
                except psycopg.Error:
                    pass
            raise _map_error(ex) from ex

    def executemany(self, sql, seq):
        cur = Cursor()
        for p in seq:
            cur = self.execute(sql, p)
        return cur

    def executescript(self, script):
        for stmt in split_script(script):
            self.execute(stmt)

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        _POOL.put(self._raw)

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is None:
            self.commit()
        else:
            self.rollback()


# ------------------------------------------------------------------ pool
class _Pool:
    def __init__(self, size=4):
        self.size, self.idle, self.lock = size, [], threading.Lock()

    def _new(self):
        import psycopg
        try:
            return psycopg.connect(database_url(), autocommit=False, prepare_threshold=None, connect_timeout=20)
        except psycopg.Error as ex:
            raise sqlite3.OperationalError(f'Cannot connect to the database: {str(ex)[:200]}') from ex

    def get(self):
        import psycopg
        while True:
            with self.lock:
                item = self.idle.pop() if self.idle else None
            if item is None:
                return self._new()
            raw, since = item
            if getattr(raw, 'closed', False) or getattr(raw, 'broken', False):
                continue
            if time.time() - since > 60:              # may have been dropped by the server - check cheaply
                try:
                    raw.execute('SELECT 1'); raw.rollback()
                except psycopg.Error:
                    try:
                        raw.close()
                    except Exception:
                        pass
                    continue
            return raw

    def put(self, raw):
        try:
            if getattr(raw, 'closed', False) or getattr(raw, 'broken', False):
                return
            raw.rollback()                              # never keep an open transaction in the pool
            with self.lock:
                if len(self.idle) < self.size:
                    self.idle.append((raw, time.time())); return
            raw.close()
        except Exception:
            try:
                raw.close()
            except Exception:
                pass


_POOL = _Pool()
_INIT = {'done': False}
_INIT_LOCK = threading.Lock()

_BOOTSTRAP = [
    """CREATE OR REPLACE VIEW sqlite_master AS
       SELECT 'table'::text AS type, table_name::text AS name, table_name::text AS tbl_name
       FROM information_schema.tables WHERE table_schema=current_schema() AND table_type='BASE TABLE'""",
    'CREATE TABLE IF NOT EXISTS civora_kv(key TEXT PRIMARY KEY, value TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS civora_files(stored_name TEXT PRIMARY KEY, data BYTEA NOT NULL, created BIGINT NOT NULL)',
]


def connect():
    """A pooled PostgreSQL connection wrapped as a sqlite3-style Connection."""
    raw = _POOL.get()
    if not _INIT['done']:
        with _INIT_LOCK:
            if not _INIT['done']:
                import psycopg
                try:
                    for q in _BOOTSTRAP:
                        raw.execute(q)
                    raw.commit()
                except psycopg.Error:
                    raw.rollback()                       # view exists from another instance: fine
                _INIT['done'] = True
    return Connection(raw)


@contextmanager
def pg_session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except BaseException:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


# ------------------------------------------------------------------ small key/value store (session key)
def kv_get(conn, key):
    r = conn.execute('SELECT value FROM civora_kv WHERE key=?', (key,)).fetchone()
    return r['value'] if r else None


def kv_set(conn, key, value):
    conn.execute('INSERT INTO civora_kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))
