from decimal import Decimal
from app.common.decision import Blackboard, KnowledgeSource, ControlComponent, ResultGenerator
from app.common.validation import ValidationError


# (key, label, benefit=True if larger is better). Weight input field is 'w_' + key.
CRITERIA = (
    ('fit', '고객층 적합도', True),
    ('traffic', '이동 동선·유동인구', True),
    ('facility', '시설 조건', True),
    ('rent', '월 임대료', False),
    ('startup', '초기 필요 자금', False),
    ('area', '면적', True),
)


def _cost_conditions(board):
    v=board.inputs
    common=v['equipment']+v['initial_material']+v['other_startup']
    for key in ('a','b'):
        budget_ok=v[key+'_rent'] <= v['budget']
        area_ok=v[key+'_area'] >= v['min_area']
        startup=v[key+'_deposit']+v[key+'_rent']+v[key+'_interior']+common
        board.candidates.append(dict(
            key=key,name=v[key+'_name'],startup=startup,meets=budget_ok and area_ok,
            notes=['임대료 예산 이내' if budget_ok else '임대료 예산 초과','필요 면적 충족' if area_ok else '필요 면적 미달'],
            values=dict(fit=v[key+'_fit'],traffic=v[key+'_traffic'],facility=v[key+'_facility'],rent=v[key+'_rent'],startup=startup,area=v[key+'_area'])))


def _topsis(board):
    """TOPSIS: rank by relative closeness to the ideal and distance from the worst on weighted criteria."""
    v=board.inputs
    raw={key:v['w_'+key] for key,*_ in CRITERIA}
    total=sum(raw.values(),Decimal(0))
    if total<=0:
        raise ValidationError('평가 가중치를 하나 이상 0보다 크게 입력해 주세요.')
    weights={key:w/total for key,w in raw.items()}
    weighted={id(c):{} for c in board.candidates}
    ideal,worst={},{}
    for key,_,benefit in CRITERIA:
        norm=sum((c['values'][key]**2 for c in board.candidates),Decimal(0)).sqrt()
        column=[]
        for c in board.candidates:
            value=weights[key]*c['values'][key]/norm if norm else Decimal(0)
            weighted[id(c)][key]=value; column.append(value)
        ideal[key],worst[key]=(max(column),min(column)) if benefit else (min(column),max(column))
    for c in board.candidates:
        row=weighted[id(c)]
        to_ideal=sum(((row[k]-ideal[k])**2 for k in row),Decimal(0)).sqrt()
        to_worst=sum(((row[k]-worst[k])**2 for k in row),Decimal(0)).sqrt()
        c['closeness']=to_worst/(to_ideal+to_worst) if to_ideal+to_worst else Decimal('0.5')
        c['score']=c['closeness']*100
    board.facts['weights']=weights
    # Candidates meeting budget and area come first; TOPSIS orders within each group.
    board.candidates.sort(key=lambda c:(c['meets'],c['closeness']),reverse=True)


def compare_locations(values):
    board=Blackboard(values)
    ControlComponent().run(board, [KnowledgeSource('예산·면적 조건과 초기 자금 확인',_cost_conditions),KnowledgeSource('가중치 기반 TOPSIS 비교',_topsis)])
    return ResultGenerator().generate(board)
