"""Promotion campaigns that were actually run, for one workspace (SQLite)."""
from app.common.db import utc_now
from app.common.validation import ValidationError

COLUMNS = ('name', 'channel', 'owner', 'started_on', 'ended_on', 'cost', 'hours_per_week',
           'new_customers', 'revenue_before', 'revenue_after', 'note')


class CampaignStore:
    def __init__(self, database):
        self.database = database

    def save(self, workspace, values, campaign_id=None):
        """Insert, or update when campaign_id is given. values: column -> text or None. Returns the id."""
        now = utc_now()
        data = [None if values.get(c) is None else str(values[c]) for c in COLUMNS]
        with self.database.connect() as connection:
            self.database.touch_workspace(connection, workspace)
            if campaign_id is None:
                return connection.execute(
                    f"INSERT INTO campaigns (workspace_id, {', '.join(COLUMNS)}, created_at, updated_at) "
                    f"VALUES (?, {', '.join('?' for _ in COLUMNS)}, ?, ?)", (workspace, *data, now, now)).lastrowid
            if not connection.execute(
                    f"UPDATE campaigns SET {', '.join(f'{c} = ?' for c in COLUMNS)}, updated_at = ? WHERE id = ? AND workspace_id = ?",
                    (*data, now, campaign_id, workspace)).rowcount:
                raise ValidationError('수정할 캠페인을 찾지 못했습니다. 화면을 새로고침해 주세요.')
            return campaign_id

    def list(self, workspace):
        with self.database.connect() as connection:
            rows = connection.execute(f"SELECT id, {', '.join(COLUMNS)} FROM campaigns WHERE workspace_id = ? "
                                      'ORDER BY started_on DESC, id DESC', (workspace,)).fetchall()
        return [dict(row) for row in rows]

    def delete(self, workspace, campaign_id):
        with self.database.connect() as connection:
            return connection.execute('DELETE FROM campaigns WHERE workspace_id = ? AND id = ?', (workspace, campaign_id)).rowcount

    def forget(self, workspace):
        with self.database.connect() as connection:
            connection.execute('DELETE FROM campaigns WHERE workspace_id = ?', (workspace,))
