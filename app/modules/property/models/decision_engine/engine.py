"""Location choice: hard constraints + TOPSIS ranking + weight sensitivity (Blackboard)."""
from decimal import Decimal
from app.common.decision import Blackboard, KnowledgeSource, ControlComponent, ResultGenerator, Criterion, topsis


CANDIDATES = ('a', 'b')
# (criterion key, label, weight field, benefit?)
CRITERIA = (
    ('rent', '월 임대료', 'w_rent', False),
    ('startup', '초기 필요 자금', 'w_startup', False),
    ('area', '면적', 'w_area', True),
    ('fit', '고객층 적합도', 'w_fit', True),
    ('traffic', '동선·유동인구', 'w_traffic', True),
    ('facility', '시설 조건', 'w_facility', True),
)


def _criteria(v, override=None):
    override = override or {}
    return [Criterion(key, label, override.get(key, v[weight]), benefit) for key, label, weight, benefit in CRITERIA]


def _rank(candidates, closeness):
    """Feasible candidates first, then by closeness to the ideal."""
    order = sorted(range(len(candidates)), key=lambda i: (candidates[i]['feasible'], closeness[i]), reverse=True)
    return candidates[order[0]]['key']


def _constraints(board):
    v = board.inputs
    for key in CANDIDATES:
        startup = (v[key+'_deposit'] + v[key+'_rent'] + v[key+'_interior']
                   + v['equipment'] + v['initial_material'] + v['other_startup'])
        checks = (
            (v[key+'_rent'] <= v['budget'], '임대료 예산 이내', '임대료 예산 초과'),
            (v[key+'_area'] >= v['min_area'], '필요 면적 충족', '필요 면적 미달'),
            (startup <= v['available'], '확보 자금으로 충당 가능', '창업 자금 부족'),
        )
        board.candidates.append(dict(
            key=key, name=v[key+'_name'], startup=startup,
            values=dict(rent=v[key+'_rent'], startup=startup, area=v[key+'_area'],
                        fit=v[key+'_fit'], traffic=v[key+'_traffic'], facility=v[key+'_facility']),
            feasible=all(ok for ok, *_ in checks),
            notes=[yes if ok else no for ok, yes, no in checks]))


def _topsis(board):
    closeness = topsis([c['values'] for c in board.candidates], _criteria(board.inputs))
    for c, value in zip(board.candidates, closeness):
        c['closeness'] = value
        c['score'] = value * 100
    board.facts['best'] = _rank(board.candidates, closeness)
    board.candidates.sort(key=lambda c: (c['feasible'], c['closeness']), reverse=True)


def _sensitivity(board):
    """Re-rank with each weight set to 0 and to 5; list criteria that flip the first choice."""
    v, best = board.inputs, board.facts['best']
    sensitive = []
    for key, label, weight, _ in CRITERIA:
        for trial in (Decimal(0), Decimal(5)):
            if trial == v[weight]:
                continue
            criteria = _criteria(v, {key: trial})
            if sum(c.weight for c in criteria) == 0:
                continue
            closeness = topsis([c['values'] for c in board.candidates], criteria)
            if _rank(board.candidates, closeness) != best:
                sensitive.append(f"{label} 중요도 {trial}")
    board.facts['sensitive'] = sensitive


def compare_locations(values):
    board = Blackboard(values)
    ControlComponent().run(board, [
        KnowledgeSource('예산·면적·자금 제약 확인', _constraints),
        KnowledgeSource('TOPSIS 다기준 평가 (이상해 근접도)', _topsis),
        KnowledgeSource('중요도 민감도 분석 (0·5 대입)', _sensitivity),
    ])
    return ResultGenerator().generate(board)
