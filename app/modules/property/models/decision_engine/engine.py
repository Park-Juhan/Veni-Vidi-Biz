from decimal import Decimal
from app.common.decision import Blackboard, KnowledgeSource, ControlComponent, ResultGenerator


def _cost_conditions(board):
    v=board.inputs
    for key in ('a','b'):
        notes=[]
        budget_ok=v[key+'_rent'] <= v['budget']
        area_ok=v[key+'_area'] >= v['min_area']
        notes.append('임대료 예산 이내' if budget_ok else '임대료 예산 초과')
        notes.append('필요 면적 충족' if area_ok else '필요 면적 미달')
        board.candidates.append(dict(key=key,name=v[key+'_name'],score=Decimal(25*budget_ok+15*area_ok),notes=notes))


def _fit_conditions(board):
    for c in board.candidates:
        v=board.inputs; k=c['key']
        c['score'] += v[k+'_fit']*6+v[k+'_traffic']*4+v[k+'_facility']*2
    board.candidates.sort(key=lambda c:c['score'],reverse=True)


def compare_locations(values):
    board=Blackboard(values)
    ControlComponent().run(board, [KnowledgeSource('예산·면적 조건 비교',_cost_conditions),KnowledgeSource('고객층·동선·시설 평가 종합',_fit_conditions)])
    return ResultGenerator().generate(board)
