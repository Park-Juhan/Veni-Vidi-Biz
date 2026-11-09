from decimal import Decimal, ROUND_CEILING
from itertools import combinations
from app.common.decision import Blackboard, KnowledgeSource, ControlComponent, ResultGenerator


def _channels(board):
    # Fictional comparison fixtures, not market observations or supplier quotes.
    specs=[
        ('매장 소식·SNS 직접 운영','직접',50000,5,('학생·청년','폭넓은 고객'),('브랜드 인지도',),'콘텐츠를 직접 조정','제작 시간과 꾸준한 운영 필요'),
        ('동네 소식·재방문 쿠폰','직접',100000,2,('동네 주민','인근 직장인'),('재방문 유도',),'생활권 고객과 접점','쿠폰 할인액은 별도 비용'),
        ('지역 타깃 광고 대행','외부 업체',400000,1,('인근 직장인','폭넓은 고객'),('신규 고객 유입','브랜드 인지도'),'운영 시간을 줄일 수 있음','계약·수수료·성과 지표 확인'),
    ]
    for name,owner,cost,hours,targets,goals,benefit,caution in specs:
        board.candidates.append(dict(name=name,owner=owner,cost=Decimal(cost),hours=Decimal(hours),targets=targets,goals=goals,benefit=benefit,caution=caution))


def _constraints(board):
    v=board.inputs
    for c in board.candidates:
        c['feasible']=c['cost']<=v['budget'] and c['hours']<=v['hours']
        c['score']=2*(v['target'] in c['targets'])+2*(v['goal'] in c['goals'])+int(v['scale']=='1인 매장' and c['hours']<=2)
    board.candidates.sort(key=lambda c:(c['feasible'],c['score']),reverse=True)


def _breakeven(board):
    v=board.inputs
    unit=v['ticket']*v['contribution_rate']/100
    for c in board.candidates:
        # Extra customers per month whose contribution pays back the channel cost.
        c['breakeven']=(c['cost']/unit).to_integral_value(rounding=ROUND_CEILING) if unit>0 else None


def _portfolio(board):
    """0-1 knapsack by enumeration: maximise total fit score within budget and hours."""
    v=board.inputs
    best=()
    for size in range(1,len(board.candidates)+1):
        for combo in combinations(board.candidates,size):
            cost=sum(c['cost'] for c in combo);hours=sum(c['hours'] for c in combo)
            if cost>v['budget'] or hours>v['hours']: continue
            key=(sum(c['score'] for c in combo),-cost,-hours)
            if not best or key>best[0]: best=(key,combo)
    combo=best[1] if best else ()
    board.facts['portfolio']=[c['name'] for c in combo]
    board.facts['portfolio_cost']=sum((c['cost'] for c in combo),Decimal(0))
    board.facts['portfolio_hours']=sum((c['hours'] for c in combo),Decimal(0))
    board.facts['portfolio_score']=sum(c['score'] for c in combo)


def compare_channels(v):
    board=Blackboard(v)
    ControlComponent().run(board,[KnowledgeSource('가상 채널·직접/업체 대안 준비',_channels),KnowledgeSource('예산·시간 제약 및 고객층·목적 비교',_constraints),
                                  KnowledgeSource('광고 손익분기 고객 수 계산',_breakeven),KnowledgeSource('예산·시간 제약 하 채널 조합 최적화 (0-1 배낭 문제)',_portfolio)])
    return ResultGenerator().generate(board)
