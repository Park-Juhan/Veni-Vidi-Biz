"""Release regressions: numeric errors, CLI input and real Git ignore rules."""
from decimal import Overflow
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from app.common.model import AnalysisModel
from app.common.repository import MemoryRepository
from app.common.validation import ValidationError
from app.main.application import MODULES, create_app
from tests.module_support import model_for


ROOT = Path(__file__).resolve().parents[1]


class ReleaseInputTests(unittest.TestCase):
    def test_extreme_numbers_return_422_without_replacing_saved_result(self):
        for name, *_ in MODULES:
            with self.subTest(module=name):
                client = create_app({'TESTING': True}, [name]).test_client()
                path = '/' + name.replace('_', '-') + '/'
                client.get(path)
                with client.session_transaction() as session:
                    csrf = session['csrf']
                model = model_for(name)
                defaults = model.defaults() | {'csrf': csrf}
                numeric = next(f.name for f in model.fields if f.kind == 'number')
                self.assertEqual(client.post(path, data=defaults).status_code, 303)
                for value in ('1e-999999999', '0.' + '0' * 65 + '1'):
                    response = client.post(path, data=defaults | {numeric: value})
                    self.assertEqual(response.status_code, 422)
                    self.assertIn('role="alert"', response.get_data(as_text=True))
                self.assertIn('<table>', client.get(path).get_data(as_text=True))

    def test_decimal_failure_becomes_validation_error_and_is_not_saved(self):
        class FailingCalculation(AnalysisModel):
            def calculate(self, values):
                raise Overflow

        model = FailingCalculation(MemoryRepository())
        with self.assertRaises(ValidationError):
            model.analyze({}, 'test')
        self.assertIsNone(model.latest('test'))

    def test_invalid_cli_options_show_usage_without_traceback(self):
        for args in (
            ['--module', 'unknown'], ['--port', '0'], ['--port', '65536'],
            ['--port', 'not-a-number'],
        ):
            with self.subTest(args=args):
                result = subprocess.run(
                    [sys.executable, str(ROOT / 'run.py'), *args],
                    cwd=ROOT, capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn('usage:', result.stderr)
                self.assertNotIn('Traceback', result.stderr)


@unittest.skipUnless(shutil.which('git'), 'Git is needed to verify upload exclusions')
class GitUploadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Keep the real project uninitialized and never touch its index/history.
        cls.temp = tempfile.TemporaryDirectory(prefix='veni-git-review-')
        cls.metadata = Path(cls.temp.name) / 'review.git'
        subprocess.run(
            ['git', 'init', '--bare', '--quiet', str(cls.metadata)],
            check=True, capture_output=True, text=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def git(self, *args, input=None):
        return subprocess.run(
            ['git', '--git-dir', str(self.metadata), '--work-tree', str(ROOT), *args],
            cwd=ROOT, input=input, capture_output=True, text=True, encoding='utf-8',
            check=False, timeout=10,
        )

    def test_local_and_sensitive_paths_are_ignored(self):
        paths = [
            '.venv/pyvenv.cfg', 'venv/pyvenv.cfg', 'tmp/ui/home.png',
            '.env', '.env.local', '.env.production', '.envrc', 'config/dev.env',
            '.vscode/settings.json', '.idea/workspace.xml', '.aws/credentials',
            '.codex/config.toml', '.ssh/id_rsa', 'secrets/config.json',
            'credentials.json', 'service-account-dev.json', 'secrets.json', 'auth.json',
            'id_ed25519', 'cert.pem', 'private.key',
            'certificate.pfx', 'local-data/sales.csv', 'data/private/customers.csv',
            'instance/settings.py', 'uploads/business.csv', 'server.log', 'data.sqlite3',
            'app/__pycache__/module.pyc',
        ]
        result = self.git('check-ignore', '--no-index', '--stdin', '-z', input='\0'.join(paths)+'\0')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(result.stdout.rstrip('\0').split('\0')), set(paths))

    def test_public_sources_and_placeholder_example_can_be_uploaded(self):
        paths = [
            'run.py', 'README.md', '.gitignore', '.gitattributes', '.env.example',
            '.github/workflows/tests.yml', 'requirements.txt', 'requirements-dev.txt',
            'app/common/validation.py', 'tests/test_release_readiness.py',
        ]
        for name, *_ in MODULES:
            paths += [
                f'app/modules/{name}/models/service.py',
                f'app/modules/{name}/controllers/routes.py',
                f'app/modules/{name}/repositories/memory.py',
                f'app/modules/{name}/views/{name}/index.html',
            ]
        result = self.git('check-ignore', '--no-index', '--stdin', '-z', input='\0'.join(paths)+'\0')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertFalse(result.stdout)


if __name__ == '__main__':
    unittest.main()
