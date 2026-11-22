"""Saved location candidates (01): storage, validation, selection and N-candidate TOPSIS."""
from decimal import Decimal
from html import unescape
import re
import unittest

from app.common.db import Database
from app.common.validation import ValidationError
from app.main.application import create_app
from app.modules.property.repositories.candidates import CandidateStore
from tests.module_support import model_for


def candidate(name, rent='1400000', fit='5'):
    return dict(name=name, rent=rent, deposit='10000000', area='32', interior='12000000', fit=fit, traffic='5', facility='2')


class CandidateModelTests(unittest.TestCase):
    def setUp(self):
        database = Database.in_memory()
        database.migrate()
        self.model = model_for('property')
        self.model.candidate_store = CandidateStore(database)

    def test_examples_until_candidates_are_saved(self):
        candidates, saved = self.model.candidates_for('w')
        self.assertFalse(saved)
        self.assertEqual([c['name'] for c in candidates], ['가상 역세권 A', '가상 주거지 B'])
        self.model.add_example_candidates('w')
        self.model.add_example_candidates('w')  # no duplicates
        self.assertEqual(len(self.model.list_candidates('w')), 2)
        self.assertTrue(self.model.candidates_for('w')[1])

    def test_validation_duplicates_and_edit(self):
        first = self.model.save_candidate('w', candidate('C'))
        for bad in (candidate('D', fit='6'), candidate('', rent='1'), candidate('E', rent='abc')):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                self.model.save_candidate('w', bad)
        with self.assertRaises(ValidationError):
            self.model.save_candidate('w', candidate('C'))  # same name
        self.model.save_candidate('w', candidate('C2', rent='900000'), first)
        [saved] = self.model.list_candidates('w')
        self.assertEqual((saved['name'], saved['rent']), ('C2', '900000'))
        with self.assertRaises(ValidationError):
            self.model.save_candidate('other', candidate('X'), first)  # another workspace cannot edit it
        self.assertTrue(self.model.delete_candidate('w', first))
        self.assertEqual(self.model.list_candidates('w'), [])

    def test_compares_selected_candidates_with_topsis(self):
        self.model.add_example_candidates('w')
        third = self.model.save_candidate('w', candidate('C'))
        everything, _ = self.model.candidates_for('w')
        result = self.model.analyze(self.model.defaults() | {'candidates': everything}, 'w').result
        self.assertEqual(len(result['rows']), 3)
        self.assertEqual(result['metrics'][3][1], 3)
        # C (rent within budget, best fit and traffic) ranks first among three.
        self.assertEqual(result['best_name'], 'C')
        self.assertEqual(len(result['extra_tables'][0]['columns']), 3 + 3 + 1)
        only_one, _ = self.model.candidates_for('w', {third})
        with self.assertRaises(ValidationError):
            self.model.analyze(self.model.defaults() | {'candidates': only_one}, 'w')
        pair = [candidate('Same'), candidate('Same')]
        with self.assertRaises(ValidationError):
            self.model.analyze(self.model.defaults() | {'candidates': pair}, 'w')


class CandidateHttpTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app({'TESTING': True}).test_client()
        self.client.get('/property/')
        with self.client.session_transaction() as session:
            self.token = session['csrf']

    def post(self, data, **kwargs):
        return self.client.post('/property/', data=data | {'csrf': self.token}, **kwargs)

    def add(self, item):
        return self.post({'action': 'save_candidate', **{'cand_' + k: v for k, v in item.items()}})

    def test_add_edit_select_and_delete(self):
        self.assertIn('가상 예시 2곳으로 비교합니다', self.client.get('/property/').get_data(as_text=True))
        self.add(candidate('후보 1', rent='1000000'))
        self.add(candidate('후보 2', rent='1300000', fit='3'))
        page = unescape(self.add(candidate('후보 3', rent='9000000')).get_data(as_text=True))
        self.assertIn("후보 '후보 3'을(를) 추가했습니다", page)
        bad = unescape(self.add(candidate('후보 1')).get_data(as_text=True))
        self.assertIn("같은 이름의 후보 '후보 1'", bad)
        self.assertIn('value="후보 1"', bad)  # typed values stay in the form

        ids = dict((name, cid) for cid, name in re.findall(r'name="compare" value="(\d+)" checked>\s*<span><b>([^<]+)</b>', page))
        form = model_for('property').defaults() | {'compare_sent': 'yes', 'compare': [ids['후보 1'], ids['후보 2']]}
        result = unescape(self.post(form, follow_redirects=True).get_data(as_text=True))
        self.assertIn('저장한 후보 2곳 비교', result)
        self.assertIn(f'name="compare" value="{ids["후보 3"]}" >', result)  # unticked stays unticked
        self.assertEqual(self.post(model_for('property').defaults() | {'compare_sent': 'yes', 'compare': [ids['후보 1']]}).status_code, 422)

        editing = unescape(self.post({'action': 'edit_candidate', 'candidate_id': ids['후보 2']}).get_data(as_text=True))
        self.assertIn('후보 수정', editing)
        self.post({'action': 'save_candidate', 'candidate_id': ids['후보 2'], **{'cand_' + k: v for k, v in candidate('후보 2', rent='800000').items()}})
        self.assertIn('<td><b>후보 2</b></td><td>800,000</td>', unescape(self.client.get('/property/').get_data(as_text=True)))
        page = unescape(self.post({'action': 'delete_candidate', 'candidate_id': ids['후보 3']}).get_data(as_text=True))
        self.assertIn('후보를 삭제했습니다', page)
        self.assertNotIn('<b>후보 3</b>', page)

        self.client.post('/workspace/', data={'csrf': self.token, 'action': 'delete', 'confirm': 'yes'})
        self.assertIn('저장한 후보가 없습니다', self.client.get('/property/').get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
