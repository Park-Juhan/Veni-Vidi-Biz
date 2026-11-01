from datetime import datetime, timezone
from decimal import DecimalException
from app.common.repository import AnalysisRecord, AnalysisRepository
from app.common.validation import ValidationError, validate


class AnalysisModel:
    fields = ()

    def __init__(self, repository: AnalysisRepository):
        self.repository = repository

    def defaults(self):
        return {field.name: field.default for field in self.fields}

    def latest(self, workspace):
        return self.repository.latest(workspace)

    def analyze(self, raw, workspace, source="사용자 입력 · 검증되지 않은 가정"):
        values = validate(self.fields, raw)
        try:
            result = self.calculate(values)
        except DecimalException as exc:
            raise ValidationError('입력한 수치의 크기나 정밀도로 계산할 수 없습니다. 값을 확인해 주세요.') from exc
        record = AnalysisRecord(dict(raw), result, source, datetime.now(timezone.utc).isoformat(timespec="seconds"))
        self.repository.save(workspace, record)
        return record
