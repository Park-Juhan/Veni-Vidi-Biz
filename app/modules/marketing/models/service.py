from datetime import date
from decimal import Decimal, InvalidOperation
from app.common.model import AnalysisModel
from app.common.validation import Field, ValidationError, validate
from app.integrations.contracts import OperatingCostSnapshot
from .decision_engine.engine import compare_channels

# Channels offered in the recommendation, plus a catch-all for campaigns.
CHANNELS = ('매장 소식·SNS 직접 운영', '동네 소식·재방문 쿠폰', '지역 타깃 광고 대행', '기타')
OWNERS = ('직접', '외부 업체')
CAMPAIGN_FIELDS = (
    Field('name', '캠페인 이름', '', 'text'),
    Field('channel', '채널', '', 'select', choices=CHANNELS),
    Field('owner', '실행 주체', '', 'select', choices=OWNERS),
    Field('cost', '총비용 (원)', ''),
    Field('hours_per_week', '주당 운영 시간', '', maximum='168'),
)
OPTIONAL_NUMBERS = (('new_customers', '신규 고객 수', True), ('revenue_before', '캠페인 전 같은 기간 매출', False), ('revenue_after', '캠페인 기간 매출', False))
MAX_CAMPAIGNS = 200


class MarketingModel(AnalysisModel):
    fields=(
        Field('business','사업 아이템 / 업종','동네 카페','text'),
        Field('target','목표 고객층','인근 직장인','select',choices=('인근 직장인','동네 주민','학생·청년','폭넓은 고객')),
        Field('scale','사업 규모','1인 매장','select',choices=('1인 매장','소규모 팀 매장')),
        Field('goal','홍보 목적','신규 고객 유입','select',choices=('신규 고객 유입','재방문 유도','브랜드 인지도')),
        Field('budget','월 홍보 예산 (원)','300000'),
        Field('hours','주당 운영 가능 시간','4',maximum='168'),
    )

    def __init__(self, repository, campaigns=None):
        super().__init__(repository)
        # Optional campaign log (needs a database).
        self.campaign_store = campaigns

    # ---- Campaign records ----
    @staticmethod
    def validate_campaign(raw):
        values = validate(CAMPAIGN_FIELDS, raw)
        values['name'] = values['name'].strip()
        errors = []
        try:
            started, ended = date.fromisoformat(str(raw.get('started_on', ''))), date.fromisoformat(str(raw.get('ended_on', '')))
            if ended < started:
                errors.append('종료일이 시작일보다 빠릅니다.')
            values['started_on'], values['ended_on'] = started.isoformat(), ended.isoformat()
        except ValueError:
            errors.append('시작일과 종료일을 YYYY-MM-DD 날짜로 입력하세요.')
        for key, label, integer in OPTIONAL_NUMBERS:
            text = str(raw.get(key) or '').strip()
            if not text:
                values[key] = None; continue
            try:
                number = Decimal(text)
                if not number.is_finite() or number < 0 or number > Decimal(10**12) or (integer and number != number.to_integral_value()):
                    raise InvalidOperation
                values[key] = number
            except (InvalidOperation, ValueError):
                errors.append(f"{label}: 0 이상의 {'정수' if integer else '숫자'}로 입력하거나 비워 두세요.")
        if (values.get('revenue_before') is None) != (values.get('revenue_after') is None):
            errors.append('매출 변화는 캠페인 전·기간 매출을 둘 다 입력해야 계산됩니다.')
        if errors:
            raise ValidationError(' / '.join(errors))
        values['note'] = str(raw.get('note') or '').strip()[:200]
        return values

    @staticmethod
    def campaign_metrics(c):
        """Per-campaign results from user-entered figures. None where not measured."""
        cost = Decimal(c['cost'])
        customers = Decimal(c['new_customers']) if c.get('new_customers') not in (None, '') else None
        lift = (Decimal(c['revenue_after']) - Decimal(c['revenue_before'])) if c.get('revenue_after') not in (None, '') else None
        return dict(days=(date.fromisoformat(c['ended_on']) - date.fromisoformat(c['started_on'])).days + 1,
                    cost_value=cost, customers=customers,
                    cac=cost / customers if customers else None,
                    lift=lift, roi=(lift - cost) / cost * 100 if lift is not None and cost else None)

    def list_campaigns(self, workspace):
        if not self.campaign_store: return []
        campaigns = self.campaign_store.list(workspace)
        for c in campaigns:
            c.update(self.campaign_metrics(c))
        return campaigns

    def channel_summary(self, workspace):
        """Per channel: runs, total cost, measured new customers and average cost per new customer."""
        summary = {}
        for c in self.list_campaigns(workspace):
            s = summary.setdefault(c['channel'], dict(channel=c['channel'], runs=0, cost=Decimal(0), measured_cost=Decimal(0),
                                                      customers=Decimal(0), lift_cost=Decimal(0), lift=Decimal(0), lift_runs=0))
            s['runs'] += 1; s['cost'] += c['cost_value']
            if c['customers'] is not None:
                s['measured_cost'] += c['cost_value']; s['customers'] += c['customers']
            if c['lift'] is not None:
                s['lift_cost'] += c['cost_value']; s['lift'] += c['lift']; s['lift_runs'] += 1
        for s in summary.values():
            s['cac'] = s['measured_cost'] / s['customers'] if s['customers'] else None
            s['roi'] = (s['lift'] - s['lift_cost']) / s['lift_cost'] * 100 if s['lift_runs'] and s['lift_cost'] else None
        return sorted(summary.values(), key=lambda s: (s['cac'] is None, s['cac'] or 0))

    def save_campaign(self, workspace, raw, campaign_id=None):
        if not self.campaign_store: return None
        values = self.validate_campaign(raw)
        if campaign_id is None and len(self.campaign_store.list(workspace)) >= MAX_CAMPAIGNS:
            raise ValidationError(f'캠페인은 최대 {MAX_CAMPAIGNS}건까지 기록할 수 있습니다.')
        return self.campaign_store.save(workspace, values, campaign_id)

    def delete_campaign(self, workspace, campaign_id):
        return bool(self.campaign_store and self.campaign_store.delete(workspace, campaign_id))

    def forget(self, workspace):
        super().forget(workspace)
        if self.campaign_store: self.campaign_store.forget(workspace)

    # ---- Recommendation ----
    def prepare(self, values, raw):
        # Own campaign summary (added by the controller) is shown next to each recommended channel.
        return values | {'history': {s['channel']: s for s in raw.get('history') or []}}

    def calculate(self,v):
        decision=compare_channels(v)
        candidates=decision['candidates']
        eligible=[c for c in candidates if c['feasible']]
        history=v.get('history') or {}

        def own(name):
            s=history.get(name)
            if not s: return '기록 없음'
            text=f"{s['runs']}회 · 총 {Decimal(s['cost']):,.0f}원"
            if s.get('cac') is not None: text+=f" · 신규 1명당 {Decimal(s['cac']):,.0f}원"
            if s.get('roi') is not None: text+=f" · 수익률 {Decimal(s['roi']):,.0f}%"
            return text
        notes=['비용·시간은 실제 업체 견적이 아닌 가상 시연 값입니다. 업체명과 실제 광고 성과 자료는 제공하지 않습니다.',
               '규칙: 목표 고객층 +2점, 홍보 목적 +2점, 1인 운영 시 저시간 채널 +1점. 예산·시간을 모두 충족하는 방법을 우선 정렬합니다.',
               f"업종 '{v['business']}'은 검토 맥락으로 기록합니다. 업종별 효과 차이를 추정할 자료는 없습니다.",
               '매출 증가·ROI는 예측하지 않습니다. 광고비 외 제작비·계약 기간·수수료를 실제 실행 전에 확인하세요.']
        if history:
            notes.insert(2,"'내 캠페인 기록'은 이 작업 공간에 기록한 실제 캠페인 결과입니다. 점수에는 반영하지 않고 참고로만 보여 줍니다.")
        return dict(metrics=[('조건에 맞는 방법',len(eligible),'개'),('월 홍보 예산',v['budget'],'원'),('주당 가용 시간',v['hours'],'시간')],
                    columns=['방법','실행 주체','가상 월 비용 (원)','주당 시간','조건','적합 점수','내 캠페인 기록','장점','유의사항'],
                    rows=[[c['name'],c['owner'],c['cost'],c['hours'],'검토 가능' if c['feasible'] else '예산 또는 시간 초과',c['score'],own(c['name']),c['benefit'],c['caution']] for c in candidates],
                    chart=[(c['name'],c['cost']) for c in candidates],chart_title='시연용 마케팅 비용 비교',budget=v['budget'],
                    notes=notes+([] if eligible else ['현재 예산과 시간에 모두 맞는 방법이 없습니다. 조건을 조정하거나 작은 실험을 계획하세요.']),trace=decision['trace'])

    def export_operating_costs(self, workspace):
        record = self.latest(workspace)
        if record is None or 'budget' not in record.result:
            return None
        return OperatingCostSnapshot(detail='월 홍보 예산', source=record.source,
                                     updated_at=record.updated_at, monthly_advertising=record.result['budget'])
