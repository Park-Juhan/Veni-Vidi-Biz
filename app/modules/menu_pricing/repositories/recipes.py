"""Saved menus and their recipes (material id + quantity in the material's base unit)."""
from decimal import Decimal
from app.common.db import utc_now


class RecipeStore:
    def __init__(self, database):
        self.database = database

    def save(self, workspace, name, items):
        """Create or replace the menu's recipe. items: [(material_id, quantity, unit)]."""
        now = utc_now()
        with self.database.connect() as connection:
            self.database.touch_workspace(connection, workspace)
            connection.execute(
                'INSERT INTO menus (workspace_id, name, updated_at) VALUES (?, ?, ?) '
                'ON CONFLICT(workspace_id, name) DO UPDATE SET updated_at = excluded.updated_at', (workspace, name, now))
            menu_id = connection.execute('SELECT id FROM menus WHERE workspace_id = ? AND name = ?', (workspace, name)).fetchone()['id']
            connection.execute('DELETE FROM recipe_items WHERE menu_id = ?', (menu_id,))
            connection.executemany(
                'INSERT INTO recipe_items (menu_id, material_id, quantity, unit, position) '
                'SELECT ?, id, ?, ?, ? FROM materials WHERE id = ? AND workspace_id = ?',
                [(menu_id, str(quantity), unit, position, material_id, workspace)
                 for position, (material_id, quantity, unit) in enumerate(items)])
        return menu_id

    def list(self, workspace):
        with self.database.connect() as connection:
            menus = connection.execute('SELECT id, name, updated_at FROM menus WHERE workspace_id = ? ORDER BY updated_at DESC, id DESC',
                                       (workspace,)).fetchall()
            items = connection.execute(
                'SELECT r.menu_id, r.material_id, m.name AS material_name, r.quantity, r.unit FROM recipe_items r '
                'JOIN menus u ON u.id = r.menu_id JOIN materials m ON m.id = r.material_id '
                'WHERE u.workspace_id = ? ORDER BY r.menu_id, r.position', (workspace,)).fetchall()
        by_menu = {}
        for row in items:
            by_menu.setdefault(row['menu_id'], []).append(dict(material_id=row['material_id'], material_name=row['material_name'],
                                                                quantity=Decimal(row['quantity']), unit=row['unit']))
        return [dict(id=row['id'], name=row['name'], updated_at=row['updated_at'], items=by_menu.get(row['id'], [])) for row in menus]

    def get(self, workspace, menu_id):
        return next((menu for menu in self.list(workspace) if menu['id'] == menu_id), None)

    def delete(self, workspace, menu_id):
        with self.database.connect() as connection:
            return connection.execute('DELETE FROM menus WHERE workspace_id = ? AND id = ?', (workspace, menu_id)).rowcount

    def forget(self, workspace):
        with self.database.connect() as connection:
            connection.execute('DELETE FROM menus WHERE workspace_id = ?', (workspace,))
