from decimal import Decimal, ROUND_CEILING
from app.common.model import AnalysisModel
from app.common.text import josa
from app.common.validation import Field, ValidationError
from app.integrations.contracts import DishCost, DishIngredient, MaterialCostItem, MaterialCostSnapshot
from . import recipes


UNITS = {'kg': ('mass',Decimal(1000)), 'g': ('mass',Decimal(1)), 'L': ('volume',Decimal(1000)), 'mL': ('volume',Decimal(1)), '개': ('count',Decimal(1))}
BASE_UNIT = {'mass':'g','volume':'mL','count':'개'}


def purchase_unit(unit, pack_size):
    """Unit for the saved material list: kg / L for packs of 1kg / 1L or more, else the recipe unit (장 counts as 개)."""
    if unit == 'g' and pack_size >= 1000: return 'kg', Decimal(1000)
    if unit == 'mL' and pack_size >= 1000: return 'L', Decimal(1000)
    return ('개' if unit not in UNITS else unit), Decimal(1)


class MaterialCostModel(AnalysisModel):
    result_key='advice'
    fields=(
        Field('dish','음식','카페라떼','text',help='목록의 음식을 고르면 1인분 재료와 분량을 자동으로 채웁니다.'),
        Field('monthly_volume','월 예상 판매량 (잔·그릇)','900',minimum='1',maximum='1000000',step='1',
              help='한 달에 몇 개 팔지 예상해 넣으세요. 하루 30잔 × 30일 = 900잔.'),
    )

    def __init__(self,repository,catalog=None,prices=None,commodities=None,dishes=None):
        super().__init__(repository)
        # Optional saved-material list and dish list (need a database); None disables them.
        self.catalog=catalog
        self.dishes=dishes
        # Optional MarketPriceProvider (public retail prices) and CommodityTrendProvider (e.g. green coffee futures).
        self.price_provider=prices
        self.commodity_provider=commodities

    @property
    def prices(self):
        provider=self.price_provider
        return provider if provider is not None and provider.available() else None

    @staticmethod
    def dish_names():
        return recipes.names()

    @staticmethod
    def dish_groups():
        return recipes.groups()

    def retail_of(self,ingredient):
        """Public retail quote for one recipe ingredient in the same unit, or None (reference only)."""
        _,_,unit,_,market,_,_,_=ingredient
        if not market or not self.prices: return None
        key=self.prices.suggest(market,unit)
        quote=self.prices.quote(key) if key else None
        if not quote or quote.base_unit!=unit or not quote.price_per_base: return None
        change=(Decimal(quote.price)-quote.year_ago_price)/quote.year_ago_price*100 if quote.year_ago_price else None
        return dict(per_unit=quote.price_per_base,month=quote.month,label=quote.label.split(' · ')[0],change=change)

    def compare_market(self,item):
        """Retail market comparison for one saved material (automatic name match)."""
        if not self.prices: return None
        quote=self.prices.quote(self.prices.suggest(item['name'],item['base_unit']) or '')
        if quote is None: return None
        dimension,factor=UNITS[item['unit']]
        mine=item['unit_price']/factor
        comparable=quote.price_per_base is not None and quote.base_unit==BASE_UNIT[dimension]
        gap=(mine-quote.price_per_base)/quote.price_per_base*100 if comparable and quote.price_per_base else None
        change=(Decimal(quote.price)-quote.year_ago_price)/quote.year_ago_price*100 if quote.year_ago_price else None
        return dict(label=quote.label,month=quote.month,unit=quote.unit,price=quote.price,gap=gap,change=change)

    def commodity_trend(self,name):
        provider=self.commodity_provider
        if provider is None or not provider.available(): return None
        trend=provider.trend_for(name)
        return None if trend is None else dict(commodity=trend.commodity,week=trend.week_start,cents=trend.cents_per_lb,
                                               per_kg=trend.usd_per_kg,change_4w=trend.change_4w,change_52w=trend.change_52w,source=trend.source)

    @staticmethod
    def base_unit_cost(unit,unit_price,yield_rate):
        """Price per usable base unit (g, mL, 개) for a price per purchase unit, yield applied."""
        dimension,factor=UNITS[unit]
        return BASE_UNIT[dimension],unit_price/factor*100/yield_rate

    # ---- Analysis ----
    def prepare(self,values,raw):
        dish=values['dish'].strip()
        if dish not in recipes.RECIPES:
            raise ValidationError(f"'{dish}'은(는) 등록된 음식이 아닙니다. 입력란 목록에서 골라 주세요: {', '.join(recipes.names())}")
        group,items=recipes.RECIPES[dish]
        lines=[]
        for ingredient in items:
            name,qty,unit,yield_rate,_,_,pack_size,pack_label=ingredient
            lines.append(dict(name=name,quantity=qty,unit=unit,yield_rate=yield_rate,price=ingredient[5],retail=self.retail_of(ingredient),
                              pack_size=pack_size,pack_label=pack_label,trend=self.commodity_trend(name)))
        return values|dict(dish=dish,group=group,lines=lines)

    def calculate(self,v):
        volume=v['monthly_volume']
        rows,chart,total,spend=[],[],Decimal(0),Decimal(0)
        for line in v['lines']:
            bought=line['quantity']*100/line['yield_rate']          # amount to buy for one serving
            cost=bought*line['price']
            need=bought*volume
            packs=(need/line['pack_size']).to_integral_value(rounding=ROUND_CEILING)
            line.update(cost=cost,need=need,packs=packs,spend=packs*line['pack_size']*line['price'])
            total+=cost; spend+=line['spend']
            unit=line['unit']; r=line['retail']
            retail=(f"{r['per_unit']:,.1f}원/{unit} ({r['month']})"+(f" · 1년 {r['change']:+.0f}%" if r['change'] is not None else '')) if r else '-'
            rows.append([line['name'],f"{line['quantity'].normalize():f} {unit}",line['yield_rate'],f"{line['price'].normalize():f}원/{unit}",retail,
                         cost.quantize(Decimal(1)),f"{need:,.0f} {unit}",f"{line['pack_label']} × {packs:,.0f}",line['spend'].quantize(Decimal(1))])
            chart.append((line['name'],cost))
        top=max(v['lines'],key=lambda l:l['cost'])
        share=top['cost']/total*100 if total else Decimal(0)
        compared=[l for l in v['lines'] if l['retail']]
        serving='1잔' if v['group']==recipes.CAFE else '1그릇'
        advice=[f"{v['dish']} {serving}의 재료비는 {total:,.0f}원입니다. 메뉴 가격 관리(03)에서 이 원가로 판매가와 손익분기점을 확인하세요.",
                f"{josa(top['name'],'이/가')} 재료비의 {share:.0f}%를 차지합니다. 공급처 2~3곳의 견적을 받아 비교하면 원가를 가장 크게 줄일 수 있습니다."]
        trend=next((l['trend'] for l in v['lines'] if l['trend'] and l['trend']['change_52w'] is not None),None)
        if trend:
            move='내렸' if trend['change_52w']<0 else '올랐'
            advice.append(f"국제 {trend['commodity']} 시세가 1년 전보다 {abs(trend['change_52w']):.0f}% {move}습니다. "
                          +('원두 납품가 인하를 요청해 볼 만합니다.' if trend['change_52w']<0 else '원두 납품가 인상에 대비하세요.'))
        rising=max((l for l in compared if l['retail']['change'] is not None),key=lambda l:l['retail']['change'],default=None)
        if rising and rising['retail']['change']>=15:
            advice.append(f"{rising['name']} 소매 시세가 1년 새 {rising['retail']['change']:.0f}% 올랐습니다. 납품가가 따라 오를 수 있으니 대체 재료나 분량을 점검하세요.")
        advice.append(f"월 {volume:,.0f}개 기준으로 한 달에 표의 '추천 구매'만큼 사면 됩니다. 유통기한이 짧은 재료는 주 단위로 나눠 사세요.")
        notes=['1인분 원가 = 1인분 사용량 ÷ 수율 × 단가. 수율은 손질·폐기 후 실제로 쓰는 비율입니다(대파 85%, 바나나 65% 등 통상 값).',
               '적용 단가는 2026년 업소용(도매·온라인 대용량) 통상 가격을 가정한 값입니다. 소매 시세(참고)는 KAMIS·참가격·서울 시장 조사의 최근 월평균으로, 소포장 소매가라 업소용보다 비쌉니다. 1년 변화로 가격 흐름을 확인하세요.',
               '레시피 분량은 이 프로토타입이 정리한 통상 1인분 기준입니다. 매장 레시피와 다르면 결과도 달라집니다.',
               '추천 구매 = 월 필요량(수율 반영)을 통상 포장 단위로 올림한 수량입니다. 월 구매비는 남는 양까지 포함한 금액입니다.']
        notes.append('실제 매입가는 거래처·물량·계절에 따라 다릅니다. 영수증 단가와 비교해 보세요.')
        if trend: notes.append(f"원두 추세 출처: {trend['source']} ({trend['week']} 주). 생두 국제가라 로스팅·관세·환율·마진이 빠져 있습니다. (내 PC 계산용)")
        return dict(metrics=[(f'{serving} 재료비',total.quantize(Decimal(1)),'원'),('월 재료 구매비',spend.quantize(Decimal(1)),'원'),('가장 비싼 재료',f"{top['name']} ({share:.0f}%)",''),
                             ('소매 시세와 비교한 재료',f"{len(compared)} / {len(v['lines'])}",'개')],
                    advice=advice,table_tab='재료별 원가',table_title=f"{v['dish']} 재료별 원가와 월 구매량 (월 {volume:,.0f}개)",
                    columns=['재료','1인분 사용량','수율 (%)','적용 단가 (업소용)','소매 시세 (참고)','1인분 원가 (원)','월 필요량','추천 구매','월 구매비 (원)'],
                    rows=rows,chart=chart,chart_title=f'{v["dish"]} 1인분 재료비 구성',notes=notes,
                    dish=v['dish'],usage_cost=total,monthly_volume=volume,
                    lines=[dict(name=l['name'],quantity=l['quantity'],unit=l['unit'],yield_rate=l['yield_rate'],price=l['price'],
                                cost=l['cost'],packs=l['packs'],pack_size=l['pack_size']) for l in v['lines']])

    # ---- Saved dishes and materials ----
    def remember(self,workspace,record):
        """Save the analysed dish (for 03) and update the material list with this month's purchases."""
        r=record.result
        if self.dishes:
            self.dishes.save(workspace,r['dish'],r['monthly_volume'],r['usage_cost'],
                             [dict(name=l['name'],quantity=l['quantity'],unit=l['unit'],cost=l['cost']) for l in r['lines']])
        if self.catalog:
            for l in r['lines']:
                unit,factor=purchase_unit(l['unit'],l['pack_size'])
                self.catalog.save_purchase(workspace,l['name'],unit,l['yield_rate'],l['price']*factor,l['packs']*l['pack_size']/factor)

    def list_dishes(self,workspace):
        """Public contract for the menu module: analysed dishes and their ingredient cost per serving."""
        if not self.dishes: return []
        return [DishCost(d['id'],d['name'],d['cost'],d['monthly_volume'],
                         tuple(DishIngredient(i['name'],i['quantity'],i['unit'],i['cost']) for i in d['items']),d['updated_at'])
                for d in self.dishes.list(workspace)]

    def delete_dish(self,workspace,dish_id):
        return bool(self.dishes and self.dishes.delete(workspace,dish_id))

    def list_materials(self,workspace,with_market=True):
        if not self.catalog: return []
        materials=self.catalog.list(workspace)
        for item in materials:
            item['base_unit'],item['cost_per_base_unit']=self.base_unit_cost(item['unit'],item['unit_price'],item['yield_rate'])
            item['market']=self.compare_market(item) if with_market else None
            item['commodity']=self.commodity_trend(item['name']) if with_market else None
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
        if self.dishes: self.dishes.forget(workspace)

    def export_usage_cost(self,workspace):
        record=self.latest(workspace)
        if record is None or 'usage_cost' not in record.result: return None
        return MaterialCostSnapshot(record.result['usage_cost'],record.source,record.updated_at)
