from decimal import Decimal
from app.common.model import AnalysisModel
from app.common.validation import Field, ValidationError
from app.integrations.contracts import MaterialCostSnapshot


UNITS = {'kg': ('mass',Decimal(1000)), 'g': ('mass',Decimal(1)), 'L': ('volume',Decimal(1000)), 'mL': ('volume',Decimal(1)), '개': ('count',Decimal(1))}


class MaterialCostModel(AnalysisModel):
    fields=(
        Field('name','재료명','원두','text'),
        Field('purchase_price','구매 단가 (구매 단위 1개당 원)','20000', help='예: 1kg당 20,000원. 배송비·세금은 단가에 포함해 입력하세요.'),
        Field('quantity','구매 수량 (구매 단위 기준)','2',minimum='0.000001',maximum='1000000000'),
        Field('unit','구매 단위','kg','select',choices=tuple(UNITS)),
        Field('usage','1회 사용량','18',maximum='1000000000'),
        Field('usage_unit','사용량 단위','g','select',choices=tuple(UNITS)),
        Field('monthly_uses','월 사용 횟수','3000',maximum='1000000000',group='발주 계획 (EOQ)',help='한 달 동안 1회 사용량만큼 쓰는 횟수. 예: 아메리카노 월 판매량'),
        Field('order_cost','1회 주문 비용 (원)','3000',group='발주 계획 (EOQ)',help='배송비·주문 처리 시간 등 주문 한 번마다 드는 비용'),
        Field('holding_rate','월 보관 비용률 (%)','2',maximum='100',group='발주 계획 (EOQ)',help='구매 단가 대비 한 달 보관에 드는 비용(공간·냉장·묶인 자금·손실)'),
        Field('shelf_months','보관 가능 기간 (개월)','1',minimum='0.01',maximum='120',group='발주 계획 (EOQ)',help='품질을 유지할 수 있는 최대 보관 기간'),
    )

    def calculate(self,v):
        dimension,factor=UNITS[v['unit']]
        use_dimension,use_factor=UNITS[v['usage_unit']]
        if dimension!=use_dimension:
            raise ValidationError('구매 단위와 사용량 단위의 차원이 다릅니다. kg↔g, L↔mL, 개↔개만 환산할 수 있습니다.')
        total=v['purchase_price']*v['quantity']
        amount=v['quantity']*factor
        used=v['usage']*use_factor
        if used>amount:
            raise ValidationError('1회 사용량이 총 구매량보다 큽니다.')
        base=total/amount
        cost=base*used
        base_unit={'mass':'g','volume':'mL','count':'개'}[dimension]
        plan=self.order_plan(v,used/factor)
        notes=['총 구매 비용 = 구매 단가 × 구매 수량. 사용 원가 = 기준 단위 원가 × 1회 사용량.', '밀도·폐기율은 반영하지 않습니다. 질량과 부피를 서로 변환하지 않습니다.', '메뉴 모듈로 가져오면 이 재료의 1회 사용 원가를 재료비로 사용합니다. 여러 재료의 레시피 합산은 후속 기능입니다.']
        metrics=[('총 구매 비용',total,'원'),('기준 단위 원가',base,'원 / '+base_unit),('1회 사용 원가',cost,'원')]
        rows=[[v['name'],f"{amount} {base_unit}",base,f"{used} {base_unit}",cost]]
        charts=[dict(title='구매 비용 구성',unit='원',data=[('사용분 원가',cost),('남은 재료 원가',total-cost)])]
        if plan:
            unit=v['unit']
            metrics+=[('권장 1회 주문량 (EOQ)',plan['q'],unit),('월 주문 횟수',plan['orders'],'회'),('발주 방식 변경 시 월 절감액',plan['saving'],'원')]
            notes+=[f"경제적 주문량 EOQ = √(2 × 월 수요 D × 1회 주문 비용 S ÷ 월 보관 비용 H). D = {plan['demand']:,.2f}{unit}, H = 구매 단가 × 보관 비용률 = {plan['holding']:,.2f}원/{unit}.",
                    f"월 발주 관련 비용 = (D ÷ 주문량) × S + (주문량 ÷ 2) × H. 현재 구매 수량 {v['quantity']}{unit}씩 주문하면 {plan['current_cost']:,.0f}원, 권장 주문량이면 {plan['best_cost']:,.0f}원입니다.",
                    'EOQ는 수요가 일정하고 주문 즉시 입고된다는 가정입니다. 수량 할인·최소 주문량·리드타임 안전재고는 반영하지 않습니다.']
            if plan['capped']:
                notes.append(f"보관 가능 기간 {v['shelf_months']}개월을 넘지 않도록 주문량을 월 수요 × 보관 가능 기간으로 제한했습니다.")
            charts.append(dict(title='주문량별 월 발주·보관 비용',unit='원',data=[('현재 주문량',plan['current_cost']),('권장 주문량 (EOQ)',plan['best_cost'])]))
        else:
            notes.append('월 사용 횟수·주문 비용·보관 비용률 중 0이 있어 경제적 주문량(EOQ)을 계산하지 않았습니다.')
        return dict(model='경제적 주문량 (EOQ) 모델' if plan else '원가 계산',metrics=metrics,
                    columns=['재료','총 구매량','기준 단가 (원)','1회 사용량','사용 원가 (원)'],rows=rows,charts=charts,notes=notes,
                    usage_cost=cost,eoq=plan['q'] if plan else None)

    @staticmethod
    def order_plan(v,use_per_purchase_unit):
        """Classic EOQ (Harris, 1913) in purchase units per month, capped by shelf life."""
        demand=v['monthly_uses']*use_per_purchase_unit
        holding=v['purchase_price']*v['holding_rate']/100
        if demand<=0 or v['order_cost']<=0 or holding<=0:
            return None
        eoq=(2*demand*v['order_cost']/holding).sqrt()
        cap=demand*v['shelf_months']
        q=min(eoq,cap)
        def monthly(quantity): return demand/quantity*v['order_cost']+quantity/2*holding
        current=monthly(v['quantity']);best=monthly(q)
        return dict(q=q,orders=demand/q,demand=demand,holding=holding,current_cost=current,best_cost=best,saving=current-best,capped=eoq>cap)

    def export_usage_cost(self,workspace):
        record=self.latest(workspace)
        if record is None: return None
        return MaterialCostSnapshot(record.result['usage_cost'],record.source,record.updated_at)
