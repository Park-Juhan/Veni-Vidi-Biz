from decimal import Decimal
from app.common.model import AnalysisModel
from app.common.validation import Field
from .decision_engine.engine import compare_locations


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
    ))

    def calculate(self, v):
        decision = compare_locations(v)
        candidates = decision['candidates']
        rows = []
        for c in candidates:
            k=c['key']
            startup = v[k+'_deposit']+v[k+'_rent']+v[k+'_interior']+v['equipment']+v['initial_material']+v['other_startup']
            c['startup'] = startup
            rows.append([c['name'], v[k+'_rent'], v[k+'_deposit'], v[k+'_area'], startup, max(Decimal(0),startup-v['available']), c['score'], ' / '.join(c['notes'])])
        best = candidates[0]
        k=best['key']
        return dict(
            metrics=[('조건 비교 1순위', best['name'], ''), ('해당 후보 초기 필요 자금', best['startup'], '원'), ('월 임대료', v[k+'_rent'], '원')],
            columns=['후보', '월 임대료 (원)', '보증금 (원)', '면적 (㎡)', '초기 필요 자금 (원)', '부족 자금 (원)', '조건 점수 / 100', '검토 사항'], rows=rows,
            chart=[('보증금',v[k+'_deposit']),('첫 달 임대료',v[k+'_rent']),('시설·인테리어',v[k+'_interior']),('장비',v['equipment']),('초기 재료',v['initial_material']),('기타',v['other_startup'])],
            chart_title='조건 비교 1순위 후보의 초기 자금 구성',
            notes=['초기 자금 = 보증금 + 첫 달 임대료 + 시설·인테리어 + 장비 + 초기 재료 + 기타. 보증금은 반환 가능한 묶이는 자금입니다.',
                   '입지 점수는 사용자 평가와 예산·면적 조건을 합산한 시연용 규칙입니다. 실제 유동인구·상권·매물 자료를 조회하지 않습니다.',
                   '점수: 고객층 30점, 동선 20점, 시설 10점, 예산 이내 25점, 필요 면적 충족 15점. 점수가 높아도 미충족 조건을 확인하세요.'], trace=decision['trace'])
