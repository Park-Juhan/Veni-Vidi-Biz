from decimal import Decimal, InvalidOperation, ROUND_CEILING
import re
from app.common.db import utc_now
from app.common.model import AnalysisModel
from app.common.validation import Field, ValidationError
from app.integrations.contracts import DishCostProvider, LocationProvider, OperatingCostSnapshot

DAYS = Decimal(30)
# 02 dish name -> 외식비 survey menu (행정안전부 지방물가), for the price comparison tab.
DINEOUT_MENUS = {'김치찌개': '김치찌개 백반', '짜장면': '자장면', '칼국수': '칼국수', '김밥': '김밥', '비빔밥': '비빔밥', '삼겹살 1인분': '삼겹살 (200g 환산)'}


def won(value):
    return value.quantize(Decimal(1))


class MenuPricingModel(AnalysisModel):
    result_key='advice'
    fields=(
        Field('dish','메뉴','아메리카노','text'),
        Field('material','1개 재료비 (원)','500',help='재료비 관리(02)에서 음식을 계산하면 이 값은 자동으로 채워집니다.'),
        Field('price','판매가 (원)','5000',minimum='1'),
        Field('volume','월 예상 판매량 (개)','900',step='1',minimum='1',maximum='1000000000',help='02에서 정한 판매량을 가져옵니다. 하루 30개 × 30일 = 900개.'),
        Field('other','기타 변동비 (원/개)','400',group='비용',help='컵·뚜껑·포장재·카드 수수료처럼 1개 팔 때마다 드는 비용입니다.'),
        Field('rent','월 임대료 (원)','1800000',group='비용'),
        Field('labor','월 인건비 (원)','3000000',group='비용',help='직원 급여와 4대 보험. 사장님 본인 몫을 넣으면 실제로 남는 돈을 볼 수 있습니다.'),
        Field('fixed_other','기타 월 고정비 (원)','700000',group='비용',help='공과금·관리비·통신·보험·세무 등.'),
    )

    PERIOD=re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')
    # Kasavana-Smith menu engineering: (popular, profitable) -> (label, suggestion)
    CLASSES={(True,True):('스타','지금 가격·품질을 유지하고 메뉴판에서 눈에 띄게 두세요.'),
             (True,False):('인기·저수익','원가를 줄이거나 소폭 가격 인상을 검토하세요.'),
             (False,True):('저인기·고수익','추천·위치·설명으로 노출을 늘려 보세요.'),
             (False,False):('저인기·저수익','메뉴 정리나 재구성을 검토하세요.')}

    def __init__(self,repository,dishes: DishCostProvider | None = None,location: LocationProvider | None = None,
                 recipes=None,sales=None,dineout=None):
        super().__init__(repository)
        self.dish_provider=dishes          # 02: analysed dishes and their ingredient cost
        self.location_provider=location    # 01: chosen area's rent and average sales per store
        self.recipes=recipes               # menus priced here (names, other cost) for the sales records
        self.sales=sales if recipes else None
        self.dineout_provider=dineout

    # ---- Inputs from other modules ----
    def dishes(self,workspace):
        return self.dish_provider.list_dishes(workspace) if self.dish_provider else []

    def location(self,workspace):
        return self.location_provider.export_location(workspace) if self.location_provider else None

    def defaults_for(self,workspace):
        """Defaults filled from 02 (latest dish and its volume) and 01 (rent of the top area)."""
        values=self.defaults()
        dishes=self.dishes(workspace)
        if dishes:
            values.update(dish=dishes[0].name,volume=f'{dishes[0].monthly_volume.normalize():f}',
                          price=f'{self.suggested_price(dishes[0].cost_per_serving):f}')
        place=self.location(workspace)
        if place: values['rent']=f'{place.monthly_rent.normalize():f}'
        return values

    @staticmethod
    def suggested_price(cost):
        """A starting price at a 30% food cost ratio, rounded up to 500 원."""
        return (cost/Decimal('0.3')/500).to_integral_value(rounding=ROUND_CEILING)*500

    @property
    def dineout(self):
        provider=self.dineout_provider
        return provider if provider is not None and provider.available() else None

    def prepare(self,values,raw):
        """Ingredient cost comes from the dish analysed in 02; typed by hand only while 02 has no dishes."""
        workspace=raw.get('_workspace')
        dishes=self.dishes(workspace) if workspace else []
        name=values['dish'].strip()
        found=next((d for d in dishes if d.name==name),None)
        if dishes and found is None:
            raise ValidationError('메뉴를 목록에서 고르세요. 새 메뉴는 재료비 관리(02)에서 먼저 계산하세요.')
        place=self.location(workspace) if workspace else None
        values=values|dict(dish=name,material=found.cost_per_serving if found else values['material'],
                           ingredients=[(i.name,i.cost) for i in found.ingredients] if found else [],
                           place=dict(name=place.area_name,sales=place.sales_per_store,industry=place.industry) if place and place.sales_per_store else None,
                           dineout=None)
        menu=DINEOUT_MENUS.get(name)
        if self.dineout and menu in self.dineout.menus():
            quote=self.dineout.quote(menu,'서울')
            if quote:
                values['dineout']=dict(menu=quote.menu,region=quote.region,month=quote.month,price=quote.price,
                                       year_ago_price=quote.year_ago_price,source=quote.source)
        return values

    # ---- Analysis ----
    @staticmethod
    def scenario(v,price):
        unit_cost=v['material']+v['other']
        margin=price-unit_cost
        fixed=v['rent']+v['labor']+v['fixed_other']
        bep=(fixed/margin).to_integral_value(rounding=ROUND_CEILING) if margin>0 else None
        revenue=price*v['volume']
        profit=margin*v['volume']-fixed
        return dict(price=price,margin=margin,cost_ratio=v['material']/price*100,bep=bep,bep_day=(bep/DAYS).to_integral_value(rounding=ROUND_CEILING) if bep else None,
                    bep_revenue=bep*price if bep else None,revenue=revenue,profit=profit)

    def calculate(self,v):
        fixed=v['rent']+v['labor']+v['fixed_other']
        now=self.scenario(v,v['price'])
        prices=sorted({max(Decimal(500),v['price']-500),v['price'],v['price']+500,v['price']+1000,self.suggested_price(v['material'])})
        rows=[]
        for price in prices:
            s=self.scenario(v,price)
            label='현재 가격' if price==v['price'] else ('원가율 30% 가격' if price==self.suggested_price(v['material']) else '')
            rows.append([f"{price:,.0f}원"+(f" ({label})" if label else ''),s['margin'],s['cost_ratio'],
                         f"{s['bep']:,.0f}개 (하루 {s['bep_day']:,.0f}개)" if s['bep'] else '이익이 남지 않음',
                         s['bep_revenue'] if s['bep_revenue'] is not None else '-',s['revenue'],s['profit']])
        day=(v['volume']/DAYS).quantize(Decimal(1))
        advice=[]
        if now['bep'] is None:
            advice.append(f"지금 가격({v['price']:,.0f}원)은 1개 원가({v['material']+v['other']:,.0f}원)보다 낮거나 같아 팔수록 손해입니다. 가격을 올리세요.")
        else:
            advice.append(f"하루 {now['bep_day']:,.0f}개(월 {now['bep']:,.0f}개, 매출 {now['bep_revenue']:,.0f}원) 이상 팔아야 적자를 면합니다.")
            advice.append(f"예상대로 하루 {day:,.0f}개를 팔면 한 달에 {abs(now['profit']):,.0f}원 " + ('남습니다.' if now['profit']>=0 else '모자랍니다.'))
            if now['profit']<0:
                need=next((p for p in range(int(v['price'])+100,int(v['price'])*3,100) if self.scenario(v,Decimal(p))['profit']>=0),None)
                if need: advice.append(f"판매량이 그대로라면 판매가를 {need:,.0f}원 이상으로 올려야 손익분기점을 넘습니다. 고정비를 줄이는 방법은 비용 절감(05)에서 확인하세요.")
        if now['cost_ratio']>40:
            advice.append(f"원가율이 {now['cost_ratio']:.0f}%로 높은 편입니다(통상 25~35%). 분량이나 비싼 재료를 점검하세요.")
        place=v.get('place')
        if place and now['bep_revenue']:
            ratio=now['bep_revenue']/place['sales']*100
            advice.append(f"{place['name']} 상권의 {place['industry']} 점포당 월평균 매출은 {place['sales']:,.0f}원입니다. 손익분기 매출은 그 {ratio:.0f}% 수준이라 "
                          +('무리 없는 목표입니다.' if ratio<=70 else '평균 매장만큼 팔아야 하는 빠듯한 목표입니다.' if ratio<=110 else '평균 매장보다 많이 팔아야 해 어려운 목표입니다.'))
        notes=['손익분기 판매량 = 월 고정비(임대료 + 인건비 + 기타 고정비) ÷ 1개당 공헌이익(판매가 - 재료비 - 기타 변동비). 하루 판매량은 30일로 나눈 값입니다.',
               (f"재료비 {v['material']:,.0f}원은 재료비 관리(02)에서 계산한 {v['dish']} 1인분 원가입니다: "+', '.join(f"{n} {c:,.0f}원" for n,c in v['ingredients'])+'.')
               if v['ingredients'] else f"재료비 {v['material']:,.0f}원은 직접 입력한 값입니다. 재료비 관리(02)에서 음식을 계산하면 자동으로 이어받습니다.",
               '이 메뉴 하나만 판다고 가정한 계산입니다. 여러 메뉴를 팔면 판매 비중에 따라 손익분기점이 달라집니다.',
               '모든 가격에서 판매량이 같다고 가정합니다. 가격을 올리면 판매량이 줄 수 있습니다.',
               '세금(부가세·소득세)과 대출 이자는 빠져 있습니다.']
        if place: notes.append('상권 평균 매출: 부동산 및 업장 관리(01) 추천 1순위 상권의 서울시 상권분석서비스 추정매출(점포당 월평균)입니다.')
        dine=self.dineout_table(v)
        chart=[('손익분기 매출',now['bep_revenue'] or Decimal(0)),('예상 월 매출',now['revenue'])]
        if place: chart.append((f"{place['name']} 점포당 평균 매출",won(place['sales'])))
        return dict(metrics=[('손익분기 판매량',f"하루 {now['bep_day']:,.0f}" if now['bep'] else '도달 불가','개'),
                             ('손익분기 월 매출',won(now['bep_revenue']) if now['bep_revenue'] else '-','원'),
                             ('예상 월 매출',won(now['revenue']),'원'),('예상 월 영업이익',won(now['profit']),'원')],
                    advice=advice,table_tab='가격별 손익',table_title=f"{v['dish']} 가격별 손익분기점과 월 이익 (월 {v['volume']:,.0f}개, 고정비 {fixed:,.0f}원)",
                    columns=['판매가','1개당 공헌이익 (원)','원가율 (%)','손익분기 판매량 (월)','손익분기 매출 (원)','예상 월 매출 (원)','예상 월 영업이익 (원)'],rows=rows,
                    chart=chart,chart_title='손익분기 매출과 예상 매출',extra_tables=[dine] if dine else [],notes=notes,
                    menu_name=v['dish'],monthly_revenue=now['revenue'],monthly_material=v['material']*v['volume'],monthly_volume=v['volume'])

    @staticmethod
    def dineout_table(v):
        d=v.get('dineout')
        if not d: return None
        avg=Decimal(d['price'])
        change=(avg-d['year_ago_price'])/d['year_ago_price']*100 if d['year_ago_price'] else None
        rows=[['서울 평균 외식 가격',avg,'-','-'],['내 판매가',v['price'],v['price']-avg,(v['price']-avg)/avg*100]]
        note=f"출처: {d['source']}, {d['month']} 기준." + (f" 1년 전 대비 {change:+.1f}%." if change is not None else '')
        note+=' 대표 음식점 평균 판매가라 양·구성·입지에 따라 차이가 큽니다. (내 PC 계산용)'
        return dict(tab='외식 가격 비교',title=f"{d['region']} {d['menu']} 평균 가격과 비교 ({d['month']})",
                    lead='내 가격이 지역 평균보다 얼마나 높거나 낮은지 보여 줍니다.',
                    columns=['구분','가격 (원)','평균과 차이 (원)','평균과 차이 (%)'],rows=rows,note=note)

    # ---- Priced menus, monthly sales and menu engineering ----
    def remember(self,workspace,record):
        if self.recipes: self.recipes.save(workspace,record.result['menu_name'],[],Decimal(record.inputs['other']))

    def list_menus(self,workspace):
        """Menus priced here, with their current ingredient cost from 02."""
        if not self.recipes: return []
        costs={d.name:d.cost_per_serving for d in self.dishes(workspace)}
        menus=self.recipes.list(workspace)
        for menu in menus:
            menu['cost']=costs.get(menu['name'],Decimal(0))
        return menus

    def delete_menu(self,workspace,menu_id):
        return bool(self.recipes and self.recipes.delete(workspace,menu_id))

    def forget(self,workspace):
        super().forget(workspace)
        if self.recipes: self.recipes.forget(workspace)  # menu_sales go with their menus

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
        unit contribution margin (>= sales-weighted average). Costs use current ingredient prices."""
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

    def export_operating_costs(self, workspace):
        periods = self.sales_periods(workspace)
        if periods:
            analysis = self.menu_engineering(workspace, periods[0])
            if analysis['rows']:
                return OperatingCostSnapshot(detail=f"{periods[0]} 판매 기록 (메뉴 {len(analysis['rows'])}개)",
                                             source='사용자 판매 기록', updated_at=utc_now(),
                                             monthly_revenue=analysis['revenue'], monthly_material=analysis['material'])
        record = self.latest(workspace)
        if record is None or 'monthly_volume' not in record.result:
            return None
        result = record.result
        return OperatingCostSnapshot(detail=f"메뉴 '{result['menu_name']}' 월 {result['monthly_volume']:,.0f}개 기준", source=record.source,
                                     updated_at=record.updated_at, monthly_revenue=result['monthly_revenue'],
                                     monthly_material=result['monthly_material'])
