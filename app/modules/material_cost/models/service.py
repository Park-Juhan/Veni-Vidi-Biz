from decimal import Decimal
from app.common.model import AnalysisModel
from app.common.validation import Field, ValidationError, validate
from app.integrations.contracts import MaterialCostItem, MaterialCostSnapshot


UNITS = {'kg': ('mass',Decimal(1000)), 'g': ('mass',Decimal(1)), 'L': ('volume',Decimal(1000)), 'mL': ('volume',Decimal(1)), '개': ('count',Decimal(1))}
BASE_UNIT = {'mass':'g','volume':'mL','count':'개'}


class MaterialCostModel(AnalysisModel):
    fields=(
        Field('name','재료명','원두','text'),
        Field('purchase_price','구매 단가 (구매 단위 1개당 원)','20000', help='예: 1kg당 20,000원. 배송비·세금은 단가에 포함해 입력하세요.'),
        Field('quantity','구매 수량 (구매 단위 기준)','2',minimum='0.000001',maximum='1000000000'),
        Field('unit','구매 단위','kg','select',choices=tuple(UNITS)),
        Field('usage','1회 사용량','18',maximum='1000000000'),
        Field('usage_unit','사용량 단위','g','select',choices=tuple(UNITS)),
        Field('yield_rate','수율 (%)','100',minimum='1',maximum='100',
              help='손질·폐기 후 실제로 쓸 수 있는 비율. 예: 껍질·꼭지를 버려 70%만 쓰면 70. 손실이 없으면 100.'),
    )

    def __init__(self,repository,catalog=None,prices=None):
        super().__init__(repository)
        # Optional saved-material list (needs a database); None disables it.
        self.catalog=catalog
        # Optional MarketPriceProvider (public retail prices); unused until data is imported.
        self.price_provider=prices

    @property
    def prices(self):
        provider=self.price_provider
        return provider if provider is not None and provider.available() else None

    def market_options(self):
        return self.prices.options() if self.prices else []

    def compare_market(self,item):
        """Market comparison for one listed material: the linked (or name-matched) series and price gap."""
        if not self.prices or item.get('market_item')=='':
            return None
        key=item.get('market_item') or self.prices.suggest(item['name'],item['base_unit'])
        quote=self.prices.quote(key) if key else None
        if quote is None:
            return None
        dimension,factor=UNITS[item['unit']]
        mine=item['unit_price']/factor  # purchase price per base unit, before yield (market prices are as sold)
        comparable=quote.price_per_base is not None and quote.base_unit==BASE_UNIT[dimension]
        gap=(mine-quote.price_per_base)/quote.price_per_base*100 if comparable and quote.price_per_base else None
        change=(Decimal(quote.price)-quote.year_ago_price)/quote.year_ago_price*100 if quote.year_ago_price else None
        return dict(key=quote.key,label=quote.label,auto=not item.get('market_item'),month=quote.month,unit=quote.unit,price=quote.price,
                    seoul_price=quote.seoul_price,per_base=quote.price_per_base if comparable else None,mine_per_base=mine,
                    gap=gap,change=change,comparable=comparable,source=quote.source)

    def set_market_item(self,workspace,material_id,text):
        """Link by option label/key; 'auto' resets to name matching, 'none' turns comparison off."""
        if not self.catalog or not self.prices: return False
        text=(text or '').strip()
        if text in ('','auto'): key=None
        elif text=='none': key=''
        else:
            key=next((o.key for o in self.prices.options() if text in (o.label,o.key)),None)
            if key is None:
                raise ValidationError(f"시세 품목 '{text}'을(를) 찾지 못했습니다. 입력란에서 목록에 나오는 품목을 골라 주세요.")
        return bool(self.catalog.set_market_item(workspace,material_id,key))

    @staticmethod
    def base_unit_cost(unit,unit_price,yield_rate):
        """Price per usable base unit (g, mL, 개) for a price per purchase unit, yield applied."""
        dimension,factor=UNITS[unit]
        return BASE_UNIT[dimension],unit_price/factor*100/yield_rate

    def save_material(self,workspace,raw):
        """Store the calculator's material as a purchase in the workspace's material list."""
        if not self.catalog: return None
        v=validate(self.fields,raw)
        return self.catalog.save_purchase(workspace,v['name'].strip(),v['unit'],v['yield_rate'],v['purchase_price'],v['quantity'])

    def list_materials(self,workspace,with_market=True):
        if not self.catalog: return []
        materials=self.catalog.list(workspace)
        for item in materials:
            item['base_unit'],item['cost_per_base_unit']=self.base_unit_cost(item['unit'],item['unit_price'],item['yield_rate'])
            item['market']=self.compare_market(item) if with_market else None
        return materials

    def delete_material(self,workspace,material_id):
        return bool(self.catalog and self.catalog.delete(workspace,material_id))

    def list_material_costs(self,workspace):
        """Public contract for other modules: saved materials priced per usable base unit."""
        return [MaterialCostItem(item['id'],item['name'],item['base_unit'],item['cost_per_base_unit'],item['purchased_at'])
                for item in self.list_materials(workspace,with_market=False)]

    def forget(self,workspace):
        super().forget(workspace)
        if self.catalog: self.catalog.forget(workspace)

    def calculate(self,v):
        dimension,factor=UNITS[v['unit']]
        use_dimension,use_factor=UNITS[v['usage_unit']]
        if dimension!=use_dimension:
            raise ValidationError('구매 단위와 사용량 단위의 차원이 다릅니다. kg↔g, L↔mL, 개↔개만 환산할 수 있습니다.')
        total=v['purchase_price']*v['quantity']
        amount=v['quantity']*factor
        used=v['usage']*use_factor
        usable=amount*v['yield_rate']/100
        if used>usable:
            raise ValidationError('1회 사용량이 수율을 반영한 사용 가능량보다 큽니다.')
        base=total/amount
        # Waste raises the cost of every usable unit: price per usable unit = price per bought unit / yield.
        effective=base*100/v['yield_rate']
        cost=effective*used
        loss=cost-base*used
        base_unit=BASE_UNIT[dimension]
        return dict(metrics=[('총 구매 비용',total,'원'),('기준 단위 원가',base,'원 / '+base_unit),('수율 반영 단위 원가',effective,'원 / '+base_unit),('1회 사용 원가',cost,'원')],
                    columns=['재료','총 구매량','수율 (%)','사용 가능량','기준 단가 (원)','수율 반영 단가 (원)','1회 사용량','사용 원가 (원)'],
                    rows=[[v['name'],f"{amount} {base_unit}",v['yield_rate'],f"{usable} {base_unit}",base,effective,f"{used} {base_unit}",cost]],
                    chart=[('1회 사용분 원가',base*used),('1회 사용분의 손질·폐기 손실',loss),('남은 재료 원가',total-cost)],chart_title='구매 비용 구성',
                    notes=['총 구매 비용 = 구매 단가 × 구매 수량. 사용 원가 = 기준 단위 원가 × 1회 사용량.', '수율 반영 단위 원가 = 기준 단위 원가 ÷ 수율. 손질·폐기로 버리는 양의 비용을 실제 사용하는 양이 부담합니다.',
                           '수율은 사용자가 입력한 값입니다. 재료·손질 방법에 따라 다르니 실제로 측정해 보는 것이 좋습니다. 밀도는 반영하지 않으며 질량과 부피를 서로 변환하지 않습니다.', '메뉴 모듈로 가져오면 이 재료의 1회 사용 원가를 재료비로 사용합니다. 여러 재료를 합산하려면 재료를 내 재료 목록에 저장한 뒤 메뉴 모듈의 레시피 계산을 쓰세요.'],
                    usage_cost=cost)

    def export_usage_cost(self,workspace):
        record=self.latest(workspace)
        if record is None: return None
        return MaterialCostSnapshot(record.result['usage_cost'],record.source,record.updated_at)
