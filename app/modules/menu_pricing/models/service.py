from decimal import Decimal, InvalidOperation, ROUND_CEILING
import re
from app.common.db import utc_now
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
    PERIOD=re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')
    # Kasavana-Smith menu engineering: (popular, profitable) -> (label, suggestion)
    CLASSES={(True,True):('스타','지금 가격·품질을 유지하고 메뉴판에서 눈에 띄게 두세요.'),
             (True,False):('인기·저수익','원가를 줄이거나 소폭 가격 인상을 검토하세요.'),
             (False,True):('저인기·고수익','추천·위치·설명으로 노출을 늘려 보세요.'),
             (False,False):('저인기·저수익','메뉴 정리나 재구성을 검토하세요.')}

    def __init__(self,repository,material_provider: MaterialCostProvider | None = None,
                 material_catalog: MaterialCatalogProvider | None = None,recipes=None,sales=None,dineout=None):
        super().__init__(repository)
        # Optional DineOutProvider (average restaurant menu prices by region); unused until data is imported.
        self.dineout_provider=dineout
        self.material_provider=material_provider
        # Recipe costing needs both the saved-material list (material module) and a recipe store.
        self.material_catalog=material_catalog
        self.recipes=recipes if material_catalog else None
        self.sales=sales if self.recipes else None

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

    def save_recipe(self,workspace,name,items,other_cost=Decimal(0)):
        return self.recipes.save(workspace,name.strip(),items,other_cost) if self.recipes else None

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
        if self.recipes: self.recipes.forget(workspace)  # menu_sales go with their menus

    # ---- Monthly sales and menu engineering ----
    def sales_periods(self,workspace):
        return self.sales.periods(workspace) if self.sales else []

    def sales_for(self,workspace,period):
        return self.sales.for_period(workspace,period) if self.sales else {}

    def latest_prices(self,workspace):
        return self.sales.latest_prices(workspace) if self.sales else {}

    def save_sales(self,workspace,period,rows):
        """rows: [(menu_id, quantity_text, price_text)] for saved menus. Blank quantity skips the menu."""
        if not self.sales: return 0
        if not self.PERIOD.match(period or ''):
            raise ValidationError('판매 월을 YYYY-MM 형식으로 선택하세요.')
        names={menu['id']:menu['name'] for menu in self.list_menus(workspace)}
        clean,errors=[],[]
        for menu_id,quantity,price in rows:
            quantity,price=(quantity or '').strip(),(price or '').strip()
            if menu_id not in names or not quantity: continue
            try:
                qty,unit_price=Decimal(quantity),Decimal(price)
                if not (qty.is_finite() and unit_price.is_finite()) or qty<0 or qty!=qty.to_integral_value() or unit_price<0 or qty>Decimal(10**9) or unit_price>Decimal(10**12):
                    raise InvalidOperation
            except (InvalidOperation,ValueError):
                errors.append(f'{names[menu_id]}: 판매량은 0 이상의 정수, 판매가는 0 이상의 숫자로 입력하세요.'); continue
            clean.append((menu_id,qty,unit_price))
        if errors: raise ValidationError(' / '.join(errors))
        if not clean: raise ValidationError('판매량을 한 개 이상 입력하세요.')
        self.sales.save_period(workspace,period,clean)
        return len(clean)

    def delete_sales(self,workspace,period):
        return bool(self.sales and self.PERIOD.match(period or '') and self.sales.delete_period(workspace,period))

    def menu_engineering(self,workspace,period):
        """Classify each sold menu by popularity (share >= 70% of an equal share) and
        unit contribution margin (>= sales-weighted average). Costs use current recipe prices."""
        sold=self.sales_for(workspace,period)
        menus=[menu for menu in self.list_menus(workspace) if menu['id'] in sold and sold[menu['id']][0]>0]
        total_qty=sum((sold[m['id']][0] for m in menus),Decimal(0))
        if not menus or total_qty==0:
            return dict(period=period,rows=[],revenue=Decimal(0),material=Decimal(0),contribution=Decimal(0))
        rows=[]
        for menu in menus:
            qty,price=sold[menu['id']]
            unit_cost=menu['cost']+menu['other_cost']
            rows.append(dict(name=menu['name'],quantity=qty,share=qty/total_qty*100,price=price,material=menu['cost'],
                             unit_cost=unit_cost,margin=price-unit_cost,total_margin=(price-unit_cost)*qty,revenue=price*qty))
        popularity_line=Decimal(100)/len(rows)*Decimal('0.7')
        average_margin=sum((r['total_margin'] for r in rows),Decimal(0))/total_qty
        for row in rows:
            row['popular']=row['share']>=popularity_line
            row['profitable']=row['margin']>=average_margin
            row['label'],row['advice']=self.CLASSES[(row['popular'],row['profitable'])]
        rows.sort(key=lambda r:r['total_margin'],reverse=True)
        return dict(period=period,rows=rows,quantity=total_qty,popularity_line=popularity_line,average_margin=average_margin,
                    revenue=sum((r['revenue'] for r in rows),Decimal(0)),
                    material=sum((r['material']*r['quantity'] for r in rows),Decimal(0)),
                    contribution=sum((r['total_margin'] for r in rows),Decimal(0)))

    @property
    def dineout(self):
        provider=self.dineout_provider
        return provider if provider is not None and provider.available() else None

    def dineout_choices(self):
        return (self.dineout.menus(),self.dineout.regions()) if self.dineout else ([],[])

    def prepare(self,values,raw):
        """Attach the chosen restaurant menu average (or none) for the comparison tab."""
        values['dineout']=None
        menu=(raw.get('dine_menu') or 'none').strip()
        if not self.dineout or menu=='none': return values
        menus,regions=self.dineout_choices()
        region=(raw.get('dine_region') or ('서울' if '서울' in regions else regions[0])).strip()
        if menu not in menus or region not in regions:
            raise ValidationError('비교할 외식 메뉴와 지역을 목록에서 골라 주세요.')
        quote=self.dineout.quote(menu,region)
        values['dineout']=dict(menu=quote.menu,region=quote.region,month=quote.month,price=quote.price,
                               year_ago_price=quote.year_ago_price,source=quote.source) if quote else None
        return values

    @staticmethod
    def dineout_table(v,suggested):
        d=v.get('dineout')
        if not d: return None
        avg=Decimal(d['price'])
        def gap(price): return (price-avg)/avg*100
        change=(avg-d['year_ago_price'])/d['year_ago_price']*100 if d['year_ago_price'] else None
        rows=[['지역 평균 외식 가격',avg,'-','-'],['현재 가격',v['price'],v['price']-avg,gap(v['price'])],['계산 기준 가격',suggested,suggested-avg,gap(suggested)]]
        note=(f"출처: {d['source']}, {d['month']} 기준. 1년 전 대비 {change:+.1f}%." if change is not None else f"출처: {d['source']}, {d['month']} 기준.")
        note+=' 지역 대표 음식점의 평균 판매가이며 메뉴 구성·양·입지에 따라 차이가 큽니다. 가격 수준 참고용입니다. (내 PC 계산용)'
        return dict(tab='외식 가격 비교',title=f"{d['region']} {d['menu']} 평균 가격과 비교 ({d['month']})",
                    lead='내 가격이 지역 평균보다 얼마나 높거나 낮은지 보여 줍니다.',
                    columns=['구분','가격 (원)','평균과 차이 (원)','평균과 차이 (%)'],rows=rows,note=note)

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
                    extra_tables=[t for t in [self.dineout_table(v,suggested)] if t],menu_name=v['name'],monthly_revenue=v['price']*v['volume'],monthly_material=v['material']*v['volume'],monthly_volume=v['volume'],
                    notes=[f'반올림 전 가격 = 단위 변동 원가 ÷ (1 - 목표 공헌이익률) = {exact:,.2f}원. 표시 가격은 100원 단위 올림입니다.',
                           '공헌이익 = 매출 - 변동 원가. 임대료·인건비·세금 등을 차감한 순이익이 아닙니다.',
                           '모든 가격에서 입력 판매량을 동일하게 가정합니다. 가격에 따른 수요 변화나 실제 적정 시장 가격을 예측하지 않습니다.'])

    def export_operating_costs(self, workspace):
        periods = self.sales_periods(workspace)
        if periods:
            analysis = self.menu_engineering(workspace, periods[0])
            if analysis['rows']:
                return OperatingCostSnapshot(detail=f"{periods[0]} 판매 기록 (메뉴 {len(analysis['rows'])}개, 레시피 재료비)",
                                             source='사용자 판매 기록', updated_at=utc_now(),
                                             monthly_revenue=analysis['revenue'], monthly_material=analysis['material'])
        record = self.latest(workspace)
        if record is None or 'monthly_volume' not in record.result:
            return None
        result = record.result
        return OperatingCostSnapshot(detail=f"메뉴 '{result['menu_name']}' 월 {result['monthly_volume']:,.0f}개 기준", source=record.source,
                                     updated_at=record.updated_at, monthly_revenue=result['monthly_revenue'],
                                     monthly_material=result['monthly_material'])
