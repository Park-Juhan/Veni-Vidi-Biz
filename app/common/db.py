"""SQLite file database: connections, versioned migrations and retention.

Uses only the standard library. Amounts are stored as text and restored as Decimal.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from uuid import uuid4

MIGRATIONS = Path(__file__).with_name('migrations')


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self._uri = None
        self._keeper = None

    @classmethod
    def in_memory(cls):
        """Private shared in-memory database for tests and no-file runs; lives as long as this object."""
        database = cls(':memory:')
        database._uri = f'file:veni-{uuid4().hex}?mode=memory&cache=shared'
        database._keeper = sqlite3.connect(database._uri, uri=True, check_same_thread=False)
        return database

    @contextmanager
    def connect(self):
        """One short-lived connection per unit of work; commits on success, rolls back on error."""
        connection = sqlite3.connect(self._uri, uri=True, timeout=10) if self._uri else sqlite3.connect(self.path, timeout=10)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA foreign_keys = ON')
            with connection:
                yield connection
        finally:
            connection.close()

    def migrate(self):
        """Apply migrations/NNN_*.sql in order, once each. Safe to call on every start."""
        if not self._uri:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
            applied = {row['version'] for row in connection.execute('SELECT version FROM schema_version')}
        for script in sorted(MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql')):
            version = int(script.name[:3])
            if version in applied:
                continue
            with self.connect() as connection:
                # executescript commits on its own; record the version right after in the same connection.
                connection.executescript(script.read_text(encoding='utf-8'))
                connection.execute('INSERT INTO schema_version (version, applied_at) VALUES (?, ?)', (version, utc_now()))

    def touch_workspace(self, connection, workspace):
        now = utc_now()
        connection.execute(
            'INSERT INTO workspaces (id, created_at, last_seen_at) VALUES (?, ?, ?) '
            'ON CONFLICT(id) DO UPDATE SET last_seen_at = excluded.last_seen_at', (workspace, now, now))

    def workspace_exists(self, workspace):
        with self.connect() as connection:
            return connection.execute('SELECT 1 FROM workspaces WHERE id = ?', (workspace,)).fetchone() is not None

    def delete_workspace(self, workspace):
        """Remove a workspace and, through ON DELETE CASCADE, everything stored for it."""
        with self.connect() as connection:
            connection.execute('DELETE FROM workspaces WHERE id = ?', (workspace,))

    def purge_inactive(self, days):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec='seconds')
        with self.connect() as connection:
            return connection.execute('DELETE FROM workspaces WHERE last_seen_at < ?', (cutoff,)).rowcount
