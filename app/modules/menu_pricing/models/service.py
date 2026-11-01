from decimal import Decimal, ROUND_CEILING
from app.common.model import AnalysisModel
from app.common.validation import Field
from app.integrations.contracts import MaterialCostProvider


class MenuPricingModel(AnalysisModel):
    fields=(
        Field('name','메뉴명','아메리카노','text'),
        Field('material','메뉴 1개 재료비 (원)','1200'),
        Field('other','메뉴 1개 기타 변동비 (원)','300',help='컵·포장비 등 판매 수량에 따라 드는 비용'),
        Field('margin','목표 공헌이익률 (%)','65',maximum='99.99'),
        Field('price','현재 판매가 (원)','4500'),
        Field('volume','월 예상 판매량 (개)','1000',step='1',maximum='1000000000'),
    )

    def __init__(self,repository,material_provider: MaterialCostProvider | None = None):
        super().__init__(repository)
        self.material_provider=material_provider

    def import_material(self,workspace):
        return self.material_provider.export_usage_cost(workspace) if self.material_provider else None

    def calculate(self,v):
        cost=v['material']+v['other']
        exact=cost/(1-v['margin']/100)
        suggested=(exact/100).to_integral_value(rounding=ROUND_CEILING)*100
        prices=[('현재 가격',v['price']),('계산 기준 가격',suggested),('기준 + 500원',suggested+500)]
        rows=[]
        for label,price in prices:
            profit=price-cost
            rows.append([label,price,v['volume'],price*v['volume'],profit,profit*v['volume'],profit/price*100 if price else '산출 불가'])
        return dict(metrics=[('100원 단위 올림 가격',suggested,'원'),('단위 변동 원가',cost,'원'),('기준 가격의 월 공헌이익',(suggested-cost)*v['volume'],'원')],
                    columns=['시나리오','판매가 (원)','월 판매량','월 매출 (원)','단위 공헌이익 (원)','월 공헌이익 (원)','공헌이익률 (%)'],rows=rows,
                    chart=[(label,price*v['volume']) for label,price in prices],chart_title='가격별 월 매출 비교 (동일 판매량 가정)',
                    notes=[f'반올림 전 가격 = 단위 변동 원가 ÷ (1 - 목표 공헌이익률) = {exact:,.2f}원. 표시 가격은 100원 단위 올림입니다.',
                           '공헌이익 = 매출 - 변동 원가. 임대료·인건비·세금 등을 차감한 순이익이 아닙니다.',
                           '모든 가격에서 입력 판매량을 동일하게 가정합니다. 가격에 따른 수요 변화나 실제 적정 시장 가격을 예측하지 않습니다.'])
