"""Monthly sales per saved menu (quantity and average price)."""
from decimal import Decimal


class SalesStore:
    def __init__(self, database):
        self.database = database

    def save_period(self, workspace, period, rows):
        """Replace the period's sales for this workspace's menus. rows: [(menu_id, quantity, price)]."""
        with self.database.connect() as connection:
            self.database.touch_workspace(connection, workspace)
            connection.execute('DELETE FROM menu_sales WHERE period = ? AND menu_id IN (SELECT id FROM menus WHERE workspace_id = ?)',
                               (period, workspace))
            connection.executemany(
                'INSERT INTO menu_sales (menu_id, period, quantity, price) SELECT id, ?, ?, ? FROM menus WHERE id = ? AND workspace_id = ?',
                [(period, str(quantity), str(price), menu_id, workspace) for menu_id, quantity, price in rows])

    def periods(self, workspace):
        with self.database.connect() as connection:
            return [row['period'] for row in connection.execute(
                'SELECT DISTINCT s.period FROM menu_sales s JOIN menus m ON m.id = s.menu_id WHERE m.workspace_id = ? ORDER BY s.period DESC',
                (workspace,))]

    def for_period(self, workspace, period):
        """{menu_id: (quantity, price)} for the period."""
        with self.database.connect() as connection:
            rows = connection.execute(
                'SELECT s.menu_id, s.quantity, s.price FROM menu_sales s JOIN menus m ON m.id = s.menu_id '
                'WHERE m.workspace_id = ? AND s.period = ?', (workspace, period)).fetchall()
        return {row['menu_id']: (Decimal(row['quantity']), Decimal(row['price'])) for row in rows}

    def latest_prices(self, workspace):
        """{menu_id: price} from each menu's most recent sales month."""
        with self.database.connect() as connection:
            rows = connection.execute(
                'SELECT s.menu_id, s.price FROM menu_sales s JOIN menus m ON m.id = s.menu_id WHERE m.workspace_id = ? '
                'AND s.period = (SELECT MAX(period) FROM menu_sales t WHERE t.menu_id = s.menu_id)', (workspace,)).fetchall()
        return {row['menu_id']: Decimal(row['price']) for row in rows}

    def delete_period(self, workspace, period):
        with self.database.connect() as connection:
            return connection.execute('DELETE FROM menu_sales WHERE period = ? AND menu_id IN (SELECT id FROM menus WHERE workspace_id = ?)',
                                      (period, workspace)).rowcount
