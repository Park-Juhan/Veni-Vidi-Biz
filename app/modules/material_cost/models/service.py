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
        return dict(metrics=[('총 구매 비용',total,'원'),('기준 단위 원가',base,'원 / '+base_unit),('1회 사용 원가',cost,'원')],
                    columns=['재료','총 구매량','기준 단가 (원)','1회 사용량','사용 원가 (원)'],
                    rows=[[v['name'],f"{amount} {base_unit}",base,f"{used} {base_unit}",cost]],
                    chart=[('사용분 원가',cost),('남은 재료 원가',total-cost)],chart_title='구매 비용 구성',
                    notes=['총 구매 비용 = 구매 단가 × 구매 수량. 사용 원가 = 기준 단위 원가 × 1회 사용량.', '밀도·폐기율은 반영하지 않습니다. 질량과 부피를 서로 변환하지 않습니다.', '메뉴 모듈로 가져오면 이 재료의 1회 사용 원가를 재료비로 사용합니다. 여러 재료의 레시피 합산은 후속 기능입니다.'],
                    usage_cost=cost)

    def export_usage_cost(self,workspace):
        record=self.latest(workspace)
        if record is None: return None
        return MaterialCostSnapshot(record.result['usage_cost'],record.source,record.updated_at)
