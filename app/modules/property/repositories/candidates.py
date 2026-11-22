"""Saved location candidates for one workspace (SQLite)."""
import sqlite3
from app.common.db import utc_now
from app.common.validation import ValidationError

COLUMNS = ('name', 'rent', 'deposit', 'area', 'interior', 'fit', 'traffic', 'facility')


class CandidateStore:
    def __init__(self, database):
        self.database = database

    def save(self, workspace, values, candidate_id=None):
        """Insert a candidate, or update it when candidate_id is given. values: column -> text. Returns the id."""
        now = utc_now()
        data = [str(values[c]) for c in COLUMNS]
        try:
            with self.database.connect() as connection:
                self.database.touch_workspace(connection, workspace)
                if candidate_id is None:
                    cursor = connection.execute(
                        f"INSERT INTO location_candidates (workspace_id, {', '.join(COLUMNS)}, created_at, updated_at) "
                        f"VALUES (?, {', '.join('?' for _ in COLUMNS)}, ?, ?)", (workspace, *data, now, now))
                    return cursor.lastrowid
                updated = connection.execute(
                    f"UPDATE location_candidates SET {', '.join(f'{c} = ?' for c in COLUMNS)}, updated_at = ? "
                    'WHERE id = ? AND workspace_id = ?', (*data, now, candidate_id, workspace)).rowcount
                if not updated:
                    raise ValidationError('수정할 후보를 찾지 못했습니다. 화면을 새로고침해 주세요.')
                return candidate_id
        except sqlite3.IntegrityError as exc:
            raise ValidationError(f"같은 이름의 후보 '{values['name']}'이(가) 이미 있습니다. 다른 이름을 쓰세요.") from exc

    def list(self, workspace):
        with self.database.connect() as connection:
            rows = connection.execute(f"SELECT id, {', '.join(COLUMNS)}, updated_at FROM location_candidates "
                                      'WHERE workspace_id = ? ORDER BY id', (workspace,)).fetchall()
        return [dict(row) for row in rows]

    def delete(self, workspace, candidate_id):
        with self.database.connect() as connection:
            return connection.execute('DELETE FROM location_candidates WHERE workspace_id = ? AND id = ?', (workspace, candidate_id)).rowcount

    def forget(self, workspace):
        with self.database.connect() as connection:
            connection.execute('DELETE FROM location_candidates WHERE workspace_id = ?', (workspace,))
