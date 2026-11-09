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

    def test_portfolio_respects_budget_and_hours(self):
        model=model_for('marketing')
        r=model.analyze(model.defaults()|{'budget':'600000','hours':'8'},'a').result
        metrics={m[0]:m[1] for m in r['metrics']}
        self.assertEqual(metrics['추천 조합'],'지역 타깃 광고 대행 + 동네 소식·재방문 쿠폰')
        self.assertLessEqual(metrics['추천 조합 월 비용'],600000)
        self.assertLessEqual(metrics['추천 조합 주당 시간'],8)
        # 500,000 / (8,000 x 60%) = 104.2 -> 105 extra customers per month.
        self.assertEqual(metrics['비용 회수에 필요한 추가 고객'],Decimal(105))
        self.assertEqual(r['model'],'채널 조합 최적화 (배낭 문제)')

    def test_breakeven_needs_positive_contribution(self):
        model=model_for('marketing')
        r=model.analyze(model.defaults()|{'contribution_rate':'0'},'a').result
        self.assertTrue(all(row[6]=='산출 불가' for row in r['rows']))
        none=model.analyze(model.defaults()|{'budget':'0','hours':'0'},'a').result
        self.assertEqual(none['metrics'][1][1],'없음')


if __name__ == "__main__":
    unittest.main()
