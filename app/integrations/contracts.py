"""Public immutable data transfer contract; no imports of module internals."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class MaterialCostSnapshot:
    usage_cost: Decimal
    source: str
    updated_at: str


class MaterialCostProvider(Protocol):
    def export_usage_cost(self, workspace: str) -> MaterialCostSnapshot | None: ...
