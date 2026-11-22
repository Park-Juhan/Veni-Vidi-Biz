from decimal import Decimal
from app.common.model import AnalysisModel
from app.common.validation import Field
from app.integrations.contracts import OperatingCostSnapshot
from .decision_engine.engine import CRITERIA, compare_locations


class PropertyModel(AnalysisModel):
    fields = (
        Field('business', '사업 아이템 / 업종', '동네 카페', 'text'),
        Field('target', '주요 고객층', '인근 직장인', 'text'),
        Field('budget', '월 임대료 예산 (원)', '1500000'),
        Field('min_area', '필요 면적 (㎡)', '30', minimum='0.1'),
        Field('available', '확보한 창업 자금 (원)', '60000000'),
        Field('equipment', '장비 구입비 (원)', '12000000', group='공통 초기 자금'),
        Field('initial_material', '초기 재료비 (원)', '1500000', group='공통 초기 자금'),
        Field('other_startup', '기타 초기 비용 (원)', '2000000', group='공통 초기 자금'),
    ) + tuple(field for key, title, defaults in (
        ('a', '후보 A', ('가상 역세권 A', '1800000', '20000000', '40', '15000000', '4', '3', '4')),
        ('b', '후보 B', ('가상 주거지 B', '1200000', '15000000', '35', '18000000', '3', '4', '3')),
    ) for field in (
        Field(key+'_name', '후보 지역 / 이름', defaults[0], 'text', group=title),
        Field(key+'_rent', '월 임대료 (원)', defaults[1], group=title),
        Field(key+'_deposit', '보증금 (원)', defaults[2], group=title),
        Field(key+'_area', '면적 (㎡)', defaults[3], minimum='0.1', group=title),
        Field(key+'_interior', '시설·인테리어 비용 (원)', defaults[4], group=title),
        Field(key+'_fit', '고객층 적합도 (직접 평가 1~5)', defaults[5], minimum='1', maximum='5', step='1', group=title),
        Field(key+'_traffic', '이동 동선·유동인구 적합도 (직접 평가 1~5)', defaults[6], minimum='1', maximum='5', step='1', group=title),
        Field(key+'_facility', '시설 조건 적합도 (직접 평가 1~5)', defaults[7], minimum='1', maximum='5', step='1', group=title),
    )) + tuple(
        Field('w_'+key, label+' 가중치', default, maximum='100', step='1', group='평가 가중치',
              help=help_text)
        for (key, label, _), default, help_text in zip(CRITERIA, ('30', '20', '10', '15', '15', '10'), (
            '숫자가 클수록 중요합니다. 합계가 100이 아니어도 비율로 환산합니다.', '', '', '낮을수록 유리한 기준입니다.', '낮을수록 유리한 기준입니다.', ''))
    )

    def calculate(self, v):
        decision = compare_locations(v)
        candidates = decision['candidates']
        rows = []
        for c in candidates:
            k=c['key']
            rows.append([c['name'], v[k+'_rent'], v[k+'_deposit'], v[k+'_area'], c['startup'], max(Decimal(0),c['startup']-v['available']), c['score'], ' / '.join(c['notes'])])
        weights = decision['facts']['weights']
        criteria_rows = []
        for key, label, benefit in CRITERIA:
            values = [c['values'][key] for c in candidates]
            best_value = max(values) if benefit else min(values)
            winners = [c['name'] for c in candidates if c['values'][key] == best_value]
            criteria_rows.append([label, weights[key]*100, '높을수록 유리' if benefit else '낮을수록 유리', *values,
                                  '동일' if len(winners) == len(candidates) else ', '.join(winners)])
        best = candidates[0]
        k=best['key']
        return dict(
            metrics=[('조건 비교 1순위', best['name'], ''), ('해당 후보 초기 필요 자금', best['startup'], '원'), ('월 임대료', v[k+'_rent'], '원')],
            columns=['후보', '월 임대료 (원)', '보증금 (원)', '면적 (㎡)', '초기 필요 자금 (원)', '부족 자금 (원)', 'TOPSIS 근접도 (0~100)', '검토 사항'], rows=rows,
            extra_tables=[dict(tab='기준별 비교', title='평가 기준별 값과 가중치', lead='각 기준에서 유리한 후보와 반영 비중입니다. 가중치를 바꾸면 순위가 달라질 수 있습니다.',
                               columns=['기준', '가중치 (%)', '방향', *[c['name'] for c in candidates], '유리한 후보'], rows=criteria_rows,
                               note='적합도 1~5점은 사용자가 직접 평가한 값입니다.')],
            chart=[('보증금',v[k+'_deposit']),('첫 달 임대료',v[k+'_rent']),('시설·인테리어',v[k+'_interior']),('장비',v['equipment']),('초기 재료',v['initial_material']),('기타',v['other_startup'])],
            chart_title='조건 비교 1순위 후보의 초기 자금 구성',best_name=best['name'],best_rent=v[k+'_rent'],
            notes=['초기 자금 = 보증금 + 첫 달 임대료 + 시설·인테리어 + 장비 + 초기 재료 + 기타. 보증금은 반환 가능한 묶이는 자금입니다.',
                   'TOPSIS: 기준마다 값을 정규화하고 가중치를 곱한 뒤, 가장 좋은 값(이상해)에 가깝고 가장 나쁜 값에서 먼 정도를 0~100 근접도로 계산합니다.',
                   '순위: 임대료 예산과 필요 면적을 모두 충족한 후보를 먼저 두고, 같은 그룹 안에서 근접도가 높은 순으로 정렬합니다.',
                   '후보가 2곳이면 기준마다 한 후보가 이상해가 되므로 근접도가 0 또는 100 쪽으로 치우칠 수 있습니다. 기준별 비교 탭에서 이유를 확인하세요.',
                   '적합도는 사용자 평가입니다. 실제 유동인구·상권·매물 자료를 조회하지 않습니다.'], trace=decision['trace'])

    def export_operating_costs(self, workspace):
        record = self.latest(workspace)
        if record is None or 'best_rent' not in record.result:
            return None
        return OperatingCostSnapshot(detail=f"1순위 후보 {record.result['best_name']}", source=record.source,
                                     updated_at=record.updated_at, monthly_rent=record.result['best_rent'])
