"""Monthly revenue and cost records for one workspace."""
from decimal import Decimal
from app.common.db import utc_now

ITEMS = ('revenue', 'rent', 'labor', 'material', 'utilities', 'advertising', 'other')


class FinancialStore:
    def __init__(self, database):
        self.database = database

    def save(self, workspace, period, values):
        with self.database.connect() as connection:
            self.database.touch_workspace(connection, workspace)
            connection.execute(
                f"INSERT INTO monthly_financials (workspace_id, period, {', '.join(ITEMS)}, updated_at) "
                f"VALUES (?, ?, {', '.join('?' for _ in ITEMS)}, ?) "
                f"ON CONFLICT(workspace_id, period) DO UPDATE SET {', '.join(f'{i} = excluded.{i}' for i in ITEMS)}, updated_at = excluded.updated_at",
                (workspace, period, *(str(values[i]) for i in ITEMS), utc_now()))

    def list(self, workspace):
        """All months, newest first."""
        with self.database.connect() as connection:
            rows = connection.execute(f"SELECT period, {', '.join(ITEMS)}, updated_at FROM monthly_financials "
                                      'WHERE workspace_id = ? ORDER BY period DESC', (workspace,)).fetchall()
        return [dict(period=row['period'], updated_at=row['updated_at'], **{i: Decimal(row[i]) for i in ITEMS}) for row in rows]

    def delete(self, workspace, period):
        with self.database.connect() as connection:
            return connection.execute('DELETE FROM monthly_financials WHERE workspace_id = ? AND period = ?', (workspace, period)).rowcount

    def forget(self, workspace):
        with self.database.connect() as connection:
            connection.execute('DELETE FROM monthly_financials WHERE workspace_id = ?', (workspace,))
