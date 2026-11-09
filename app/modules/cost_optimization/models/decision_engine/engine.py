from decimal import Decimal
import random
from app.common.decision import Blackboard, KnowledgeSource, ControlComponent, ResultGenerator


CAUTIONS={
    'rent':'재계약·공간 조정 검토: 위약금·이전비·고객 접근성 확인',
    'labor':'근무 동선·업무 배치 개선: 최저임금·근로계약 준수, 서비스 품질 확인',
    'material':'발주·폐기율 점검: 품질·위생·수급 안정성 유지',
    'utilities':'에너지 사용·관리비 점검: 위생·안전 설비 유지',
    'advertising':'채널별 성과 확인 후 재배분: 신규 유입 감소 위험',
    'other':'정기 결제·수수료 점검: 세금·이자·필수 비용 임의 미납 금지',
}
SIMULATIONS=4000
SEED=20261109  # Fixed seed: identical inputs always give identical results.


def _draws(v,categories):
    """Common random numbers so every scenario is compared on the same simulated months."""
    rng=random.Random(SEED)
    keys=[key for key,*_ in categories]
    return [(rng.gauss(0,1),{key:rng.gauss(0,1) for key in keys}) for _ in range(SIMULATIONS)]


def simulate(v,categories,draws,rates):
    """Monthly profit samples. Material cost moves with revenue; other costs vary independently."""
    revenue=float(v['revenue']);sigma_r=float(v['revenue_volatility'])/100;sigma_c=float(v['cost_volatility'])/100
    material_ratio=float(v['material']/v['revenue']) if v['revenue'] else None
    profits=[]
    for z_revenue,z_costs in draws:
        sales=max(0.0,revenue*(1+sigma_r*z_revenue))
        cost=0.0
        for key,*_ in categories:
            keep=1-float(rates.get(key,0))/100
            if key=='material' and material_ratio is not None:
                cost+=sales*material_ratio*keep
            else:
                cost+=max(0.0,float(v[key])*(1+sigma_c*z_costs[key]))*keep
        profits.append(sales-cost)
    return profits


def summarise(profits):
    ordered=sorted(profits)
    return dict(loss=Decimal(str(round(sum(p<0 for p in profits)/len(profits)*100,2))),
                p5=Decimal(str(round(ordered[int(len(ordered)*0.05)]))),
                mean=Decimal(str(round(sum(profits)/len(profits)))))


def compare_savings(v,categories,total):
    board=Blackboard(v, facts={'total':total})
    def structure(b):
        for key,label,*_ in categories:
            b.candidates.append(dict(key=key,label=label,cost=v[key],share=v[key]/total*100 if total else Decimal(0),rate=v[key+'_rate']))
    def scenarios(b):
        for c in b.candidates:
            c['saving']=c['cost']*c['rate']/100
            c['caution']=CAUTIONS[c['key']]
        b.candidates.sort(key=lambda c:c['saving'],reverse=True)
    def risk(b):
        draws=_draws(v,categories)
        all_rates={key:v[key+'_rate'] for key,*_ in categories}
        b.facts['before']=summarise(simulate(v,categories,draws,{}))
        b.facts['after']=summarise(simulate(v,categories,draws,all_rates))
        for c in b.candidates:
            # Risk reduction from this item alone, on the same simulated months.
            alone=summarise(simulate(v,categories,draws,{c['key']:c['rate']}))
            c['risk_drop']=b.facts['before']['loss']-alone['loss']
    ControlComponent().run(board,[KnowledgeSource('비용 구조와 비중 분석',structure),KnowledgeSource('입력 감축률별 대안·위험 종합',scenarios),
                                  KnowledgeSource(f'몬테카를로 적자 위험 시뮬레이션 ({SIMULATIONS:,}회)',risk)])
    return ResultGenerator().generate(board)
