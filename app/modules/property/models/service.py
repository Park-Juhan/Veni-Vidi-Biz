from dataclasses import asdict
from decimal import Decimal, ROUND_CEILING
from app.common.model import AnalysisModel
from app.common.text import josa
from app.common.validation import Field, ValidationError
from app.integrations.contracts import LocationSnapshot, OperatingCostSnapshot
from .decision_engine.engine import CRITERIA, recommend_areas


# Monthly rent bands, like a hotel price filter: label -> (above, up to) in 원.
RENT_BANDS = {
    '상관없음': (None, None), '100만 원 이하': (None, 1_000_000), '100~200만 원': (1_000_000, 2_000_000),
    '200~300만 원': (2_000_000, 3_000_000), '300~500만 원': (3_000_000, 5_000_000), '500만 원 초과': (5_000_000, None),
}
CAFE = {'커피-음료', '제과점'}
FOOD = {'한식음식점', '중식음식점', '일식음식점', '양식음식점', '분식전문점', '치킨전문점', '패스트푸드점', '호프-간이주점', '반찬가게'}
# Rule-of-thumb assumptions per kind of business (editable on screen):
# ㎡ per seat, fixed ㎡ (counter, kitchen, storage), equipment, interior per ㎡, first stock, other (sign, POS, permits, opening ads).
SUGGESTIONS = {
    'cafe': dict(seat_m2=Decimal('1.8'), base_m2=Decimal(15), equipment=25_000_000, interior_per_m2=550_000, initial_material=2_000_000, other_startup=5_000_000),
    'food': dict(seat_m2=Decimal('1.6'), base_m2=Decimal(20), equipment=20_000_000, interior_per_m2=500_000, initial_material=3_000_000, other_startup=5_000_000),
    'other': dict(seat_m2=Decimal('1.5'), base_m2=Decimal(10), equipment=10_000_000, interior_per_m2=400_000, initial_material=1_000_000, other_startup=3_000_000),
}
DEFAULT_INDUSTRY = '커피-음료'
DEFAULT_DEPOSIT_MONTHS = Decimal(10)


def kind_of(industry):
    return 'cafe' if industry in CAFE else 'food' if industry in FOOD else 'other'


def suggestion(industry):
    return SUGGESTIONS[kind_of(industry)]


def survey_industry(industry):
    """소상공인실태조사 industry used for average lease terms and start-up costs."""
    return '음식점 및 주점업' if kind_of(industry) in ('cafe', 'food') else '전산업 전체'


class PropertyModel(AnalysisModel):
    result_key='advice'
    fields = (
        Field('industry', '업종', DEFAULT_INDUSTRY, 'text'),
        Field('rent_band', '월 임대료 예산', '200~300만 원', 'select', choices=tuple(RENT_BANDS)),
        Field('seats', '손님 좌석 수 (명)', '16', minimum='1', maximum='500', step='1',
              help='동시에 앉을 수 있는 손님 수입니다. 업종별 좌석당 면적과 주방·카운터 면적으로 필요한 크기를 계산합니다.'),
        Field('available', '확보한 창업 자금 (원)', '80000000'),
        Field('equipment', '장비 구입비 (원)', '25000000', group='초기 자금'),
        Field('interior_per_m2', '인테리어 (원/㎡)', '550000', group='초기 자금'),
        Field('initial_material', '초기 재료비 (원)', '2000000', group='초기 자금'),
        Field('other_startup', '기타 (간판·POS·인허가·오픈 홍보, 원)', '5000000', group='초기 자금'),
    )

    def __init__(self, repository, areas=None, startup=None, rents=None):
        super().__init__(repository)
        # Optional AreaDataProvider (서울시 상권분석서비스), RentProvider (부동산원 임대료) and StartupBenchmarkProvider.
        self.area_provider = areas
        self.rent_provider = rents
        self.startup_provider = startup

    @staticmethod
    def _ready(provider):
        return provider if provider is not None and provider.available() else None

    @property
    def areas(self): return self._ready(self.area_provider)

    @property
    def rents(self): return self._ready(self.rent_provider)

    @property
    def startup(self): return self._ready(self.startup_provider)

    def industries(self):
        return self.areas.industries() if self.areas else []

    def districts(self):
        return self.areas.districts() if self.areas else []

    def suggestions(self):
        """Per-industry default start-up costs for the form (industry -> field values)."""
        return {industry: {k: str(v) for k, v in suggestion(industry).items()} for industry in self.industries()}

    def benchmark(self, industry):
        return self.startup.benchmark(survey_industry(industry), '서울특별시') if self.startup else None

    # ---- Analysis ----
    def prepare(self, values, raw):
        if not self.areas or not self.rents:
            raise ValidationError('상권·임대료 공공데이터를 아직 불러오지 않았습니다. import_data.py로 data/raw 파일을 불러온 뒤 다시 시도하세요.')
        industry = values['industry'].strip()
        if industry not in self.industries():
            raise ValidationError('업종을 목록에서 골라 주세요.')
        known = set(self.districts())
        districts = [d for d in (raw.get('districts') or []) if d in known]
        kind = suggestion(industry)
        area_needed = (values['seats'] * kind['seat_m2'] + kind['base_m2']).to_integral_value(rounding=ROUND_CEILING)
        months, benchmark = DEFAULT_DEPOSIT_MONTHS, self.benchmark(industry)
        areas = []
        for snapshot in self.areas.snapshots(industry, districts or None):
            rent = self.rents.estimate(snapshot.name, snapshot.district, snapshot.dong)
            if rent is None: continue
            areas.append(asdict(snapshot) | dict(rent_per_m2=rent.per_m2, rent_basis=rent.basis, rent_quarter=rent.quarter, rent_source=rent.source))
        return values | dict(industry=industry, districts=districts, area_needed=area_needed, deposit_months=months,
                             rent_range=RENT_BANDS[values['rent_band']], areas=areas,
                             startup=asdict(benchmark) if benchmark else None)

    def calculate(self, v):
        decision = recommend_areas(v)
        top, facts = decision['candidates'], decision['facts']
        best = top[0]
        rows = [[rank, f"{c['name']} ({c['area']['district']} {c['area']['dong']})", c['rent'], c['startup'],
                 c['values']['sales_per_store'].quantize(Decimal(1)), c['values']['competition'], c['values']['footfall'],
                 c['score'].quantize(Decimal('0.1')), c['reason'] + (f" / 주의: {c['caution']}" if c['caution'] else '')]
                for rank, c in enumerate(top, start=1)]
        common = v['equipment'] + v['initial_material'] + v['other_startup']
        interior = v['interior_per_m2'] * v['area_needed']
        shortage = best['startup'] - v['available']
        where = ', '.join(v['districts']) if v['districts'] else '서울 전체'
        advice = [f"{best['name']}({best['area']['district']} {best['area']['dong']})부터 직접 둘러보세요. {best['reason']}."]
        if best['caution']: advice.append(f"{josa(best['name'], '은/는')} {best['caution']}이라 현장에서 손님 흐름과 경쟁 가게를 확인하세요.")
        advice.append(f"자금이 {shortage:,.0f}원 부족합니다. 인테리어·장비를 줄이거나 2~5순위 중 임대료가 낮은 곳을 검토하세요." if shortage > 0
                      else f"1순위 기준으로 확보 자금에서 {-shortage:,.0f}원이 남습니다. 3~6개월 운영비로 남겨 두세요.")
        advice.append(f"표의 임대료는 부동산원 평균으로 추정한 값입니다. 실제 매물의 월세·보증금을 받아 다시 비교하세요.")
        notes = [
            f"후보: {where}의 서울시 상권 중 '{v['industry']}' 점포가 {3}곳 이상이고 매출·유동인구 자료가 있는 {facts['with_data']}곳, "
            f"그중 예상 월 임대료가 '{v['rent_band']}'에 드는 {facts['in_budget']}곳을 비교했습니다.",
            f"필요 면적 = 좌석 {v['seats']:,.0f}석 × 좌석당 {suggestion(v['industry'])['seat_m2']}㎡ + 주방·카운터 {suggestion(v['industry'])['base_m2']}㎡ = {v['area_needed']:,.0f}㎡ (업종별 통상 가정).",
            '예상 월 임대료 = 상권 ㎡당 월 임대료 × 필요 면적. 상권별 ㎡당 임대료는 한국부동산원 「상업용부동산 임대동향조사」 소규모 상가 임대료(서울 64개 조사 상권)를 '
            '이름·행정동으로 연결하고, 조사 상권이 없으면 같은 구의 조사 상권 평균, 그것도 없으면 서울 기타지역 평균을 씁니다. 1층·대로변은 더 비쌉니다.',
            f"보증금 = 월 임대료 × {v['deposit_months']:,.0f}개월 (서울 소규모 상가 통상 가정). 실제 보증금은 매물마다 차이가 큽니다.",
            '초기 필요 자금 = 보증금 + 첫 달 임대료 + 인테리어(㎡당 × 면적) + 장비 + 초기 재료 + 기타.',
            '순위: TOPSIS(이상적인 값에 가깝고 가장 나쁜 값에서 먼 정도). 가중치는 ' + ', '.join(f'{label} {w}%' for _, label, _, w in CRITERIA) + '로 고정했습니다.',
            f"상권 지표 출처: {best['area']['source']}, 기준 {best['area']['period']}. 서울시가 카드 결제 등으로 추정한 상권 전체 값이며 특정 매물의 실적이 아닙니다. 점포당 월평균 추정매출 = 분기 추정매출 ÷ 점포 수 ÷ 3.",
        ]
        startup_tab = self.startup_table(top, v.get('startup'))
        if startup_tab: notes.append(startup_tab['note'])
        return dict(
            metrics=[('추천 1순위 상권', best['name'], ''), ('예상 월 임대료', best['rent'], '원'), ('초기 필요 자금', best['startup'], '원'),
                     ('필요 면적', v['area_needed'], '㎡')],
            advice=advice, table_tab='추천 상권 5곳', table_title=f"{v['industry']} 추천 상권 상위 {len(top)}곳 (좌석 {v['seats']:,.0f}석 · {v['area_needed']:,.0f}㎡ · {v['rent_band']})",
            columns=['순위', '상권 (위치)', '예상 월 임대료 (원)', '초기 필요 자금 (원)', '점포당 월매출 (원)', '같은 업종 점포 (곳)', '유동인구 (분기)', '종합 점수', '추천 이유'],
            rows=rows,
            extra_tables=[self.area_table(top, v['industry'])] + ([startup_tab] if startup_tab else []),
            chart=[('보증금', best['deposit']), ('첫 달 임대료', best['rent']), ('인테리어', interior), ('장비', v['equipment']),
                   ('초기 재료', v['initial_material']), ('기타', v['other_startup'])],
            chart_title=f"1순위 {best['name']}의 초기 자금 구성", notes=notes, trace=decision['trace'],
            best_name=best['name'], best_rent=best['rent'], best_sales_per_store=best['values']['sales_per_store'], industry=v['industry'])

    @staticmethod
    def startup_table(top, b):
        """Compare each area's estimated rent and deposit with the survey average for the industry."""
        if not b or b['monthly_rent'] is None or b['deposit'] is None:
            return None
        labels = ('5천만 원 미만', '5천만~1억 원', '1억 원 이상')
        def bracket(amount):
            return 0 if amount < 50_000_000 else 1 if amount < 100_000_000 else 2
        def pct(value, avg):
            return f"{(value - avg) / avg * 100:+.1f}" if avg else '-'
        rows = []
        for c in top:
            index = bracket(c['startup'])
            share = b['cost_brackets'][index]
            rows.append([c['name'], c['rent'], pct(c['rent'], b['monthly_rent']), c['startup'],
                         f"{labels[index]} (업체 {share:.1f}%)" if share is not None else labels[index]])
        brackets = ', '.join(f"{label} {value:.1f}%" for label, value in zip(labels, b['cost_brackets']) if value is not None)
        note = (f"업종 평균 출처: {b['source']}, {b['year']}년 {b['region']} · {b['industry']}. 평균 월세 {b['monthly_rent']:,.0f}원, "
                f"보증금 {b['deposit']:,.0f}원. 창업비용 분포: {brackets}. (내 PC 계산용)")
        return dict(tab='업종 평균과 비교', title=f"업종 평균 임대·창업비용과 비교 ({b['industry']} · {b['region']}, {b['year']})",
                    lead='추천 상권의 예상 월 임대료가 업종 평균 월세보다 얼마나 높은지, 초기 자금이 창업비용 분포의 어디쯤인지 보여 줍니다.',
                    columns=['상권', '예상 월 임대료 (원)', '평균 월세 대비 (%)', '초기 필요 자금 (원)', '창업비용 구간 (해당 구간 업체 비율)'],
                    rows=rows, note=note)

    @staticmethod
    def area_table(top, industry):
        """Detailed commercial-area statistics of the recommended areas."""
        def won(value):
            return None if value is None else value.quantize(Decimal(1))
        def cell(c, pick):
            value = pick(c['area'])
            return '-' if value is None else value
        rows = [
            ['위치 · 상권 종류', *[cell(c, lambda a: f"{a['district']} {a['dong']} · {a['kind']}") for c in top]],
            ['㎡당 월 임대료 (원)', *[cell(c, lambda a: f"{a['rent_per_m2']:,.0f} ({a['rent_basis']})") for c in top]],
            [f'{industry} 분기 추정매출 (원)', *[cell(c, lambda a: a['sales']) for c in top]],
            [f'{industry} 점포 수', *[cell(c, lambda a: a['stores']) for c in top]],
            ['결제 1건당 금액 (원)', *[cell(c, lambda a: won(Decimal(a['sales'])/a['sales_count']) if a['sales'] is not None and a['sales_count'] else None) for c in top]],
            ['프랜차이즈 점포 수', *[cell(c, lambda a: a['franchise']) for c in top]],
            ['분기 개업률 / 폐업률 (%)', *[cell(c, lambda a: None if a['open_rate'] is None else f"{a['open_rate']} / {a['close_rate']}") for c in top]],
            ['매출이 가장 많은 연령대 · 시간대', *[cell(c, lambda a: None if a['top_age'] is None else f"{a['top_age']} · {a['top_time']}") for c in top]],
            ['유동인구 (분기)', *[cell(c, lambda a: a['footfall']) for c in top]],
            ['직장인구 / 상주인구', *[cell(c, lambda a: None if a['workers'] is None else f"{a['workers']:,} / {a['residents'] or 0:,}") for c in top]],
            ['집객시설 (지하철역 · 버스정거장)', *[cell(c, lambda a: None if a['facilities'] is None else f"{a['facilities']:,} ({a['subway']} · {a['bus_stops']})") for c in top]],
            ['상권 변화', *[cell(c, lambda a: a['change']) for c in top]],
        ]
        period = top[0]['area']['period']
        return dict(tab='상권 상세 지표', title=f'추천 상권 상세 지표 ({industry}, {period})',
                    lead='서울시 상권분석서비스 공개 통계와 부동산원 임대료입니다. 매출·점포 수는 선택한 업종 기준입니다.',
                    columns=['지표', *[c['name'] for c in top]], rows=rows, note=None)

    def export_operating_costs(self, workspace):
        record = self.latest(workspace)
        if record is None or 'best_rent' not in record.result:
            return None
        return OperatingCostSnapshot(detail=f"추천 1순위 {record.result['best_name']}", source=record.source,
                                     updated_at=record.updated_at, monthly_rent=record.result['best_rent'])

    def export_location(self, workspace):
        record = self.latest(workspace)
        if record is None or 'best_sales_per_store' not in record.result:
            return None
        r = record.result
        return LocationSnapshot(area_name=r['best_name'], monthly_rent=r['best_rent'], sales_per_store=r['best_sales_per_store'],
                                industry=r['industry'], updated_at=record.updated_at)
