"""Framework-independent input contracts and validation."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    default: str
    kind: str = "number"
    minimum: str = "0"
    maximum: str = "1000000000000"
    step: str = "any"
    choices: tuple[str, ...] = ()
    help: str = ""
    group: str = "기본 조건"


def validate(fields: tuple[Field, ...], raw: Mapping) -> dict:
    values = {}
    errors = []
    for field in fields:
        text = str(raw.get(field.name, "")).strip()
        if field.kind in ("text", "select"):
            if not text or len(text) > 120:
                errors.append(f"{field.label}: 1~120자로 입력해 주세요.")
            elif field.choices and text not in field.choices:
                errors.append(f"{field.label}: 제공된 선택지를 선택해 주세요.")
            values[field.name] = text
            continue
        try:
            if len(text) > 64:
                raise InvalidOperation
            value = Decimal(text)
            if not value.is_finite() or not Decimal(field.minimum) <= value <= Decimal(field.maximum):
                raise InvalidOperation
            # Bound tiny scientific notation before arithmetic and HTML formatting.
            if value and value.adjusted() < -28:
                raise InvalidOperation
            if field.step == "1" and value != value.to_integral_value():
                raise InvalidOperation
            values[field.name] = value
        except (InvalidOperation, ValueError):
            errors.append(f"{field.label}: {field.minimum}~{field.maximum} 범위의 숫자를 입력해 주세요. 숫자는 64자 이하, 0이 아닌 값은 1e-28 이상이어야 합니다.")
    if errors:
        raise ValidationError(" / ".join(errors))
    return values
