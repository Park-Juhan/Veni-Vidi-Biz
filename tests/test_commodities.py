"""International coffee futures (aT FIS) shown next to coffee materials (02)."""
import csv
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from app.common.db import Database
from app.main.application import create_app
from app.modules.material_cost.repositories.catalog import MaterialCatalog
from app.reference import commodities
from app.reference.commodities import CommodityPrices
from tests.module_support import model_for


def loaded(weeks=53):
    database = Database.in_memory(); database.migrate()
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'aTFIS_국제원료_커피아라비카_주간.csv'
        with path.open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.writer(handle); writer.writerow(commodities.COLUMNS)
            # Newest first: 300 now, 250 four weeks ago, 400 a year (52 weeks) ago.
            for i in range(weeks):
                price = 300 if i == 0 else 250 if i == 4 else 400 if i == 52 else 280
                writer.writerow(['커피(아라비카)', f'week-{999 - i:03d}', price, price * 22.0462])
        assert commodities.is_commodity(path)
        commodities.import_file(database, path)
    return database, CommodityPrices(database)


class CommodityTests(unittest.TestCase):
    def test_trend_by_material_name(self):
        _, prices = loaded()
        trend = prices.trend_for('에티오피아 원두')
        self.assertEqual((trend.commodity, trend.cents_per_lb), ('커피(아라비카)', Decimal(300)))
        self.assertEqual((trend.change_4w, trend.change_52w), (Decimal(20), Decimal(-25)))
        self.assertEqual(round(trend.usd_per_kg, 2), Decimal('6.61'))
        self.assertIsNone(prices.trend_for('양파'))
        _, short = loaded(weeks=3)
        self.assertIsNone(short.trend_for('커피').change_52w)

    def test_dish_advice_material_list_and_page(self):
        database, prices = loaded()
        model = model_for('material_cost')
        model.catalog, model.commodity_provider = MaterialCatalog(database), prices
        record = model.analyze(model.defaults(), 'w')   # 카페라떼 uses 원두
        self.assertTrue(any('국제 커피(아라비카) 시세가 1년 전보다 25% 내렸습니다' in line for line in record.result['advice']))
        model.remember('w', record)
        beans = next(i for i in model.list_materials('w') if i['name'] == '원두')
        self.assertEqual(beans['commodity']['change_52w'], Decimal(-25))

        client = create_app({'TESTING': True, 'COMMODITIES': prices}).test_client()
        client.get('/material-cost/')
        with client.session_transaction() as session:
            token = session['csrf']
        client.post('/material-cost/', data=model_for('material_cost').defaults() | {'csrf': token})
        page = client.get('/material-cost/').get_data(as_text=True)
        self.assertIn('국제 커피(아라비카)', page)
        self.assertIn('-25%', page)
        self.assertIn('aT 식품산업통계정보(FIS)', page)


if __name__ == '__main__':
    unittest.main()
