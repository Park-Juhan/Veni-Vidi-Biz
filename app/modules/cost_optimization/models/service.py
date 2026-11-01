from decimal import Decimal
from app.common.model import AnalysisModel
from app.common.validation import Field
from .decision_engine.engine import compare_savings


CATEGORIES=(('rent','임대료','1500000','0'),('labor','인건비','3000000','0'),('material','재료비','2500000','10'),('utilities','공과금·관리비','400000','5'),('advertising','광고비','300000','10'),('other','기타 고정비 (세금·이자 등)','300000','0'))


class CostOptimizationModel(AnalysisModel):
    fields=(Field('revenue','월 예상 매출 (원)','12000000'),Field('previous','이전 월 총비용 (원)','8500000',help='이전 월과 현재 월의 조건이 다르면 직접 비교에 한계가 있습니다.'))+tuple(
        field for key,label,default,rate in CATEGORIES for field in (
            Field(key,label+' (원/월)',default,group='월 운영 비용'),
            Field(key+'_rate',label+' 절감 가정 (%)',rate,maximum='100',group='항목별 절감 시나리오'),
        ))

    def calculate(self,v):
        amounts={key:v[key] for key,*_ in CATEGORIES}
        total=sum(amounts.values(),Decimal(0))
        decision=compare_savings(v,CATEGORIES,total)
        savings=sum((c['saving'] for c in decision['candidates']),Decimal(0))
        profit=v['revenue']-total
        fixed=total-v['material']
        contribution=1-v['material']/v['revenue'] if v['revenue'] else None
        breakeven=fixed/contribution if contribution is not None and contribution>0 else None
        notes=['비용은 월 단위입니다. 재료비만 매출 비례 변동비로, 나머지는 고정비로 가정합니다. 임금 관련 법적 의무와 계약 조건을 확인하세요.',
               '손익분기 매출 = 고정비 ÷ (1 - 재료비/매출). 실제 비용 구조가 다르면 이 가정에 맞춰 입력하거나 후속 모델 확장이 필요합니다.',
               '절감액은 입력한 감축률을 적용한 시나리오입니다. 매출과 서비스 품질이 유지된다는 가정이며 실제 실현을 보장하지 않습니다.',
               '운영 손익은 입력된 비용만 차감한 계산입니다. 누락한 세금·이자·수수료 등이 있으면 실제 손익과 다릅니다.']
        if breakeven is None: notes.append('매출이 0이거나 재료비 비율이 100% 이상이어서 유효한 손익분기 매출을 산출할 수 없습니다.')
        if total==0: notes.append('운영 비용이 모두 0입니다. 누락된 비용을 확인하세요.')
        return dict(metrics=[('월 총비용',total,'원'),('절감 전 운영 손익',profit,'원'),('가정상 월 절감액',savings,'원'),('절감 후 운영 손익',profit+savings,'원'),('손익분기 월 매출',breakeven if breakeven is not None else '산출 불가','원' if breakeven is not None else ''),('이전 월 대비 비용 증감',total-v['previous'],'원')],
                    columns=['항목','현재 비용 (원)','비중 (%)','절감 가정 (%)','월 절감액 (원)','절감 후 비용 (원)','검토할 대안·위험'],
                    rows=[[c['label'],c['cost'],c['share'],c['rate'],c['saving'],c['cost']-c['saving'],c['caution']] for c in decision['candidates']],
                    chart=[(label,v[key]) for key,label,*_ in CATEGORIES],chart_title='현재 월 비용 구성',notes=notes,trace=decision['trace'],total=total,savings=savings,breakeven=breakeven)
