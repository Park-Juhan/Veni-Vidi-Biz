from decimal import Decimal
import unittest

from app.common.validation import ValidationError
from tests.module_support import StandaloneModuleChecks, model_for


class MarketingTests(StandaloneModuleChecks, unittest.TestCase):
    module_name = 'marketing'

    def test_marketing_no_feasible_channel(self):
        model=model_for('marketing')
        r=model.analyze(model.defaults()|{'budget':'0','hours':'0'},'a').result
        self.assertEqual(r['metrics'][0][1],0)
        self.assertTrue(any('맞는 방법이 없습니다' in note for note in r['notes']))


if __name__ == "__main__":
    unittest.main()
