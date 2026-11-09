from decimal import Decimal
from app.common.model import AnalysisModel
from app.common.validation import Field
from .decision_engine.engine import SIMULATIONS, compare_savings


CATEGORIES=(('rent','임대료','1500000','0'),('labor','인건비','3000000','0'),('material','재료비','2500000','10'),('utilities','공과금·관리비','400000','5'),('advertising','광고비','300000','10'),('other','기타 고정비 (세금·이자 등)','300000','0'))


class CostOptimizationModel(AnalysisModel):
    fields=(Field('revenue','월 예상 매출 (원)','12000000'),Field('previous','이전 월 총비용 (원)','8500000',help='이전 월과 현재 월의 조건이 다르면 직접 비교에 한계가 있습니다.'))+tuple(
        field for key,label,default,rate in CATEGORIES for field in (
            Field(key,label+' (원/월)',default,group='월 운영 비용'),
            Field(key+'_rate',label+' 절감 가정 (%)',rate,maximum='100',group='항목별 절감 시나리오'),
        ))+(
        Field('revenue_volatility','월 매출 변동성 (%)','20',maximum='100',group='불확실성 가정',help='평소 매출이 평균에서 벗어나는 정도(표준편차). 계절·날씨 영향이 크면 크게 입력하세요.'),
        Field('cost_volatility','비용 변동성 (%)','5',maximum='100',group='불확실성 가정',help='재료비 외 비용이 달마다 달라지는 정도(표준편차).'),
    )

    def calculate(self,v):
        amounts={key:v[key] for key,*_ in CATEGORIES}
        total=sum(amounts.values(),Decimal(0))
        decision=compare_savings(v,CATEGORIES,total)
        before,after=decision['facts']['before'],decision['facts']['after']
        savings=sum((c['saving'] for c in decision['candidates']),Decimal(0))
        profit=v['revenue']-total
        fixed=total-v['material']
        contribution=1-v['material']/v['revenue'] if v['revenue'] else None
        breakeven=fixed/contribution if contribution is not None and contribution>0 else None
        safety=(v['revenue']-breakeven)/v['revenue']*100 if breakeven is not None else None
        notes=['비용은 월 단위입니다. 재료비만 매출 비례 변동비로, 나머지는 고정비로 가정합니다. 임금 관련 법적 의무와 계약 조건을 확인하세요.',
               '손익분기 매출 = 고정비 ÷ (1 - 재료비/매출). 안전한계율 = (매출 - 손익분기 매출) ÷ 매출. 매출이 이 비율 이상 줄면 적자입니다.',
               f'몬테카를로 시뮬레이션: 매출을 정규분포(표준편차 {v["revenue_volatility"]}%)로, 재료비 외 비용을 각각 정규분포(표준편차 {v["cost_volatility"]}%)로 {SIMULATIONS:,}개월 생성해 적자가 나는 달의 비율을 셉니다. 재료비는 매출에 비례해 움직입니다.',
               '절감 전·후와 항목별 효과는 같은 난수(가상의 같은 달들)로 비교합니다. 같은 입력이면 항상 같은 결과가 나오도록 난수 시드를 고정했습니다.',
               '하위 5% 손익은 20번 중 1번 정도 나올 수 있는 나쁜 달의 손익입니다. 이 금액 이상의 운영 예비 자금을 준비하는 기준으로 쓸 수 있습니다.',
               '변동성은 입력한 가정값입니다. 실제 월별 매출 기록이 있으면 그 표준편차를 입력하세요. 절감 효과는 매출·품질이 유지된다는 가정이며 실현을 보장하지 않습니다.']
        if breakeven is None: notes.append('매출이 0이거나 재료비 비율이 100% 이상이어서 유효한 손익분기 매출을 산출할 수 없습니다.')
        if total==0: notes.append('운영 비용이 모두 0입니다. 누락된 비용을 확인하세요.')
        candidates=decision['candidates']
        best=max(candidates,key=lambda c:(c['risk_drop'],c['saving']))
        if best['risk_drop']>0:
            notes.insert(0,f"적자 위험을 가장 크게 줄이는 단일 항목: {best['label']} (적자 확률 {best['risk_drop']}%p 감소).")
        return dict(model='몬테카를로 적자 위험 시뮬레이션',
                    metrics=[('월 총비용',total,'원'),('절감 전 운영 손익',profit,'원'),('가정상 월 절감액',savings,'원'),('절감 후 운영 손익',profit+savings,'원'),
                             ('적자 확률 (절감 전)',before['loss'],'%'),('적자 확률 (절감 후)',after['loss'],'%'),
                             ('하위 5% 월 손익 (절감 후)',after['p5'],'원'),
                             ('손익분기 월 매출',breakeven if breakeven is not None else '산출 불가','원' if breakeven is not None else ''),
                             ('안전한계율',safety if safety is not None else '산출 불가','%' if safety is not None else ''),
                             ('이전 월 대비 비용 증감',total-v['previous'],'원')],
                    columns=['항목','현재 비용 (원)','비중 (%)','절감 가정 (%)','월 절감액 (원)','절감 후 비용 (원)','이 항목만 절감 시 적자 확률 감소 (%p)','검토할 대안·위험'],
                    rows=[[c['label'],c['cost'],c['share'],c['rate'],c['saving'],c['cost']-c['saving'],c['risk_drop'],c['caution']] for c in candidates],
                    charts=[dict(title='현재 월 비용 구성',unit='원',data=[(label,v[key]) for key,label,*_ in CATEGORIES]),
                            dict(title='적자 확률 비교',unit='%',data=[('절감 전',before['loss']),('절감 후',after['loss'])])],
                    notes=notes,trace=decision['trace'],total=total,savings=savings,breakeven=breakeven,loss_before=before['loss'],loss_after=after['loss'])
