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
    def districts(self) -> list[str]: ...
    def snapshots(self, industry: str, districts: list[str] | None = None) -> list[AreaSnapshot]: ...


@dataclass(frozen=True)
class MarketItemOption:
    """One market price series a material can be compared with (key = 품목|품종|단위|등급)."""
    key: str
    label: str


@dataclass(frozen=True)
class MarketQuote:
    """Latest monthly retail price of one item; per-base prices are None when the unit is not g/mL/개 based."""
    key: str
    label: str
    unit: str
    month: str
    price: int
    seoul_price: int | None
    base_unit: str | None
    price_per_base: Decimal | None
    seoul_per_base: Decimal | None
    year_ago_price: int | None
    source: str


class MarketPriceProvider(Protocol):
    def available(self) -> bool: ...
    def options(self) -> list[MarketItemOption]: ...
    def suggest(self, name: str, base_unit: str) -> str | None: ...
    def quote(self, key: str) -> MarketQuote | None: ...


@dataclass(frozen=True)
class IndustryBenchmark:
    """Average small business of one industry and region: monthly revenue and cost shares of revenue (%)."""
    industry: str
    region: str
    year: str
    firms: int | None
    monthly_revenue: Decimal | None
    cost_of_sales_ratio: Decimal | None
    payroll_ratio: Decimal | None
    rent_ratio: Decimal | None
    other_ratio: Decimal | None
    profit_ratio: Decimal | None
    split_region: str          # region whose cost breakdown was used (may fall back to 전국)
    source: str


class BenchmarkProvider(Protocol):
    def available(self) -> bool: ...
    def industries(self) -> list[str]: ...
    def regions(self) -> list[str]: ...
    def benchmark(self, industry: str, region: str) -> IndustryBenchmark | None: ...


@dataclass(frozen=True)
class DineOutQuote:
    """Average price of one representative restaurant menu in one region (원)."""
    menu: str
    region: str
    month: str
    price: int
    year_ago_price: int | None
    source: str


class DineOutProvider(Protocol):
    def available(self) -> bool: ...
    def menus(self) -> list[str]: ...
    def regions(self) -> list[str]: ...
    def quote(self, menu: str, region: str) -> DineOutQuote | None: ...


@dataclass(frozen=True)
class StartupBenchmark:
    """Start-up cost brackets (% of businesses) and average lease terms (원) of one industry and region."""
    industry: str
    region: str
    year: str
    cost_brackets: tuple[Decimal | None, Decimal | None, Decimal | None]   # 5천만원 미만, 5천만~1억, 1억 이상
    own_brackets: tuple[Decimal | None, Decimal | None, Decimal | None]
    deposit: Decimal | None
    monthly_rent: Decimal | None
    source: str


class StartupBenchmarkProvider(Protocol):
    def available(self) -> bool: ...
    def industries(self) -> list[str]: ...
    def regions(self) -> list[str]: ...
    def benchmark(self, industry: str, region: str) -> StartupBenchmark | None: ...


@dataclass(frozen=True)
class CommodityTrend:
    """Latest weekly international futures price of a raw material and its change (%)."""
    commodity: str
    week_start: str
    cents_per_lb: Decimal
    usd_per_kg: Decimal | None
    change_4w: Decimal | None
    change_52w: Decimal | None
    source: str


class CommodityTrendProvider(Protocol):
    def available(self) -> bool: ...
    def trend_for(self, material_name: str) -> CommodityTrend | None: ...


@dataclass(frozen=True)
class RentEstimate:
    """Estimated monthly rent per ㎡ (원) of small shops for one commercial area, and what it was based on."""
    per_m2: Decimal
    basis: str                       # e.g. '망원역 상권', '마포구 조사 상권 평균'
    quarter: str
    source: str


class RentProvider(Protocol):
    def available(self) -> bool: ...
    def estimate(self, name: str, district: str, dong: str) -> RentEstimate | None: ...


@dataclass(frozen=True)
class DishIngredient:
    name: str
    quantity: Decimal                # per serving, in unit
    unit: str                        # g, mL, 개
    cost: Decimal                    # per serving (원)


@dataclass(frozen=True)
class DishCost:
    """A dish analysed in the material cost module: ingredient cost per serving at current prices."""
    dish_id: int
    name: str
    cost_per_serving: Decimal
    monthly_volume: Decimal
    ingredients: tuple[DishIngredient, ...]
    updated_at: str


class DishCostProvider(Protocol):
    def list_dishes(self, workspace: str) -> list[DishCost]: ...


@dataclass(frozen=True)
class LocationSnapshot:
    """The location chosen in the property module (01): rent and the area's average sales per store."""
    area_name: str
    monthly_rent: Decimal
    sales_per_store: Decimal | None   # 상권 평균 점포당 월 추정매출
    industry: str
    updated_at: str


class LocationProvider(Protocol):
    def export_location(self, workspace: str) -> LocationSnapshot | None: ...
