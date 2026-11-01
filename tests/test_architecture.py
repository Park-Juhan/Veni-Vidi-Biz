"""Check local import cycles and MVC data-access boundaries."""
import ast
from importlib.util import resolve_name
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def module_name(file):
    parts = list(file.relative_to(ROOT).with_suffix('').parts)
    if parts[-1] == '__init__':
        parts.pop()
    return '.'.join(parts)


def imported_modules(file):
    name = module_name(file)
    package = name if file.name == '__init__.py' else name.rpartition('.')[0]
    for node in ast.walk(ast.parse(file.read_text(encoding='utf-8'))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            target = '.' * node.level + (node.module or '')
            base = resolve_name(target, package) if node.level else target
            yield base
            for alias in node.names:
                yield base + '.' + alias.name


class ArchitectureTests(unittest.TestCase):
    def test_local_import_graph_has_no_cycles(self):
        files = {module_name(p): p for p in (ROOT / 'app').rglob('*.py')}
        graph = {
            name: {target for target in imported_modules(file) if target in files}
            for name, file in files.items()
        }
        # Include the factory's runtime imports of each module's entry points.
        for folder in (ROOT / 'app/modules').iterdir():
            if folder.is_dir() and (folder / 'models/service.py').exists():
                for suffix in ('models.service', 'controllers.routes', 'repositories.memory'):
                    graph['app.main.application'].add(f'app.modules.{folder.name}.{suffix}')
        visiting, visited = set(), set()

        def visit(name):
            self.assertNotIn(name, visiting, f'Import cycle involving {name}')
            if name in visited:
                return
            visiting.add(name)
            for target in graph[name]:
                visit(target)
            visiting.remove(name)
            visited.add(name)

        for name in graph:
            visit(name)

    def test_relative_and_absolute_imports_stay_within_module(self):
        for file in (ROOT / 'app/modules').rglob('*.py'):
            own = file.relative_to(ROOT / 'app/modules').parts[0]
            for target in imported_modules(file):
                if target.startswith('app.modules.'):
                    self.assertEqual(target.split('.')[2], own, str(file))

    def test_views_and_controllers_do_not_access_repositories(self):
        for file in (ROOT / 'app/modules').rglob('*.py'):
            if 'controllers' not in file.parts:
                continue
            self.assertFalse(any('.repositories' in name for name in imported_modules(file)))
            tree = ast.parse(file.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, ('repository', '_records'), str(file))
        for file in (ROOT / 'app').rglob('*.html'):
            text = file.read_text(encoding='utf-8')
            self.assertNotIn('repository.', text, str(file))
            self.assertNotIn('model.', text, str(file))


if __name__ == '__main__':
    unittest.main()
