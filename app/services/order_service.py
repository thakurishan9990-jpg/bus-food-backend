from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models.ad_campaign import AdCampaign, AdPlacement, AdStatus
from app.models.dhaba import Dhaba, DhabaStatus, MenuItem
from app.models.order import Order, OrderItem, OrderStatus
from app.models.stop import Stop
from app.models.trip import Trip, TripStatus
from app.models.user import User
from app.schemas.order import OrderCreate
from app.services.bus_service import find_bus, get_or_create_todays_trip
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


def commission_for(subtotal_inr: int, commission_pct: int) -> int:
    """round(subtotal x pct / 100), rounding halves up (Python's round() would round ₹0.50 to even)."""
    return (subtotal_inr * commission_pct + 50) // 100


def validate_cutoff(trip: Trip, stop: Stop, dhaba: Dhaba, now: datetime | None = None) -> datetime:
    """Raise 409 once the stop's order cut-off has passed. Returns the ETA at the stop.

    The cut-off is min(ETA - prep - buffer) over the stop's live dhabas (the
    ordering dhaba included), i.e. it's set by the slowest kitchen there, so a
    stop closes for ordering all at once, as the passenger app shows it.
    """
    now = now or datetime.now(timezone.utc)
    eta = compute_eta(trip, stop)
    minutes_to_arrival = minutes_until(eta, now)
    slowest_prep = max(
        [d.avg_prep_time_minutes for d in stop.dhabas if d.status == DhabaStatus.ACTIVE]
        + [dhaba.avg_prep_time_minutes]
    )
    required_minutes = slowest_prep + settings.order_cutoff_buffer_minutes

    if minutes_to_arrival < required_minutes:
        raise ConflictError(
            f"Too late to order, bus arrives in {max(0, round(minutes_to_arrival))} min "
            f"but prep needs {required_minutes} min"
        )
    return eta


def _resolve_trip(db: Session, payload: OrderCreate) -> Trip:
    if payload.bus_number is not None:
        return get_or_create_todays_trip(db, find_bus(db, payload.bus_number))
    trip = db.get(Trip, payload.trip_id)
    if trip is None:
        raise NotFoundError(f"Trip {payload.trip_id} not found")
    return trip


def create_order(db: Session, passenger: User, payload: OrderCreate) -> Order:
    """Validate the bus, stop, dhaba, cut-off and lines; price everything server-side; persist."""
    trip = _resolve_trip(db, payload)
    if trip.status in NON_ORDERABLE_TRIP_STATUSES:
        raise BadRequestError(f"Cannot order on a trip that is already '{trip.status.value}'")

    stop = db.get(Stop, payload.stop_id)
    if stop is None:
        raise NotFoundError(f"Stop {payload.stop_id} not found")
    if stop.route_id != trip.route_id:
        raise BadRequestError("This stop is not on the trip's route")

    food_lines = [line for line in payload.items if line.menu_item_id is not None]
    addon_lines = [line for line in payload.items if line.addon_campaign_id is not None]
    if not food_lines:
        raise BadRequestError("An order needs at least one item from the dhaba's menu")

    menu_items: list[MenuItem] = []
    for line in food_lines:
        menu_item = db.get(MenuItem, line.menu_item_id)
        if menu_item is None:
            raise NotFoundError(f"Menu item {line.menu_item_id} not found")
        menu_items.append(menu_item)
    dhaba_ids = {m.dhaba_id for m in menu_items} | ({payload.dhaba_id} if payload.dhaba_id else set())
    if len(dhaba_ids) > 1:
        raise BadRequestError("An order can only contain items from one dhaba")

    dhaba = db.get(Dhaba, dhaba_ids.pop())
    if dhaba.stop_id != stop.id:
        raise BadRequestError("This dhaba is not located at this stop")
    if dhaba.status != DhabaStatus.ACTIVE:
        raise BadRequestError("This dhaba is not currently accepting orders")
    unavailable = [m.name for m in menu_items if not m.is_available]
    if unavailable:
        raise BadRequestError(f"Not available right now: {', '.join(unavailable)}")

    eta = validate_cutoff(trip, stop, dhaba)

    order_items: list[OrderItem] = []
    food_subtotal_inr = 0
    for line, menu_item in zip(food_lines, menu_items):
        food_subtotal_inr += menu_item.price_inr * line.quantity
        order_items.append(
            OrderItem(menu_item_id=menu_item.id, quantity=line.quantity, unit_price_inr=menu_item.price_inr)
        )

    addon_subtotal_inr = 0
    for line in addon_lines:
        campaign = db.get(AdCampaign, line.addon_campaign_id)
        if (
            campaign is None
            or campaign.placement != AdPlacement.MENU_ADDON
            or campaign.status != AdStatus.LIVE
            or campaign.addon_price_inr is None
            or campaign.route_id not in (None, trip.route_id)
        ):
            raise BadRequestError(f"Add-on {line.addon_campaign_id} is not available on this trip")
        addon_subtotal_inr += campaign.addon_price_inr * line.quantity
        order_items.append(
            OrderItem(addon_campaign_id=campaign.id, quantity=line.quantity, unit_price_inr=campaign.addon_price_inr)
        )

    subtotal_inr = food_subtotal_inr + addon_subtotal_inr
    convenience_fee_inr = settings.convenience_fee_inr
    order = Order(
        passenger_id=passenger.id,
        trip_id=trip.id,
        stop_id=stop.id,
        dhaba_id=dhaba.id,
        seat_number=payload.seat_number,
        status=OrderStatus.PLACED,
        subtotal_inr=subtotal_inr,
        convenience_fee_inr=convenience_fee_inr,
        # The dhaba's commission is on its own food only; add-ons are DhabaGo's own sales.
        commission_inr=commission_for(food_subtotal_inr, dhaba.commission_pct),
        total_inr=subtotal_inr + convenience_fee_inr,
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
