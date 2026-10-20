from datetime import datetime

from pydantic import BaseModel

from app.schemas.catalog import IstTimesModel


class OperationsKpis(BaseModel):
    active_trips: int
    open_orders: int
    dhabas_online: int
    dhabas_total: int
    ad_revenue_today_inr: int


class RouteOpenOrders(BaseModel):
    route_code: str
    open_orders: int


class LiveTrip(BaseModel):
    route_code: str
    origin: str
    destination: str
    bus_count: int
    highway: str | None
    stop_count: int
    dhaba_count: int
    # The worst delay among the route's buses today.
    delay_minutes: int
    open_orders: int


class KitchenFlag(IstTimesModel):
    """A kitchen whose queue (open orders x prep time) won't clear before the next bus arrives."""

    dhaba_slug: str | None
    dhaba_name: str
    stop_name: str
    route_code: str
    open_orders: int
    prep_minutes: int
    queue_minutes: int
    next_arrival: datetime
    minutes_until_arrival: int
    message: str


class Operations(BaseModel):
    kpis: OperationsKpis
    orders_by_route: list[RouteOpenOrders]
    live_trips: list[LiveTrip]
    flags: list[KitchenFlag]


class IncomeToday(BaseModel):
    commission_inr: int
    convenience_fees_inr: int
    ads_inr: int
    addon_sales_inr: int
    total: int
    orders: int


class ExampleOrderSplit(BaseModel):
    food: int
    dhaba_keeps: int
    commission: int
    commission_pct: int
    fee: int
    dhabago_earns: int


class Business(BaseModel):
    income_today: IncomeToday
    example_order: ExampleOrderSplit
