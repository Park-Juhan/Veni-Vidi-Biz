"""Saved materials and their purchase history for one workspace (SQLite)."""
from decimal import Decimal
from app.common.db import utc_now


class MaterialCatalog:
    def __init__(self, database):
        self.database = database

    def save_purchase(self, workspace, name, unit, yield_rate, unit_price, quantity):
        """Create the material or update its unit/yield, then record this purchase. Returns the material id."""
        now = utc_now()
        with self.database.connect() as connection:
            self.database.touch_workspace(connection, workspace)
            connection.execute(
                'INSERT INTO materials (workspace_id, name, unit, yield_rate, created_at) VALUES (?, ?, ?, ?, ?) '
                'ON CONFLICT(workspace_id, name) DO UPDATE SET unit = excluded.unit, yield_rate = excluded.yield_rate',
                (workspace, name, unit, str(yield_rate), now))
            material_id = connection.execute('SELECT id FROM materials WHERE workspace_id = ? AND name = ?', (workspace, name)).fetchone()['id']
            connection.execute('INSERT INTO material_purchases (material_id, quantity, unit_price, purchased_at) VALUES (?, ?, ?, ?)',
                               (material_id, str(quantity), str(unit_price), now))
        return material_id

    def list(self, workspace):
        """Each material with its latest purchase, newest purchase first."""
        with self.database.connect() as connection:
            rows = connection.execute(
                'SELECT m.id, m.name, m.unit, m.yield_rate, p.unit_price, p.quantity, p.purchased_at, '
                '(SELECT COUNT(*) FROM material_purchases c WHERE c.material_id = m.id) AS purchases '
                'FROM materials m JOIN material_purchases p ON p.id = '
                '(SELECT id FROM material_purchases WHERE material_id = m.id ORDER BY id DESC LIMIT 1) '
                'WHERE m.workspace_id = ? ORDER BY p.id DESC', (workspace,)).fetchall()
        return [dict(id=row['id'], name=row['name'], unit=row['unit'], yield_rate=Decimal(row['yield_rate']),
                     unit_price=Decimal(row['unit_price']), quantity=Decimal(row['quantity']),
                     purchased_at=row['purchased_at'], purchases=row['purchases']) for row in rows]

    def delete(self, workspace, material_id):
        with self.database.connect() as connection:
            return connection.execute('DELETE FROM materials WHERE workspace_id = ? AND id = ?', (workspace, material_id)).rowcount

    def forget(self, workspace):
        with self.database.connect() as connection:
            connection.execute('DELETE FROM materials WHERE workspace_id = ?', (workspace,))
