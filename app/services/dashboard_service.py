"""Numbers for the admin Operations and Business screens."""
from collections import Counter
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models.ad_campaign import AdCampaign
from app.models.order import Order, OrderItem, OrderStatus
from app.models.route import Route
from app.models.stop import Stop
from app.models.trip import Trip
from app.schemas.dashboard import (
    Business, ExampleOrderSplit, IncomeToday, KitchenFlag, LiveTrip, Operations, OperationsKpis, RouteOpenOrders,
)
from app.services.bus_service import IST, todays_run
from app.services.catalog_service import is_live, listed_routes
from app.services.eta_service import TERMINAL_ORDER_STATUSES, minutes_until
from app.services.order_service import commission_for

# AdCampaign.spend_inr holds spend over a rolling week (as in the seed), with no
# per-day ledger yet, so "today" is the daily average. Replace with a real daily
# figure once spend is recorded per day.
AD_SPEND_WINDOW_DAYS = 7

# The illustrative order on the Business screen.
EXAMPLE_ORDER_FOOD_INR = 250


def ad_revenue_today_inr(db: Session) -> int:
    total = db.query(func.coalesce(func.sum(AdCampaign.spend_inr), 0)).scalar()
    return round(total / AD_SPEND_WINDOW_DAYS)


def operations(db: Session, now: datetime | None = None) -> Operations:
    now = now or datetime.now(timezone.utc)
    routes = (
        listed_routes(db)
        .options(selectinload(Route.buses), selectinload(Route.stops).selectinload(Stop.dhabas))
        .order_by(Route.id)
        .all()
    )
    open_orders = (
        db.query(Order)
        .join(Order.trip)
        .filter(Order.status.notin_(TERMINAL_ORDER_STATUSES), Trip.route_id.in_([r.id for r in routes]))
        .all()
    )
    open_by_route = Counter(o.trip.route_id for o in open_orders)
    open_by_dhaba = Counter(o.dhaba_id for o in open_orders)

    live_trips, flags = [], []
    for route in routes:
        runs = [todays_run(db, bus, now) for bus in route.buses if bus.is_active]
        dhabas = [d for s in route.stops for d in s.dhabas]
        live_trips.append(LiveTrip(
            route_code=route.code, origin=route.origin, destination=route.destination,
            bus_count=len(runs), highway=route.highway, stop_count=len(route.stops),
            dhaba_count=len(dhabas), delay_minutes=max((r.delay_minutes for r in runs), default=0),
            open_orders=open_by_route[route.id],
        ))
        for stop in route.stops:
            arrivals = [r.expected_at(stop) for r in runs if r.expected_at(stop) >= now]
            if not arrivals:
                continue
            next_arrival = min(arrivals)
            minutes_left = minutes_until(next_arrival, now)
            for dhaba in stop.dhabas:
                queued = open_by_dhaba[dhaba.id]
                queue_minutes = queued * dhaba.avg_prep_time_minutes
                if queued and queue_minutes > minutes_left:
                    flags.append(KitchenFlag(
                        dhaba_slug=dhaba.slug, dhaba_name=dhaba.name, stop_name=stop.name,
                        route_code=route.code, open_orders=queued, prep_minutes=dhaba.avg_prep_time_minutes,
                        queue_minutes=queue_minutes, next_arrival=next_arrival,
                        minutes_until_arrival=round(minutes_left),
                        message=(
                            f"{queued} orders queued against a {dhaba.avg_prep_time_minutes} minute prep time. "
                            f"The next bus arrives in {round(minutes_left)} minutes."
                        ),
                    ))

    all_dhabas = [d for r in routes for s in r.stops for d in s.dhabas]
    return Operations(
        kpis=OperationsKpis(
            active_trips=sum(1 for r in routes if any(b.is_active for b in r.buses)),
            open_orders=len(open_orders),
            dhabas_online=sum(1 for d in all_dhabas if is_live(d)),
            dhabas_total=len(all_dhabas),
            ad_revenue_today_inr=ad_revenue_today_inr(db),
        ),
        orders_by_route=[RouteOpenOrders(route_code=r.code, open_orders=open_by_route[r.id]) for r in routes],
        live_trips=live_trips,
        flags=sorted(flags, key=lambda f: f.minutes_until_arrival - f.queue_minutes),
    )


def example_order() -> ExampleOrderSplit:
    commission = commission_for(EXAMPLE_ORDER_FOOD_INR, settings.default_commission_pct)
    return ExampleOrderSplit(
        food=EXAMPLE_ORDER_FOOD_INR,
        dhaba_keeps=EXAMPLE_ORDER_FOOD_INR - commission,
        commission=commission,
        commission_pct=settings.default_commission_pct,
        fee=settings.convenience_fee_inr,
        dhabago_earns=commission + settings.convenience_fee_inr,
    )


def business(db: Session, now: datetime | None = None) -> Business:
    """Today's (IST) income by stream from non-cancelled orders, plus ads."""
    now = now or datetime.now(timezone.utc)
    start = datetime.combine(now.astimezone(IST).date(), time.min, tzinfo=IST).astimezone(timezone.utc)
    todays = db.query(Order).filter(
        Order.created_at >= start, Order.created_at < start + timedelta(days=1),
        Order.status != OrderStatus.CANCELLED,
    )
    commission, fees, count = todays.with_entities(
        func.coalesce(func.sum(Order.commission_inr), 0),
        func.coalesce(func.sum(Order.convenience_fee_inr), 0),
        func.count(Order.id),
    ).one()
    addon_sales = (
        db.query(func.coalesce(func.sum(OrderItem.unit_price_inr * OrderItem.quantity), 0))
        .filter(OrderItem.addon_campaign_id.isnot(None), OrderItem.order_id.in_(todays.with_entities(Order.id)))
        .scalar()
    )
    ads = ad_revenue_today_inr(db)
    return Business(
        income_today=IncomeToday(
            commission_inr=commission, convenience_fees_inr=fees, ads_inr=ads, addon_sales_inr=addon_sales,
            total=commission + fees + ads + addon_sales, orders=count,
        ),
        example_order=example_order(),
    )
