from decimal import Decimal
from app.common.model import AnalysisModel
from app.common.validation import Field, ValidationError
from .decision_engine.engine import CRITERIA, compare_locations


WEIGHT_DEFAULTS = {'w_rent': '4', 'w_startup': '3', 'w_area': '2', 'w_fit': '5', 'w_traffic': '4', 'w_facility': '2'}
WEIGHT_GROUP = '평가 기준 중요도'


class PropertyModel(AnalysisModel):
    # Declaration order is the step order of the input wizard.
    fields = (
        Field('business', '사업 아이템 / 업종', '동네 카페', 'text'),
        Field('target', '주요 고객층', '인근 직장인', 'text'),
        Field('budget', '월 임대료 예산 (원)', '1500000'),
        Field('min_area', '필요 면적 (㎡)', '30', minimum='0.1'),
        Field('available', '확보한 창업 자금 (원)', '60000000'),
        Field('equipment', '장비 구입비 (원)', '12000000', group='공통 초기 자금'),
        Field('initial_material', '초기 재료비 (원)', '1500000', group='공통 초기 자금'),
        Field('other_startup', '기타 초기 비용 (원)', '2000000', group='공통 초기 자금', help='권리금·인허가·초기 홍보 등'),
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
        Field(weight, f'{label} 중요도 (0~5)', WEIGHT_DEFAULTS[weight], minimum='0', maximum='5', step='1', group=WEIGHT_GROUP,
              help='0이면 평가에서 제외합니다.' if weight == 'w_rent' else '')
        for _, label, weight, _ in CRITERIA)

    def calculate(self, v):
        if all(v[weight] == 0 for *_, weight, _ in CRITERIA):
            raise ValidationError('평가 기준 중요도 중 하나 이상은 1 이상이어야 합니다.')
        decision = compare_locations(v)
        candidates = decision['candidates']
        best = next(c for c in candidates if c['key'] == decision['facts']['best'])
        k = best['key']
        rows = [[c['name'], v[c['key']+'_rent'], v[c['key']+'_deposit'], v[c['key']+'_area'], c['startup'],
                 max(Decimal(0), c['startup']-v['available']), '충족' if c['feasible'] else '미충족',
                 c['score'], ' / '.join(c['notes'])] for c in candidates]
        sensitive = decision['facts']['sensitive']
        notes = [
            'TOPSIS(이상해 근접 순위법): 각 기준을 벡터 정규화하고 중요도로 가중한 뒤, 가장 좋은 가상 후보(이상해)와 '
            '가장 나쁜 가상 후보(반이상해)까지의 거리로 근접도 = 반이상해 거리 ÷ (이상해 거리 + 반이상해 거리)를 계산합니다. 100에 가까울수록 좋습니다.',
            '임대료 예산·필요 면적·창업 자금 세 가지 제약을 모두 충족한 후보를 먼저 추천하고, 그 안에서 근접도가 높은 순서로 정렬합니다.',
            '고객층·동선·시설 적합도는 사용자가 직접 평가한 값입니다. 실제 유동인구·상권·매물 자료를 조회하지 않습니다.',
            '초기 자금 = 보증금 + 첫 달 임대료 + 시설·인테리어 + 장비 + 초기 재료 + 기타. 보증금은 반환 가능한 묶이는 자금입니다.',
            ('민감도: 다음 중요도로 바꾸면 1순위가 달라집니다 → ' + ', '.join(sensitive) + '. 해당 기준의 중요도를 신중히 정하세요.')
            if sensitive else '민감도: 어떤 기준의 중요도를 0 또는 5로 바꿔도 1순위가 유지됩니다. 비교적 안정적인 결과입니다.',
        ]
        if not best['feasible']:
            notes.insert(0, '모든 후보가 하나 이상의 제약을 충족하지 못했습니다. 근접도가 가장 높은 후보를 표시하지만 미충족 조건을 먼저 해결해야 합니다.')
        return dict(
            model='TOPSIS 다기준 의사결정',
            metrics=[('추천 후보', best['name'], ''), ('TOPSIS 근접도', best['score'], '/ 100'),
                     ('해당 후보 초기 필요 자금', best['startup'], '원'), ('민감 기준 수', len(sensitive), '개')],
            columns=['후보', '월 임대료 (원)', '보증금 (원)', '면적 (㎡)', '초기 필요 자금 (원)', '부족 자금 (원)', '제약 충족', 'TOPSIS 근접도 / 100', '검토 사항'],
            rows=rows,
            charts=[
                dict(title='후보별 TOPSIS 근접도 (100 = 이상해)', unit='점', data=[(c['name'], c['score']) for c in candidates]),
                dict(title='추천 후보의 초기 자금 구성', unit='원', data=[
                    ('보증금', v[k+'_deposit']), ('첫 달 임대료', v[k+'_rent']), ('시설·인테리어', v[k+'_interior']),
                    ('장비', v['equipment']), ('초기 재료', v['initial_material']), ('기타', v['other_startup'])]),
            ],
            notes=notes, trace=decision['trace'])
