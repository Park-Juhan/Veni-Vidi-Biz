"""Shared checks; importing this helper does not import any business module."""
import importlib

from app.main.application import create_app


def model_for(name):
    class_prefix = ''.join(part.title() for part in name.split('_'))
    module = importlib.import_module(f'app.modules.{name}.models.service')
    repositories = importlib.import_module(f'app.modules.{name}.repositories.memory')
    repository = getattr(repositories, class_prefix + 'Repository')()
    return getattr(module, class_prefix + 'Model')(repository)


class StandaloneModuleChecks:
    """Mixin: each module suite exercises its own MVC app and memory store."""

    def standalone_client(self):
        app = create_app({'TESTING': True}, enabled_modules=[self.module_name])
        return app.test_client()

    @property
    def module_path(self):
        return '/' + self.module_name.replace('_', '-') + '/'

    def submit(self, client, values):
        client.get(self.module_path)
        with client.session_transaction() as session:
            token = session['csrf']
        return client.post(
            self.module_path, data=values | {'csrf': token}, follow_redirects=True
        )

    def test_only_requested_module_is_registered(self):
        client = self.standalone_client()
        rules = {rule.rule for rule in client.application.url_map.iter_rules()}
        self.assertEqual(
            rules, {'/', self.module_path, '/static/<path:filename>'}
        )
        response = client.get(self.module_path)
        self.assertEqual(response.status_code, 200)
        self.assertIn('조건 입력', response.get_data(as_text=True))

    def test_standalone_input_calculation_output(self):
        client = self.standalone_client()
        response = self.submit(client, model_for(self.module_name).defaults())
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('계산 기준과 확인할 점', html)
        self.assertIn('<table>', html)
        self.assertIn('가상 예시', html)
        # New anonymous browser has its own empty result, even in the same app.
        other = client.application.test_client()
        self.assertNotIn('<table>', other.get(self.module_path).get_data(as_text=True))

    def test_standalone_invalid_input_returns_422(self):
        model = model_for(self.module_name)
        numeric = next(field.name for field in model.fields if field.kind == 'number')
        response = self.submit(
            self.standalone_client(), model.defaults() | {numeric: 'invalid-number'}
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn('role="alert"', response.get_data(as_text=True))
