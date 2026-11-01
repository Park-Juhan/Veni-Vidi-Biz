"""Replaceable memory storage; never connects to a DB or writes user data to disk."""
from copy import deepcopy
from dataclasses import dataclass
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
