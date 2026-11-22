from decimal import Decimal, InvalidOperation, ROUND_CEILING
from app.common.model import AnalysisModel
from app.common.validation import Field, ValidationError
from app.integrations.contracts import MaterialCatalogProvider, MaterialCostProvider, OperatingCostSnapshot


class MenuPricingModel(AnalysisModel):
    fields=(
        Field('name','메뉴명','아메리카노','text'),
        Field('material','메뉴 1개 재료비 (원)','1200'),
        Field('other','메뉴 1개 기타 변동비 (원)','300',help='컵·포장비 등 판매 수량에 따라 드는 비용'),
        Field('margin','목표 공헌이익률 (%)','65',maximum='99.99'),
        Field('price','현재 판매가 (원)','4500'),
        Field('volume','월 예상 판매량 (개)','1000',step='1',maximum='1000000000'),
    )

    RECIPE_ROWS=6

    def __init__(self,repository,material_provider: MaterialCostProvider | None = None,
                 material_catalog: MaterialCatalogProvider | None = None,recipes=None):
        super().__init__(repository)
        self.material_provider=material_provider
        # Recipe costing needs both the saved-material list (material module) and a recipe store.
        self.material_catalog=material_catalog
        self.recipes=recipes if material_catalog else None

    def materials(self,workspace):
        return self.material_catalog.list_material_costs(workspace) if self.material_catalog else []

    def recipe_cost(self,workspace,rows):
        """rows: [(material_id_text, quantity_text)]. Blank rows are skipped.
        Returns (total cost, [(material_id, quantity, base_unit)], description)."""
        prices={str(item.material_id):item for item in self.materials(workspace)}
        total,items,parts,errors=Decimal(0),[],[],[]
        for index,(material_id,quantity) in enumerate(rows,start=1):
            material_id,quantity=(material_id or '').strip(),(quantity or '').strip()
            if not material_id and not quantity: continue
            item=prices.get(material_id)
            if item is None:
                errors.append(f'{index}번째 줄: 재료를 선택하세요.'); continue
            try:
                amount=Decimal(quantity)
                if not amount.is_finite() or not Decimal(0)<amount<=Decimal(1000000000): raise InvalidOperation
            except (InvalidOperation,ValueError):
                errors.append(f'{index}번째 줄 ({item.name}): 사용량을 0보다 큰 숫자로 입력하세요.'); continue
            if any(existing[0]==item.material_id for existing in items):
                errors.append(f'{index}번째 줄: {item.name}이(가) 두 번 들어 있습니다. 한 줄로 합쳐 주세요.'); continue
            total+=item.cost_per_base_unit*amount
            items.append((item.material_id,amount,item.base_unit))
            parts.append(f'{item.name} {amount:f}{item.base_unit}')
        if errors: raise ValidationError(' / '.join(errors))
        if not items: raise ValidationError('레시피에 재료를 한 줄 이상 입력하세요.')
        return total,items,' + '.join(parts)

    def save_recipe(self,workspace,name,items):
        return self.recipes.save(workspace,name.strip(),items) if self.recipes else None

    def list_menus(self,workspace):
        """Saved menus with recipe cost at the current saved material prices."""
        if not self.recipes: return []
        prices={item.material_id:item for item in self.materials(workspace)}
        menus=self.recipes.list(workspace)
        for menu in menus:
            menu['cost']=sum((prices[i['material_id']].cost_per_base_unit*i['quantity'] for i in menu['items'] if i['material_id'] in prices),Decimal(0))
        return menus

    def get_menu(self,workspace,menu_id):
        return self.recipes.get(workspace,menu_id) if self.recipes else None

    def delete_menu(self,workspace,menu_id):
        return bool(self.recipes and self.recipes.delete(workspace,menu_id))

    def forget(self,workspace):
        super().forget(workspace)
        if self.recipes: self.recipes.forget(workspace)

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
                    chart=[(label,price*v['volume']) for label,price in prices],chart_title='가격별 월 매출 비교 (동일 판매량 가정)',menu_name=v['name'],monthly_revenue=v['price']*v['volume'],monthly_material=v['material']*v['volume'],monthly_volume=v['volume'],
                    notes=[f'반올림 전 가격 = 단위 변동 원가 ÷ (1 - 목표 공헌이익률) = {exact:,.2f}원. 표시 가격은 100원 단위 올림입니다.',
                           '공헌이익 = 매출 - 변동 원가. 임대료·인건비·세금 등을 차감한 순이익이 아닙니다.',
                           '모든 가격에서 입력 판매량을 동일하게 가정합니다. 가격에 따른 수요 변화나 실제 적정 시장 가격을 예측하지 않습니다.'])

    def export_operating_costs(self, workspace):
        record = self.latest(workspace)
        if record is None or 'monthly_volume' not in record.result:
            return None
        result = record.result
        return OperatingCostSnapshot(detail=f"메뉴 '{result['menu_name']}' 월 {result['monthly_volume']:,.0f}개 기준", source=record.source,
                                     updated_at=record.updated_at, monthly_revenue=result['monthly_revenue'],
                                     monthly_material=result['monthly_material'])
