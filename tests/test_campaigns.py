"""Campaign log (04): validation, per-campaign metrics, channel summary and use in recommendations."""
from decimal import Decimal
from html import unescape
import re
import unittest

from app.common.db import Database
from app.common.validation import ValidationError
from app.main.application import create_app
from app.modules.marketing.repositories.campaigns import CampaignStore
from tests.module_support import model_for


def campaign(name, channel='동네 소식·재방문 쿠폰', cost='100000', customers='20', before='', after='', **extra):
    return dict(name=name, channel=channel, owner='직접', started_on='2026-10-01', ended_on='2026-10-14', cost=cost,
                hours_per_week='2', new_customers=customers, revenue_before=before, revenue_after=after, note='') | extra


class CampaignModelTests(unittest.TestCase):
    def setUp(self):
        database = Database.in_memory()
        database.migrate()
        self.model = model_for('marketing')
        self.model.campaign_store = CampaignStore(database)

    def test_metrics_and_validation(self):
        self.model.save_campaign('w', campaign('쿠폰', before='3000000', after='3400000'))
        [c] = self.model.list_campaigns('w')
        self.assertEqual(c['days'], 14)
        self.assertEqual(c['cac'], Decimal(5000))            # 100,000 / 20
        self.assertEqual(c['lift'], Decimal(400000))
        self.assertEqual(c['roi'], Decimal(300))             # (400,000 - 100,000) / 100,000
        self.model.save_campaign('w', campaign('측정 안 함', customers=''))
        unmeasured = next(c for c in self.model.list_campaigns('w') if c['name'] == '측정 안 함')
        self.assertIsNone(unmeasured['cac'])
        self.assertIsNone(unmeasured['roi'])
        for bad in (campaign('A', ended_on='2026-09-30'), campaign('B', started_on='10/01'), campaign('C', customers='1.5'),
                    campaign('D', before='100'), campaign('E', channel='TV'), campaign('', cost='1'), campaign('F', cost='-1')):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                self.model.save_campaign('w', bad)
        self.assertEqual(self.model.list_campaigns('other'), [])

    def test_channel_summary_ranks_by_cost_per_customer(self):
        self.model.save_campaign('w', campaign('쿠폰 1', cost='100000', customers='20'))
        self.model.save_campaign('w', campaign('쿠폰 2', cost='50000', customers='5'))
        self.model.save_campaign('w', campaign('광고', channel='지역 타깃 광고 대행', cost='400000', customers='100'))
        self.model.save_campaign('w', campaign('SNS', channel='매장 소식·SNS 직접 운영', cost='0', customers=''))
        summary = self.model.channel_summary('w')
        self.assertEqual([s['channel'] for s in summary], ['지역 타깃 광고 대행', '동네 소식·재방문 쿠폰', '매장 소식·SNS 직접 운영'])
        coupons = summary[1]
        self.assertEqual((coupons['runs'], coupons['cost'], coupons['customers'], coupons['cac']), (2, Decimal(150000), Decimal(25), Decimal(6000)))
        self.assertIsNone(summary[2]['cac'])

    def test_recommendation_shows_own_history(self):
        self.model.save_campaign('w', campaign('쿠폰', before='3000000', after='3400000'))
        result = self.model.analyze(self.model.defaults() | {'history': self.model.channel_summary('w')}, 'w').result
        own = {row[0]: row[6] for row in result['rows']}
        self.assertEqual(own['동네 소식·재방문 쿠폰'], '1회 · 총 100,000원 · 신규 1명당 5,000원 · 수익률 300%')
        self.assertEqual(own['지역 타깃 광고 대행'], '기록 없음')
        self.assertEqual(model_for('marketing').analyze(model_for('marketing').defaults(), 'w').result['rows'][0][6], '기록 없음')


class CampaignHttpTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app({'TESTING': True}).test_client()
        self.client.get('/marketing/')
        with self.client.session_transaction() as session:
            self.token = session['csrf']

    def post(self, data, **kwargs):
        return self.client.post('/marketing/', data=data | {'csrf': self.token}, **kwargs)

    def save(self, item, campaign_id=None):
        data = {'action': 'save_campaign', **{'camp_' + k: v for k, v in item.items()}}
        if campaign_id: data['campaign_id'] = campaign_id
        return unescape(self.post(data).get_data(as_text=True))

    def test_log_edit_delete_and_recommend(self):
        page = self.save(campaign('11월 쿠폰', customers='25'))
        self.assertIn("캠페인 '11월 쿠폰'을(를) 기록했습니다", page)
        self.assertIn('<td>4,000</td>', page)  # 100,000 / 25
        bad = self.save(campaign('잘못된 기간', ended_on='2026-09-01'))
        self.assertIn('종료일이 시작일보다 빠릅니다', bad)
        self.assertIn('value="잘못된 기간"', bad)

        campaign_id = re.search(r'name="campaign_id" value="(\d+)"', page).group(1)
        self.assertIn('캠페인 수정', unescape(self.post({'action': 'edit_campaign', 'campaign_id': campaign_id}).get_data(as_text=True)))
        page = self.save(campaign('11월 쿠폰', customers='50'), campaign_id)
        self.assertIn('<td>2,000</td>', page)

        result = unescape(self.post(model_for('marketing').defaults(), follow_redirects=True).get_data(as_text=True))
        self.assertIn('내 캠페인 기록 1건 참고', result)
        self.assertIn('1회 · 총 100,000원 · 신규 1명당 2,000원', result)

        page = unescape(self.post({'action': 'delete_campaign', 'campaign_id': campaign_id}).get_data(as_text=True))
        self.assertIn('캠페인 기록을 삭제했습니다', page)
        self.assertIn('아직 기록한 캠페인이 없습니다', page)


if __name__ == '__main__':
    unittest.main()
