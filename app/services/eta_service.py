from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.order import Order, OrderStatus
from app.models.stop import Stop
from app.models.trip import Trip

TERMINAL_ORDER_STATUSES = (OrderStatus.PICKED_UP, OrderStatus.CANCELLED)


def _as_aware_utc(dt: datetime) -> datetime:
    """Treat a naive datetime as UTC.

    SQLite (used in tests) silently drops tzinfo on DateTime(timezone=True)
    round-trips even though Postgres preserves it; every datetime this app
    writes is already UTC, so a missing tzinfo just means "assume UTC".
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def compute_eta(trip: Trip, stop: Stop) -> datetime:
    """ETA(stop, trip) = trip.departure_time + stop.minutes_from_origin + trip.current_delay_minutes."""
    departure_time = _as_aware_utc(trip.departure_time)
    return departure_time + timedelta(minutes=stop.minutes_from_origin + trip.current_delay_minutes)


def minutes_until(target: datetime, now: datetime | None = None) -> float:
    """Minutes remaining until `target`, as a float (can be negative if already past)."""
    now = _as_aware_utc(now) if now is not None else datetime.now(timezone.utc)
    return (_as_aware_utc(target) - now).total_seconds() / 60


def recalculate_order_etas(db: Session, trip: Trip) -> list[Order]:
    """Recompute expected_arrival_time for every non-terminal order on this trip.

    Called whenever a trip's delay changes, since every active order's ETA
    depends on trip.current_delay_minutes.
    """
    orders = (
        db.query(Order)
        .filter(Order.trip_id == trip.id, Order.status.notin_(TERMINAL_ORDER_STATUSES))
        .all()
    )
    for order in orders:
        order.expected_arrival_time = compute_eta(trip, order.stop)
    db.commit()
    return orders
