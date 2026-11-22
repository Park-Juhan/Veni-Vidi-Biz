from decimal import Decimal
from app.common.model import AnalysisModel
from app.common.validation import Field, ValidationError, validate
from app.integrations.contracts import OperatingCostSnapshot
from .decision_engine.engine import CRITERIA, compare_locations


# Fields of one location candidate (validated per candidate, not part of the main form).
CANDIDATE_FIELDS = (
    Field('name', '후보 지역 / 이름', '', 'text'),
    Field('rent', '월 임대료 (원)', ''),
    Field('deposit', '보증금 (원)', ''),
    Field('area', '면적 (㎡)', '', minimum='0.1'),
    Field('interior', '시설·인테리어 비용 (원)', ''),
    Field('fit', '고객층 적합도 (1~5)', '', minimum='1', maximum='5', step='1'),
    Field('traffic', '이동 동선·유동인구 적합도 (1~5)', '', minimum='1', maximum='5', step='1'),
    Field('facility', '시설 조건 적합도 (1~5)', '', minimum='1', maximum='5', step='1'),
)
# Fictional examples used when the workspace has no saved candidates.
EXAMPLE_CANDIDATES = (
    dict(name='가상 역세권 A', rent='1800000', deposit='20000000', area='40', interior='15000000', fit='4', traffic='3', facility='4'),
    dict(name='가상 주거지 B', rent='1200000', deposit='15000000', area='35', interior='18000000', fit='3', traffic='4', facility='3'),
)
MAX_CANDIDATES = 20


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
    ) + tuple(
        Field('w_'+key, label+' 가중치', default, maximum='100', step='1', group='평가 가중치',
              help=help_text)
        for (key, label, _), default, help_text in zip(CRITERIA, ('30', '20', '10', '15', '15', '10'), (
            '숫자가 클수록 중요합니다. 합계가 100이 아니어도 비율로 환산합니다.', '', '', '낮을수록 유리한 기준입니다.', '낮을수록 유리한 기준입니다.', ''))
    )

    def __init__(self, repository, candidates=None):
        super().__init__(repository)
        # Optional saved-candidate list (needs a database); None means the examples are always used.
        self.candidate_store = candidates

    def defaults(self):
        values = super().defaults()
        values['candidates'] = [dict(c) for c in EXAMPLE_CANDIDATES]
        return values

    # ---- Saved candidates ----
    @staticmethod
    def validate_candidate(raw):
        values = validate(CANDIDATE_FIELDS, raw)
        values['name'] = values['name'].strip()
        return values

    def list_candidates(self, workspace):
        return self.candidate_store.list(workspace) if self.candidate_store else []

    def save_candidate(self, workspace, raw, candidate_id=None):
        if not self.candidate_store: return None
        values = self.validate_candidate(raw)
        if candidate_id is None and len(self.list_candidates(workspace)) >= MAX_CANDIDATES:
            raise ValidationError(f'후보는 최대 {MAX_CANDIDATES}곳까지 저장할 수 있습니다.')
        return self.candidate_store.save(workspace, values, candidate_id)

    def add_example_candidates(self, workspace):
        existing = {c['name'] for c in self.list_candidates(workspace)}
        return [self.save_candidate(workspace, c) for c in EXAMPLE_CANDIDATES if c['name'] not in existing]

    def delete_candidate(self, workspace, candidate_id):
        return bool(self.candidate_store and self.candidate_store.delete(workspace, candidate_id))

    def candidates_for(self, workspace, selected_ids=None):
        """Candidates to compare: the selected saved ones, all saved ones, or the examples when none are saved."""
        saved = self.list_candidates(workspace)
        if not saved:
            return [dict(c) for c in EXAMPLE_CANDIDATES], False
        chosen = [c for c in saved if selected_ids is None or c['id'] in selected_ids]
        return [{key: str(c[key]) for key in ('id', *(f.name for f in CANDIDATE_FIELDS))} for c in chosen], True

    def forget(self, workspace):
        super().forget(workspace)
        if self.candidate_store: self.candidate_store.forget(workspace)

    # ---- Analysis ----
    def prepare(self, values, raw):
        candidates = raw.get('candidates') or []
        if len(candidates) < 2:
            raise ValidationError('비교할 후보를 2곳 이상 선택하세요.')
        if len(candidates) > MAX_CANDIDATES:
            raise ValidationError(f'후보는 한 번에 최대 {MAX_CANDIDATES}곳까지 비교할 수 있습니다.')
        checked, errors = [], []
        for index, candidate in enumerate(candidates, start=1):
            try:
                checked.append(self.validate_candidate(candidate))
            except ValidationError as exc:
                errors.append(f"후보 {index} ({candidate.get('name') or '이름 없음'}): {exc}")
        if errors:
            raise ValidationError(' / '.join(errors))
        if len({c['name'] for c in checked}) != len(checked):
            raise ValidationError('후보 이름이 겹칩니다. 서로 다른 이름을 쓰세요.')
        return values | {'candidates': checked}

    def calculate(self, v):
        decision = compare_locations(v)
        candidates = decision['candidates']
        rows = []
        for c in candidates:
            source = c['input']
            rows.append([c['name'], source['rent'], source['deposit'], source['area'], c['startup'], max(Decimal(0), c['startup']-v['available']), c['score'], ' / '.join(c['notes'])])
        weights = decision['facts']['weights']
        criteria_rows = []
        for key, label, benefit in CRITERIA:
            values = [c['values'][key] for c in candidates]
            best_value = max(values) if benefit else min(values)
            winners = [c['name'] for c in candidates if c['values'][key] == best_value]
            criteria_rows.append([label, weights[key]*100, '높을수록 유리' if benefit else '낮을수록 유리', *values,
                                  '동일' if len(winners) == len(candidates) else ', '.join(winners)])
        best = candidates[0]
        b = best['input']
        notes = ['초기 자금 = 보증금 + 첫 달 임대료 + 시설·인테리어 + 장비 + 초기 재료 + 기타. 보증금은 반환 가능한 묶이는 자금입니다.',
                 'TOPSIS: 기준마다 값을 정규화하고 가중치를 곱한 뒤, 가장 좋은 값(이상해)에 가깝고 가장 나쁜 값에서 먼 정도를 0~100 근접도로 계산합니다.',
                 '순위: 임대료 예산과 필요 면적을 모두 충족한 후보를 먼저 두고, 같은 그룹 안에서 근접도가 높은 순으로 정렬합니다.',
                 '적합도는 사용자 평가입니다. 실제 유동인구·상권·매물 자료를 조회하지 않습니다.']
        if len(candidates) == 2:
            notes.insert(3, '후보가 2곳이면 기준마다 한 후보가 이상해가 되므로 근접도가 0 또는 100 쪽으로 치우칠 수 있습니다. 후보를 3곳 이상 비교하면 더 고르게 나뉩니다.')
        return dict(
            metrics=[('조건 비교 1순위', best['name'], ''), ('해당 후보 초기 필요 자금', best['startup'], '원'), ('월 임대료', b['rent'], '원'), ('비교한 후보', len(candidates), '곳')],
            columns=['후보', '월 임대료 (원)', '보증금 (원)', '면적 (㎡)', '초기 필요 자금 (원)', '부족 자금 (원)', 'TOPSIS 근접도 (0~100)', '검토 사항'], rows=rows,
            extra_tables=[dict(tab='기준별 비교', title='평가 기준별 값과 가중치', lead='각 기준에서 유리한 후보와 반영 비중입니다. 가중치를 바꾸면 순위가 달라질 수 있습니다.',
                               columns=['기준', '가중치 (%)', '방향', *[c['name'] for c in candidates], '유리한 후보'], rows=criteria_rows,
                               note='적합도 1~5점은 사용자가 직접 평가한 값입니다.')],
            chart=[('보증금', b['deposit']), ('첫 달 임대료', b['rent']), ('시설·인테리어', b['interior']), ('장비', v['equipment']), ('초기 재료', v['initial_material']), ('기타', v['other_startup'])],
            chart_title='조건 비교 1순위 후보의 초기 자금 구성', best_name=best['name'], best_rent=b['rent'],
            notes=notes, trace=decision['trace'])

    def export_operating_costs(self, workspace):
        record = self.latest(workspace)
        if record is None or 'best_rent' not in record.result:
            return None
        return OperatingCostSnapshot(detail=f"1순위 후보 {record.result['best_name']}", source=record.source,
                                     updated_at=record.updated_at, monthly_rent=record.result['best_rent'])
