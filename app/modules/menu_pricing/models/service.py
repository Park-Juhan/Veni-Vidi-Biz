from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from app.common.model import AnalysisModel
from app.common.validation import Field
from app.integrations.contracts import MaterialCostProvider


# Price elasticity of demand (absolute value): % change in volume per 1% change in price.
ELASTICITY = {
    '낮음 0.8 · 단골·대체 메뉴 적음': Decimal('0.8'),
    '보통 1.5 · 일반적인 외식 메뉴': Decimal('1.5'),
    '높음 2.5 · 주변에 대체 메뉴 많음': Decimal('2.5'),
}
GRID_POINTS = 200


def _round100(value):
    return (value/100).to_integral_value(rounding=ROUND_CEILING)*100


class MenuPricingModel(AnalysisModel):
    fields=(
        Field('name','메뉴명','아메리카노','text'),
        Field('material','메뉴 1개 재료비 (원)','1200'),
        Field('other','메뉴 1개 기타 변동비 (원)','300',help='컵·포장비 등 판매 수량에 따라 드는 비용'),
        Field('margin','목표 공헌이익률 (%)','65',maximum='99.99'),
        Field('price','현재 판매가 (원)','4500'),
        Field('volume','월 예상 판매량 (개)','1000',step='1',maximum='1000000000',help='현재 판매가에서의 월 판매량'),
        Field('elasticity','가격 민감도 (수요의 가격탄력성)','보통 1.5 · 일반적인 외식 메뉴','select',choices=tuple(ELASTICITY),
              help='가격을 1% 올릴 때 판매량이 몇 % 줄어드는지에 대한 가정입니다.'),
    )

    def __init__(self,repository,material_provider: MaterialCostProvider | None = None):
        super().__init__(repository)
        self.material_provider=material_provider

    def import_material(self,workspace):
        return self.material_provider.export_usage_cost(workspace) if self.material_provider else None

    def calculate(self,v):
        cost=v['material']+v['other']
        exact=cost/(1-v['margin']/100)
        suggested=_round100(exact)
        e=ELASTICITY[v['elasticity']]
        p0,q0=v['price'],v['volume']
        demand_ready=p0>0 and q0>0

        def volume(price):
            # Constant-elasticity demand through the current point: Q = Q0 × (P / P0)^(-e).
            if not demand_ready: return q0
            if price<=0: return q0
            return (q0*(price/p0)**(-e)).quantize(Decimal(1),rounding=ROUND_HALF_UP)

        def scenario(label,price):
            q=volume(price);profit=price-cost
            return [label,price,q,price*q,profit,profit*q,profit/price*100 if price else '산출 불가']

        notes=[f'목표 이익률 기준 가격 = 단위 변동 원가 ÷ (1 - 목표 공헌이익률) = {exact:,.2f}원 → 100원 단위 올림.',
               '공헌이익 = 매출 - 변동 원가. 임대료·인건비·세금 등을 차감한 순이익이 아닙니다.']
        rows=[scenario('현재 가격',p0),scenario('목표 이익률 기준 가격',suggested)]
        metrics=[('목표 이익률 기준 가격',suggested,'원'),('단위 변동 원가',cost,'원')]
        charts=[]
        if demand_ready:
            # Search prices from just above cost to twice the current price for maximum monthly contribution.
            low=_round100(cost+1);high=max(_round100(p0*2),low)
            step=max(Decimal(100),_round100((high-low)/GRID_POINTS))
            grid=[];price=low
            while price<=high:
                grid.append((price,(price-cost)*volume(price)));price+=step
            best_price,best_profit=max(grid,key=lambda item:(item[1],-item[0]))
            rows.append(scenario('수요 반영 이익 최대 가격',best_price))
            current_profit=(p0-cost)*q0
            metrics+=[('수요 반영 이익 최대 가격',best_price,'원'),('현재 대비 월 공헌이익 변화',best_profit-current_profit,'원')]
            sample=grid[::max(1,len(grid)//8)]
            charts.append(dict(title=f'가격별 예상 월 공헌이익 (가격탄력성 {e})',unit='원',
                               data=[(f'{price:,.0f}원',profit) for price,profit in sample if profit>0]))
            notes+=[f'수요 모델: 일정 탄력성 수요곡선 Q = Q0 × (P ÷ P0)^(-{e}). 현재 판매가 {p0:,.0f}원에서 월 {q0:,.0f}개가 팔린다는 입력을 기준점으로 삼습니다.',
                    f'원가 바로 위부터 현재 가격의 2배까지 {step:,.0f}원 간격으로 월 공헌이익 = (가격 - 원가) × 예상 판매량이 최대인 가격을 찾습니다.']
            if e>1:
                lerner=cost*e/(e-1)
                notes.append(f'이론값(러너 지수·역탄력성 가격 규칙): 최적 가격 = 원가 × e ÷ (e - 1) = {lerner:,.0f}원. 탐색 결과와 같은 원리입니다.')
            if best_price>=high:
                notes.append('탄력성이 낮아 탐색 상한(현재 가격의 2배)에서 이익이 가장 큽니다. 실제로는 가격을 크게 올리면 고객 이탈이 급격해질 수 있으니 소폭 인상 후 판매량을 관찰하세요.')
            if volume(best_price)>q0*2:
                notes.append('이익 최대 가격에서 예상 판매량이 현재의 2배를 넘습니다. 수요곡선을 기준점에서 멀리 연장한 추정이므로 조리·좌석 수용 능력과 실제 반응을 확인하세요.')
            notes.append('가격탄력성은 선택한 가정값입니다. 실제 판매 기록(가격별 판매량)이 쌓이면 회귀 분석으로 추정해 교체하세요.')
        else:
            notes.append('현재 판매가 또는 판매량이 0이어서 수요 반응 모델을 적용할 수 없습니다. 모든 가격에서 입력 판매량을 동일하게 가정합니다.')
        charts.append(dict(title='시나리오별 월 공헌이익',unit='원',data=[(row[0],row[5]) for row in rows]))
        metrics.append(('기준 가격의 예상 월 공헌이익',rows[1][5],'원'))
        return dict(model='가격탄력성 수요 모델',metrics=metrics,
                    columns=['시나리오','판매가 (원)','예상 월 판매량','월 매출 (원)','단위 공헌이익 (원)','월 공헌이익 (원)','공헌이익률 (%)'],
                    rows=rows,charts=charts,notes=notes)
