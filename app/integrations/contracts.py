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


@dataclass(frozen=True)
class MaterialCostItem:
    """One saved material priced per base unit (g, mL or 개), yield already applied."""
    material_id: int
    name: str
    base_unit: str
    cost_per_base_unit: Decimal
    updated_at: str


class MaterialCatalogProvider(Protocol):
    def list_material_costs(self, workspace: str) -> list[MaterialCostItem]: ...


@dataclass(frozen=True)
class AreaOption:
    """One commercial area a location candidate can be linked to."""
    code: str
    label: str


@dataclass(frozen=True)
class AreaSnapshot:
    """Published statistics of one commercial area for one industry and quarter (None = not published)."""
    code: str
    name: str
    kind: str
    district: str
    dong: str
    industry: str
    period: str
    sales: int | None = None
    sales_count: int | None = None
    stores: int | None = None
    franchise: int | None = None
    open_rate: int | None = None
    close_rate: int | None = None
    footfall: int | None = None
    workers: int | None = None
    residents: int | None = None
    facilities: int | None = None
    subway: int | None = None
    bus_stops: int | None = None
    change: str | None = None
    top_age: str | None = None
    top_time: str | None = None
    source: str = ''


class AreaDataProvider(Protocol):
    def available(self) -> bool: ...
    def area_options(self) -> list[AreaOption]: ...
    def industries(self) -> list[str]: ...
    def snapshot(self, code: str, industry: str) -> AreaSnapshot | None: ...
