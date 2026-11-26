"""Location recommendation: every Seoul commercial area with the chosen industry is a candidate.

Blackboard steps: estimate rent and start-up money per area -> keep areas inside the rent budget ->
rank with TOPSIS on fixed weights -> keep the top five and explain them.
"""
from decimal import Decimal
from app.common.decision import Blackboard, KnowledgeSource, ControlComponent, ResultGenerator
from app.common.validation import ValidationError

# (key, label, benefit=True if larger is better, weight %). Fixed so the user does not have to tune them.
CRITERIA = (
    ('sales_per_store', '점포당 월평균 추정매출', True, 30),
    ('rent', '예상 월 임대료', False, 20),
    ('footfall', '유동인구', True, 20),
    ('competition', '같은 업종 점포 수', False, 15),
    ('close_rate', '폐업률', False, 15),
)
MIN_STORES = 3        # fewer stores make "sales per store" too noisy to compare
TOP = 5


def area_values(area):
    """Criteria values from an area snapshot dict (None when not published)."""
    if not area:
        return dict(sales_per_store=None, competition=None, footfall=None, close_rate=None)
    sales, stores = area.get('sales'), area.get('stores')
    per_store = Decimal(sales)/stores/3 if sales is not None and stores else None
    footfall, close = area.get('footfall'), area.get('close_rate')
    return dict(sales_per_store=per_store, competition=Decimal(stores) if stores is not None else None,
                footfall=Decimal(footfall) if footfall is not None else None, close_rate=Decimal(close) if close is not None else None)


def _estimate_costs(board):
    v = board.inputs
    common = v['equipment'] + v['initial_material'] + v['other_startup'] + v['interior_per_m2'] * v['area_needed']
    for area in v['areas']:
        rent = (area['rent_per_m2'] * v['area_needed'] / 1000).to_integral_value() * 1000
        deposit = rent * v['deposit_months']
        board.candidates.append(dict(area=area, name=area['name'], rent=rent, deposit=deposit,
                                     startup=deposit + rent + common, values=area_values(area) | dict(rent=rent)))


def _filter_budget(board):
    v = board.inputs
    low, high = v['rent_range']
    total = len(board.candidates)
    usable = [c for c in board.candidates if c['values']['sales_per_store'] is not None and c['values']['competition'] >= MIN_STORES
              and c['values']['footfall'] is not None]
    board.facts['with_data'] = len(usable)
    board.candidates = [c for c in usable if (low is None or c['rent'] > low) and (high is None or c['rent'] <= high)]
    board.facts['in_budget'] = len(board.candidates)
    board.facts['total'] = total
    if not board.candidates:
        raise ValidationError('조건에 맞는 상권이 없습니다. 임대료 범위를 넓히거나 좌석 수를 줄이거나, 자치구를 더 선택해 보세요.')


def _topsis(board):
    """TOPSIS: closeness to the ideal and distance from the worst on the weighted, vector-normalised criteria."""
    weights = {key: Decimal(w) / 100 for key, _, _, w in CRITERIA}
    ideal, worst = {}, {}
    for key, _, benefit, _ in CRITERIA:
        values = [c['values'][key] or Decimal(0) for c in board.candidates]
        norm = sum((x * x for x in values), Decimal(0)).sqrt()
        column = []
        for c, x in zip(board.candidates, values):
            c.setdefault('weighted', {})[key] = weights[key] * x / norm if norm else Decimal(0)
            column.append(c['weighted'][key])
        ideal[key], worst[key] = (max(column), min(column)) if benefit else (min(column), max(column))
    for c in board.candidates:
        row = c['weighted']
        to_ideal = sum(((row[k] - ideal[k]) ** 2 for k in row), Decimal(0)).sqrt()
        to_worst = sum(((row[k] - worst[k]) ** 2 for k in row), Decimal(0)).sqrt()
        c['score'] = (to_worst / (to_ideal + to_worst) if to_ideal + to_worst else Decimal('0.5')) * 100
    board.candidates.sort(key=lambda c: c['score'], reverse=True)


def _explain(board):
    """Keep the top five and give each a short reason against the median of all areas in the budget."""
    pool = board.candidates
    def median(key):
        values = sorted(c['values'][key] for c in pool if c['values'][key] is not None)
        return values[len(values) // 2] if values else None
    middle = {key: median(key) for key, *_ in CRITERIA}
    board.facts['median'] = middle
    board.candidates = pool[:TOP]
    for c in board.candidates:
        v, good, bad = c['values'], [], []
        def ratio(key):
            return v[key] / middle[key] if middle[key] else None
        r = ratio('sales_per_store')
        if r and r >= Decimal('1.3'): good.append(f'점포당 매출이 중간값의 {r:.1f}배')
        elif r and r < Decimal('0.8'): bad.append('점포당 매출이 낮은 편')
        r = ratio('footfall')
        if r and r >= Decimal('1.5'): good.append('유동인구가 많음')
        r = ratio('rent')
        if r and r <= Decimal('0.85'): good.append('임대료가 낮은 편')
        elif r and r >= Decimal('1.2'): bad.append('임대료가 높은 편')
        if v['competition'] is not None and middle['competition'] and v['competition'] <= middle['competition'] * Decimal('0.6'):
            good.append('같은 업종 점포가 적음')
        elif v['competition'] is not None and middle['competition'] and v['competition'] >= middle['competition'] * 2:
            bad.append(f"같은 업종 점포 {v['competition']:,.0f}곳 (경쟁 많음)")
        if v['close_rate'] is not None and v['close_rate'] >= 5: bad.append(f"폐업률 {v['close_rate']:.0f}%")
        c['reason'] = ' · '.join(good[:2]) or '여러 기준이 고르게 무난함'
        c['caution'] = ' · '.join(bad[:2])


def recommend_areas(values):
    board = Blackboard(values)
    ControlComponent().run(board, [
        KnowledgeSource('면적·임대료·초기 자금 추정', _estimate_costs),
        KnowledgeSource('임대료 범위와 자료 유무로 거르기', _filter_budget),
        KnowledgeSource('고정 가중치 TOPSIS 순위', _topsis),
        KnowledgeSource('상위 5곳과 추천 이유', _explain),
    ])
    return ResultGenerator().generate(board)
