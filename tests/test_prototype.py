import ast
from pathlib import Path
import unittest

from app.common.validation import ValidationError
from app.main.application import MODULES, create_app
from tests.module_support import model_for


class CalculationTests(unittest.TestCase):
    def test_invalid_numbers_and_missing_fields(self):
        for name,*_ in MODULES:
            model=model_for(name)
            number=next(f.name for f in model.fields if f.kind=='number')
            for invalid in ('NaN','Infinity','-Infinity','abc','1e999','-1',''):
                with self.subTest(module=name,value=invalid),self.assertRaises(ValidationError):
                    model.analyze(model.defaults()|{number:invalid},'a')
            with self.assertRaises(ValidationError): model.analyze({},'a')

    def test_repository_browser_isolation_and_defensive_copy(self):
        model=model_for('material_cost');r=model.analyze(model.defaults(),'a')
        self.assertIsNone(model.latest('b'))
        r.inputs['name']='altered'
        self.assertNotEqual(model.latest('a').inputs['name'],'altered')


class WebTests(unittest.TestCase):
    def setUp(self):
        self.app=create_app({'TESTING':True,'SECRET_KEY':'test-only'})
        self.client=self.app.test_client()

    def post(self,client,path,values):
        client.get(path)
        with client.session_transaction() as session: token=session['csrf']
        return client.post(path,data=values|{'csrf':token},follow_redirects=True)

    def test_all_routes_and_calculation_results(self):
        self.assertEqual(self.client.get('/').status_code,200)
        for name,*_ in MODULES:
            path='/'+name.replace('_','-')+'/'
            with self.subTest(module=name):
                response=self.post(self.client,path,model_for(name).defaults())
                self.assertEqual(response.status_code,200)
                self.assertIn('계산 기준과 확인할 점',response.get_data(as_text=True))
                self.assertIn('가상 예시',response.get_data(as_text=True))

    def test_each_module_runs_with_other_modules_disabled(self):
        for name,*_ in MODULES:
            client=create_app({'TESTING':True},[name]).test_client()
            with self.subTest(module=name):
                r=self.post(client,'/'+name.replace('_','-')+'/',model_for(name).defaults())
                self.assertEqual(r.status_code,200)
                self.assertIn('계산 기준과 확인할 점',r.get_data(as_text=True))

    def test_optional_material_import_and_missing_fallback(self):
        v=model_for('menu_pricing').defaults()|{'use_material':'yes'}
        self.assertEqual(self.post(self.client,'/menu-pricing/',v).status_code,422)
        self.post(self.client,'/material-cost/',model_for('material_cost').defaults())
        r=self.post(self.client,'/menu-pricing/',v)
        self.assertEqual(r.status_code,200)
        html=r.get_data(as_text=True)
        self.assertIn('재료비 연동',html)
        self.assertRegex(html,r'name="material"[^>]*value="360(?:\.0*)?"')
        other=self.app.test_client()
        self.assertEqual(self.post(other,'/menu-pricing/',v).status_code,422)

    def test_security_error_and_escaping(self):
        self.assertEqual(self.client.post('/menu-pricing/',data={}).status_code,400)
        self.assertEqual(self.client.get('/missing').status_code,404)
        v=model_for('property').defaults()|{'a_name':'<script>alert(1)</script>'}
        r=self.post(self.client,'/property/',v)
        self.assertNotIn('<script>alert(1)</script>',r.get_data(as_text=True))
        self.assertIn('&lt;script&gt;',r.get_data(as_text=True))
        self.assertIn("frame-ancestors 'none'",r.headers['Content-Security-Policy'])

    def test_non_ascii_csrf_is_a_bad_request(self):
        self.client.get('/menu-pricing/')
        response=self.client.post('/menu-pricing/',data={'csrf':'잘못된 토큰'})
        self.assertEqual(response.status_code,400)

    def test_missing_material_preserves_import_selection(self):
        values=model_for('menu_pricing').defaults()|{'use_material':'yes'}
        response=self.post(self.client,'/menu-pricing/',values)
        self.assertEqual(response.status_code,422)
        self.assertRegex(response.get_data(as_text=True),r'name="use_material"[^>]*checked')

    def test_validation_preserves_values_and_previous_valid_result(self):
        v=model_for('menu_pricing').defaults()
        self.post(self.client,'/menu-pricing/',v)
        r=self.post(self.client,'/menu-pricing/',v|{'margin':'100'})
        self.assertEqual(r.status_code,422)
        self.assertIn('value="100"',r.get_data(as_text=True))
        self.assertIn('계산 기준과 확인할 점',self.client.get('/menu-pricing/').get_data(as_text=True))

    def test_no_cross_module_internal_imports(self):
        for file in Path('app/modules').rglob('*.py'):
            own=file.parts[2]
            for node in ast.walk(ast.parse(file.read_text(encoding='utf-8'))):
                paths=[]
                if isinstance(node,ast.Import): paths=[n.name for n in node.names]
                if isinstance(node,ast.ImportFrom) and node.module: paths=[node.module]
                for path in paths:
                    if path.startswith('app.modules.'):
                        self.assertEqual(path.split('.')[2],own,str(file))


if __name__=='__main__': unittest.main()
