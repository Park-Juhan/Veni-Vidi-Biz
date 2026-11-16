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


@dataclass(frozen=True)
class OperatingCostSnapshot:
    """Monthly figures another module can offer to operating-cost analysis.

    A provider fills only the figures it actually computes; the rest stay None.
    """
    detail: str
    source: str
    updated_at: str
    monthly_revenue: Decimal | None = None
    monthly_rent: Decimal | None = None
    monthly_material: Decimal | None = None
    monthly_advertising: Decimal | None = None


class OperatingCostProvider(Protocol):
    def export_operating_costs(self, workspace: str) -> OperatingCostSnapshot | None: ...
