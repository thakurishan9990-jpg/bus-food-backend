from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import settings
from app.models.dhaba import Dhaba, MenuItem
from app.models.order import Order, OrderItem, OrderStatus
from app.models.stop import Stop
from app.models.trip import Trip, TripStatus
from app.models.user import User
from app.schemas.order import OrderCreate
from app.services.eta_service import compute_eta, minutes_until
from app.utils.errors import BadRequestError, ConflictError, NotFoundError

# Linear, one-step-at-a-time forward flow. Cancellation is handled separately
# and is only allowed from the two earliest statuses.
FORWARD_TRANSITIONS: dict[OrderStatus, OrderStatus] = {
    OrderStatus.PLACED: OrderStatus.ACCEPTED,
    OrderStatus.ACCEPTED: OrderStatus.PREPARING,
    OrderStatus.PREPARING: OrderStatus.READY,
    OrderStatus.READY: OrderStatus.PICKED_UP,
}
CANCELLABLE_STATUSES = (OrderStatus.PLACED, OrderStatus.ACCEPTED)
NON_ORDERABLE_TRIP_STATUSES = (TripStatus.COMPLETED, TripStatus.CANCELLED)


def validate_cutoff(trip: Trip, stop: Stop, dhaba: Dhaba, now: datetime | None = None) -> datetime:
    """Raise 409 if there isn't enough time left to prepare the order before the bus arrives.

    Rule: (ETA - now) >= dhaba.avg_prep_time_minutes + buffer.
    """
    now = now or datetime.now(timezone.utc)
    eta = compute_eta(trip, stop)
    minutes_to_arrival = minutes_until(eta, now)
    required_minutes = dhaba.avg_prep_time_minutes + settings.order_cutoff_buffer_minutes

    if minutes_to_arrival < required_minutes:
        raise ConflictError(
            f"Too late to order, bus arrives in {max(0, round(minutes_to_arrival))} min "
            f"but prep needs {required_minutes} min"
        )
    return eta


def create_order(db: Session, passenger: User, payload: OrderCreate) -> Order:
    """Validate relationships + cutoff, snapshot menu prices, and persist the order."""
    trip = db.get(Trip, payload.trip_id)
    if trip is None:
        raise NotFoundError(f"Trip {payload.trip_id} not found")
    if trip.status in NON_ORDERABLE_TRIP_STATUSES:
        raise BadRequestError(f"Cannot order on a trip that is already '{trip.status.value}'")

    stop = db.get(Stop, payload.stop_id)
    if stop is None:
        raise NotFoundError(f"Stop {payload.stop_id} not found")
    if stop.route_id != trip.route_id:
        raise BadRequestError("This stop is not on the trip's route")

    dhaba = db.get(Dhaba, payload.dhaba_id)
    if dhaba is None:
        raise NotFoundError(f"Dhaba {payload.dhaba_id} not found")
    if dhaba.stop_id != stop.id:
        raise BadRequestError("This dhaba is not located at this stop")
    if not dhaba.is_active:
        raise BadRequestError("This dhaba is not currently accepting orders")

    eta = validate_cutoff(trip, stop, dhaba)

    order_items: list[OrderItem] = []
    total_amount = Decimal("0")
    for item_in in payload.items:
        menu_item = db.get(MenuItem, item_in.menu_item_id)
        if menu_item is None or menu_item.dhaba_id != dhaba.id:
            raise NotFoundError(f"Menu item {item_in.menu_item_id} not found at this dhaba")
        unit_price = menu_item.price
        total_amount += unit_price * item_in.quantity
        order_items.append(
            OrderItem(menu_item_id=menu_item.id, quantity=item_in.quantity, unit_price=unit_price)
        )

    order = Order(
        passenger_id=passenger.id,
        trip_id=trip.id,
        stop_id=stop.id,
        dhaba_id=dhaba.id,
        seat_number=payload.seat_number,
        status=OrderStatus.PLACED,
        total_amount=total_amount,
        expected_arrival_time=eta,
        items=order_items,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def advance_status(order: Order, requested_status: OrderStatus) -> Order:
    """Move an order one step forward in the linear status machine. No skipping, no reverse."""
    expected_next = FORWARD_TRANSITIONS.get(order.status)
    if expected_next is None or requested_status != expected_next:
        raise BadRequestError(
            f"Cannot move order from '{order.status.value}' to '{requested_status.value}'"
        )
    order.status = requested_status
    return order


def cancel_order(order: Order) -> Order:
    """Cancel an order. Only allowed while it's still 'placed' or 'accepted'."""
    if order.status not in CANCELLABLE_STATUSES:
        raise ConflictError(f"Cannot cancel an order that is already '{order.status.value}'")
    order.status = OrderStatus.CANCELLED
    return order
