"""SQLite storage: migrations, exact round trip, restart persistence, workspace code and deletion."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from app.common.db import Database
from app.common.repository import AnalysisRecord, SqliteRepository
from app.main.application import create_app
from tests.module_support import model_for


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.path = Path(self.folder.name) / 'data' / 'veni.db'

    def tearDown(self):
        self.folder.cleanup()

    def app(self):
        return create_app({'TESTING': True, 'DATABASE': self.path})

    @staticmethod
    def csrf(client, path='/workspace/'):
        client.get(path)
        with client.session_transaction() as session:
            return session['csrf'], session['workspace']

    def test_migrations_apply_once(self):
        database = Database(self.path)
        database.migrate()
        database.migrate()
        with database.connect() as connection:
            versions = [row['version'] for row in connection.execute('SELECT version FROM schema_version')]
        self.assertEqual(versions, [1])

    def test_repository_round_trip_is_exact_and_isolated(self):
        database = Database(self.path)
        database.migrate()
        repository = SqliteRepository(database, 'property')
        record = AnalysisRecord({'rent': '1200000'}, {'value': Decimal('0.1'), 'rows': [('A', Decimal('52.45'))]}, 'src', '2026-11-22T00:00:00+00:00')
        repository.save('w1', record)
        loaded = repository.latest('w1')
        self.assertEqual(loaded.result['value'], Decimal('0.1'))
        self.assertEqual(loaded.result['rows'], [['A', Decimal('52.45')]])
        self.assertIsNone(repository.latest('w2'))
        self.assertIsNone(SqliteRepository(database, 'marketing').latest('w1'))
        # History is kept; latest returns the newest.
        repository.save('w1', AnalysisRecord({}, {'value': Decimal(2)}, 'src', '2026-11-22T01:00:00+00:00'))
        self.assertEqual(repository.latest('w1').result['value'], Decimal(2))
        with database.connect() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM analysis_records').fetchone()[0], 2)

    def test_results_survive_restart(self):
        client = self.app().test_client()
        token, _ = self.csrf(client, '/property/')
        client.post('/property/', data=model_for('property').defaults() | {'csrf': token})
        cookie = client.get_cookie('session').value
        # A new app on the same database reuses the stored secret, so the old cookie still works.
        restarted = self.app().test_client()
        restarted.set_cookie('session', cookie)
        html = restarted.get('/property/').get_data(as_text=True)
        self.assertIn('<table>', html)
        self.assertIn('가상 주거지 B', html)
        self.assertTrue((self.path.parent / 'secret_key').exists())

    def test_open_workspace_by_code_and_delete(self):
        app = self.app()
        owner = app.test_client()
        token, code = self.csrf(owner, '/menu-pricing/')
        owner.post('/menu-pricing/', data=model_for('menu_pricing').defaults() | {'csrf': token})
        self.assertIn('-'.join(code[i:i+4] for i in range(0, 32, 4)), owner.get('/workspace/').get_data(as_text=True))

        other = app.test_client()
        token2, _ = self.csrf(other)
        self.assertEqual(other.post('/workspace/', data={'csrf': token2, 'action': 'open', 'code': 'not-a-code'}).status_code, 422)
        self.assertEqual(other.post('/workspace/', data={'csrf': token2, 'action': 'open', 'code': 'f' * 32}).status_code, 404)
        hyphenated = '-'.join(code[i:i+4] for i in range(0, 32, 4)).upper()
        response = other.post('/workspace/', data={'csrf': token2, 'action': 'open', 'code': hyphenated})
        self.assertEqual(response.status_code, 303)
        self.assertIn('<table>', other.get('/menu-pricing/').get_data(as_text=True))

        self.assertEqual(owner.post('/workspace/', data={'csrf': token, 'action': 'delete'}).status_code, 422)
        owner.post('/workspace/', data={'csrf': token, 'action': 'delete', 'confirm': 'yes'})
        self.assertNotIn('<table>', owner.get('/menu-pricing/').get_data(as_text=True))
        # The other browser had opened the same workspace, so its data is gone too.
        self.assertNotIn('<table>', other.get('/menu-pricing/').get_data(as_text=True))
        with owner.session_transaction() as session:
            self.assertNotEqual(session['workspace'], code)

    def test_purge_inactive_workspaces(self):
        database = Database(self.path)
        database.migrate()
        repository = SqliteRepository(database, 'property')
        repository.save('old', AnalysisRecord({}, {}, 'src', '2025-01-01T00:00:00+00:00'))
        repository.save('new', AnalysisRecord({}, {}, 'src', '2026-11-22T00:00:00+00:00'))
        stale = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat(timespec='seconds')
        with database.connect() as connection:
            connection.execute('UPDATE workspaces SET last_seen_at = ? WHERE id = ?', (stale, 'old'))
        self.assertEqual(database.purge_inactive(365), 1)
        self.assertIsNone(repository.latest('old'))
        self.assertIsNotNone(repository.latest('new'))

    def test_testing_without_database_stays_in_memory(self):
        app = create_app({'TESTING': True})
        self.assertFalse(app.jinja_env.globals.get('persistent', False))
        self.assertIn('메모리 임시 저장', app.test_client().get('/').get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
