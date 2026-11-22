"""Analysis storage contract with a memory implementation (tests, no-DB runs) and a SQLite one."""
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
import json
from datetime import datetime, timezone
from threading import RLock
from typing import Protocol


@dataclass
class AnalysisRecord:
    inputs: dict
    result: dict
    source: str
    updated_at: str


class AnalysisRepository(Protocol):
    def latest(self, workspace: str) -> AnalysisRecord | None: ...
    def save(self, workspace: str, record: AnalysisRecord) -> None: ...
    def delete(self, workspace: str) -> None: ...


class MemoryRepository:
    """One latest record per anonymous browser, module and process. TTL: 24h."""
    def __init__(self):
        self._records = {}
        self._lock = RLock()

    def _expire(self):
        now = datetime.now(timezone.utc).timestamp()
        expired = [key for key, (created, _) in self._records.items() if now-created > 86400]
        for key in expired:
            del self._records[key]

    def latest(self, workspace):
        with self._lock:
            self._expire()
            item = self._records.get(workspace)
            return deepcopy(item[1]) if item else None

    def save(self, workspace, record):
        with self._lock:
            self._expire()
            if workspace not in self._records and len(self._records) >= 1000:
                del self._records[next(iter(self._records))]
            self._records[workspace] = (datetime.now(timezone.utc).timestamp(), deepcopy(record))

    def delete(self, workspace):
        with self._lock:
            self._records.pop(workspace, None)


def _encode(value):
    if isinstance(value, Decimal):
        return {'__decimal__': str(value)}
    raise TypeError(f'Cannot store {type(value).__name__}')


def _decode(item):
    return Decimal(item['__decimal__']) if set(item) == {'__decimal__'} else item


def dumps(value):
    """JSON that keeps Decimal exact. Tuples come back as lists."""
    return json.dumps(value, default=_encode, ensure_ascii=False)


def loads(text):
    return json.loads(text, object_hook=_decode)


class SqliteRepository:
    """Analysis history for one module in the shared SQLite file. latest() returns the newest record."""
    def __init__(self, database, module):
        self.database = database
        self.module = module

    def latest(self, workspace):
        with self.database.connect() as connection:
            row = connection.execute(
                'SELECT inputs_json, result_json, source, created_at FROM analysis_records '
                'WHERE workspace_id = ? AND module = ? ORDER BY id DESC LIMIT 1', (workspace, self.module)).fetchone()
            if row is None:
                return None
            self.database.touch_workspace(connection, workspace)
        return AnalysisRecord(loads(row['inputs_json']), loads(row['result_json']), row['source'], row['created_at'])

    def save(self, workspace, record):
        with self.database.connect() as connection:
            self.database.touch_workspace(connection, workspace)
            connection.execute(
                'INSERT INTO analysis_records (workspace_id, module, inputs_json, result_json, source, created_at) '
                'VALUES (?, ?, ?, ?, ?, ?)',
                (workspace, self.module, dumps(record.inputs), dumps(record.result), record.source, record.updated_at))

    def delete(self, workspace):
        self.database.delete_workspace(workspace)
