"""Dishes analysed in the material cost module, one row per workspace and dish name (SQLite)."""
import json
from decimal import Decimal
from app.common.db import utc_now


class DishStore:
    def __init__(self, database):
        self.database = database

    def save(self, workspace, name, monthly_volume, cost, items):
        """items: [{name, quantity, unit, cost}] with Decimal values. Replaces the dish of the same name."""
        data = json.dumps([{k: str(v) for k, v in item.items()} for item in items], ensure_ascii=False)
        with self.database.connect() as connection:
            self.database.touch_workspace(connection, workspace)
            connection.execute(
                'INSERT INTO dishes (workspace_id, name, monthly_volume, cost, items, updated_at) VALUES (?, ?, ?, ?, ?, ?) '
                'ON CONFLICT(workspace_id, name) DO UPDATE SET monthly_volume = excluded.monthly_volume, cost = excluded.cost, '
                'items = excluded.items, updated_at = excluded.updated_at', (workspace, name, str(monthly_volume), str(cost), data, utc_now()))

    def list(self, workspace):
        with self.database.connect() as connection:
            rows = connection.execute('SELECT * FROM dishes WHERE workspace_id = ? ORDER BY updated_at DESC, id DESC', (workspace,)).fetchall()
        return [dict(id=r['id'], name=r['name'], monthly_volume=Decimal(r['monthly_volume']), cost=Decimal(r['cost']), updated_at=r['updated_at'],
                     items=[dict(name=i['name'], quantity=Decimal(i['quantity']), unit=i['unit'], cost=Decimal(i['cost'])) for i in json.loads(r['items'])])
                for r in rows]

    def delete(self, workspace, dish_id):
        with self.database.connect() as connection:
            return connection.execute('DELETE FROM dishes WHERE workspace_id = ? AND id = ?', (workspace, dish_id)).rowcount

    def forget(self, workspace):
        with self.database.connect() as connection:
            connection.execute('DELETE FROM dishes WHERE workspace_id = ?', (workspace,))
