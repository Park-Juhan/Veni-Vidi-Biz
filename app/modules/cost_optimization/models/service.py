from decimal import Decimal
from app.common.model import AnalysisModel
from app.common.validation import Field, ValidationError, validate
import re
from app.common.time import korean_time
from .decision_engine.engine import compare_savings
from .sensitivity import sensitivity_table


CATEGORIES=(('rent','임대료','1500000','0'),('labor','인건비','3000000','0'),('material','재료비','2500000','10'),('utilities','공과금·관리비','400000','5'),('advertising','광고비','300000','10'),('other','기타 고정비 (세금·이자 등)','300000','0'))


class CostOptimizationModel(AnalysisModel):
    fields=(Field('revenue','월 예상 매출 (원)','12000000'),Field('previous','이전 월 총비용 (원)','8500000',help='이전 월과 현재 월의 조건이 다르면 직접 비교에 한계가 있습니다.'))+tuple(
        field for key,label,default,rate in CATEGORIES for field in (
            Field(key,label+' (원/월)',default,group='월 운영 비용'),
            Field(key+'_rate',label+' 절감 가정 (%)',rate,maximum='100',group='항목별 절감 시나리오'),
        ))

    # Snapshot attribute -> this module's input field.
    IMPORTABLE=(('monthly_revenue','revenue'),('monthly_rent','rent'),('monthly_material','material'),('monthly_advertising','advertising'))

    PERIOD=re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')
    MONTH_ITEMS=('revenue','rent','labor','material','utilities','advertising','other')

    def __init__(self,repository,cost_providers=(),financials=None):
        super().__init__(repository)
        # (module title, OperatingCostProvider) pairs wired by the composition root.
        self.cost_providers=tuple(cost_providers)
        # Optional monthly revenue/cost history (needs a database).
        self.financials=financials

    # ---- Monthly records ----
    def list_months(self,workspace):
        """Saved months, newest first, with total cost, profit and change vs the month before."""
        if not self.financials: return []
        months=self.financials.list(workspace)
        for month in months:
            month['total']=sum((month[key] for key,*_ in CATEGORIES),Decimal(0))
            month['profit']=month['revenue']-month['total']
            month['material_ratio']=month['material']/month['revenue']*100 if month['revenue'] else None
        for newer,older in zip(months,months[1:]):
            newer['profit_change']=newer['profit']-older['profit']
        return months

    def save_month(self,workspace,period,raw):
        if not self.financials: return False
        if not self.PERIOD.match(period or ''):
            raise ValidationError('기록할 월을 YYYY-MM 형식으로 선택하세요.')
        v=validate(self.fields,raw)
        self.financials.save(workspace,period,{key:v[key] for key in self.MONTH_ITEMS})
        return True

    def month_values(self,workspace,period):
        """Form values for a saved month (saving rates keep their defaults), or None."""
        month=next((m for m in self.list_months(workspace) if m['period']==period),None)
        if month is None: return None
        values=self.defaults()
        values.update({key:f'{month[key].normalize():f}' for key in self.MONTH_ITEMS})
        previous=self.previous_total(workspace,period)
        if previous is not None: values['previous']=f'{previous[1].normalize():f}'
        return values

    def previous_total(self,workspace,period=None):
        """(period, total cost) of the latest saved month before `period` (or the latest overall)."""
        for month in self.list_months(workspace):
            if period is None or month['period']<period:
                return month['period'],month['total']
        return None

    def delete_month(self,workspace,period):
        return bool(self.financials and self.financials.delete(workspace,period))

    def forget(self,workspace):
        super().forget(workspace)
        if self.financials: self.financials.forget(workspace)

    def import_operating_costs(self,workspace,period=None):
        """Collect monthly figures other modules computed for this workspace.

        Returns values (field -> plain decimal text), origins (field -> label) and
        missing (titles of modules with no saved result). The first provider wins per field.
        """
        values,origins,missing={},{},[]
        for title,provider in self.cost_providers:
            snapshot=provider.export_operating_costs(workspace)
            if snapshot is None:
                missing.append(title); continue
            label=f'{title} · {snapshot.detail} · {korean_time(snapshot.updated_at)}'
            if '가상' in snapshot.source: label+=' · 가상 예시'
            for attribute,field in self.IMPORTABLE:
                value=getattr(snapshot,attribute)
                if value is not None and field not in values:
                    values[field]=f'{value.normalize():f}'; origins[field]=label
        previous=self.previous_total(workspace,period if period and self.PERIOD.match(period) else None)
        if previous:
            values['previous']=f'{previous[1].normalize():f}'; origins['previous']=f'05 월별 기록 · {previous[0]} 총비용'
        return dict(values=values,origins=origins,missing=missing)

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
                    chart=[(label,v[key]) for key,label,*_ in CATEGORIES],extra_tables=[sensitivity_table(v,total)],chart_title='현재 월 비용 구성',notes=notes,trace=decision['trace'],total=total,savings=savings,breakeven=breakeven)
