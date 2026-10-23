from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models.dhaba import Dhaba
from app.models.order import Order, OrderStatus
from app.models.route import Route
from app.models.stop import Stop
from app.models.trip import Trip, TripStatus
from app.models.user import User, UserRole
from app.config import settings
from app.schemas.catalog import AppConfig, DhabaListing, DhabaMenu, MenuCounts, MenuItemListing, RouteSummary
from app.schemas.order import OrderCreate, OrderPlaced, OrderRead, PaymentCheckout, PaymentVerify
from app.schemas.stop import StopRead, UpcomingStop
from app.schemas.trip import TripRead
from app.schemas.user import UserRead
from app.services import order_service, payment_service, places_service
from app.services.catalog_service import (
    CUISINE_LABELS, Diet, dhabas_with_menus, is_live, listed_routes, shown_for_diet, sponsored_first, visible_items,
)
from app.services.eta_service import compute_eta, minutes_until
from app.services.listing_service import ad_item, addon_for, dhaba_listing, route_summary
from app.utils.errors import BadRequestError, ForbiddenError, NotFoundError
from app.utils.security import get_current_user, require_role

router = APIRouter(tags=["passenger"])

DietQuery = Query("all", description="all, veg or nonveg")


@router.get("/me", response_model=UserRead)
def get_me(current_user: User = Depends(get_current_user)) -> User:
    """Return the current authenticated user, so a client can restore a session from a stored token."""
    return current_user


@router.get("/config", response_model=AppConfig)
def get_config() -> AppConfig:
    """Values the passenger app shows before the server prices an order. Public."""
    return AppConfig(
        convenience_fee_inr=settings.convenience_fee_inr,
        order_cutoff_buffer_minutes=settings.order_cutoff_buffer_minutes,
        ready_before_arrival_minutes=settings.ready_before_arrival_minutes,
        cuisines=CUISINE_LABELS,
    )


@router.get("/routes", response_model=list[RouteSummary])
def list_routes(db: Session = Depends(get_db)) -> list[RouteSummary]:
    """Bus routes passengers can browse, with active bus, stop and live dhaba counts. Public."""
    routes = (
        listed_routes(db)
        .options(selectinload(Route.buses), selectinload(Route.stops).selectinload(Stop.dhabas))
        .order_by(Route.id)
        .all()
    )
    return [route_summary(route) for route in routes]


@router.get("/routes/{route_id}/trips", response_model=list[TripRead])
def list_trips_for_route(
    route_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> list[Trip]:
    """List all trips scheduled on a route."""
    if db.get(Route, route_id) is None:
        raise NotFoundError(f"Route {route_id} not found")
    return db.query(Trip).filter(Trip.route_id == route_id).all()


@router.get("/routes/{route_id}/stops", response_model=list[StopRead])
def list_stops_for_route(route_id: int, db: Session = Depends(get_db)) -> list[Stop]:
    """List every stop on a route, in sequence order (for drawing a full route map). Public."""
    if db.get(Route, route_id) is None:
        raise NotFoundError(f"Route {route_id} not found")
    return db.query(Stop).filter(Stop.route_id == route_id).order_by(Stop.sequence_order).all()


@router.get("/trips/{trip_id}/upcoming-stops", response_model=list[UpcomingStop])
def upcoming_stops(
    trip_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> list[UpcomingStop]:
    """Stops still ahead of the bus (after last_passed_stop), each with a computed ETA."""
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError(f"Trip {trip_id} not found")

    if trip.status == TripStatus.COMPLETED:
        return []

    stops = (
        db.query(Stop)
        .filter(Stop.route_id == trip.route_id)
        .order_by(Stop.sequence_order)
        .all()
    )

    last_passed_sequence = -1
    if trip.last_passed_stop_id is not None:
        last_passed_stop = db.get(Stop, trip.last_passed_stop_id)
        if last_passed_stop is not None:
            last_passed_sequence = last_passed_stop.sequence_order

    now = datetime.now(timezone.utc)
    upcoming = []
    for stop in stops:
        if stop.sequence_order <= last_passed_sequence:
            continue
        eta = compute_eta(trip, stop)
        # Drop stops already behind us, unless the bus is still within its halt
        # window there (eta + halt_duration_minutes >= now) -- then keep it and
        # let minutes_until_arrival go slightly negative.
        if eta + timedelta(minutes=stop.halt_duration_minutes) < now:
            continue
        stop_data = StopRead.model_validate(stop).model_dump()
        upcoming.append(
            UpcomingStop(**stop_data, eta=eta, minutes_until_arrival=round(minutes_until(eta, now)))
        )
    return upcoming


@router.get("/stops/{stop_id}/dhabas", response_model=list[DhabaListing])
def list_dhabas_at_stop(stop_id: int, diet: Diet = DietQuery, db: Session = Depends(get_db)) -> list[DhabaListing]:
    """Active dhabas at a stop that serve the chosen diet, sponsored first, then by rating. Public.

    Dhabas with a Google place id show their cached Google rating and AI review summary.
    """
    if db.get(Stop, stop_id) is None:
        raise NotFoundError(f"Stop {stop_id} not found")

    dhabas = dhabas_with_menus(db).filter(Dhaba.stop_id == stop_id).all()
    shown = sponsored_first([d for d in dhabas if is_live(d) and shown_for_diet(d, diet)])
    return [
        dhaba_listing(d, diet, places_service.get_or_refresh_reviews(db, d) if d.google_place_id else None)
        for d in shown
    ]


def _get_live_dhaba(db: Session, dhaba_ref: str) -> Dhaba:
    """A live dhaba by slug, or by numeric id for older clients."""
    query = dhabas_with_menus(db)
    dhaba = (
        query.filter(Dhaba.id == int(dhaba_ref)) if dhaba_ref.isdigit() else query.filter(Dhaba.slug == dhaba_ref)
    ).first()
    if dhaba is None or not is_live(dhaba):
        raise NotFoundError(f"Dhaba {dhaba_ref} not found")
    return dhaba


@router.get("/dhabas/{dhaba_ref}/menu", response_model=DhabaMenu)
def get_dhaba_menu(dhaba_ref: str, diet: Diet = DietQuery, db: Session = Depends(get_db)) -> DhabaMenu:
    """A dhaba's available items for the diet, chip counts, and one menu add-on. Public.

    `dhaba_ref` is the dhaba's slug (or its numeric id). When the diet leaves nothing,
    `empty_reason` says why: `pure_veg` (non-veg asked of a pure-veg dhaba) or `no_veg`.
    """
    dhaba = _get_live_dhaba(db, dhaba_ref)
    items = visible_items(dhaba, diet)
    empty_reason = None
    if not items and diet == "nonveg" and dhaba.is_pure_veg:
        empty_reason = "pure_veg"
    elif not items and diet == "veg":
        empty_reason = "no_veg"
    addon = addon_for(db, dhaba)
    return DhabaMenu(
        dhaba=dhaba_listing(dhaba, diet),
        diet=diet,
        items=[MenuItemListing.model_validate(m) for m in items],
        counts=MenuCounts(**{d: len(visible_items(dhaba, d)) for d in ("all", "veg", "nonveg")}),
        empty_reason=empty_reason,
        addon=ad_item(addon) if addon else None,
    )


@router.post("/orders", response_model=OrderPlaced, status_code=201)
def place_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.PASSENGER)),
) -> OrderPlaced:
    """Place an order (passengers only). Seat number required; one dhaba per order.

    Give the bus by `bus_number` (or a `trip_id`). Totals are computed here from
    menu and add-on prices; any prices the client sends are ignored. Refused with
    409 once the stop's order cut-off has passed.

    With payments configured the order is held as 'awaiting_payment' and the
    response carries what the browser needs to open Razorpay Checkout.
    """
    order = order_service.create_order(db, current_user, payload)
    body = OrderPlaced.model_validate(order)
    if order.razorpay_order_id:
        body.payment = _checkout_for(order)
    return body


def _checkout_for(order: Order) -> PaymentCheckout:
    return PaymentCheckout(
        key_id=settings.razorpay_key_id,
        razorpay_order_id=order.razorpay_order_id,
        amount_paise=payment_service.to_paise(order.total_inr),
    )


@router.get("/orders/{order_id}/payment", response_model=PaymentCheckout)
def get_payment_handle(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaymentCheckout:
    """Re-open checkout for an order still awaiting payment.

    Needed because a passenger can close the Razorpay window; without this the
    order would be stranded with no way to pay for it.
    """
    order = db.get(Order, order_id)
    if order is None:
        raise NotFoundError(f"Order {order_id} not found")
    if current_user.role != UserRole.ADMIN and order.passenger_id != current_user.id:
        raise ForbiddenError("You may only pay for your own orders")
    if order.status != OrderStatus.AWAITING_PAYMENT or not order.razorpay_order_id:
        raise BadRequestError("This order is not awaiting payment")
    return _checkout_for(order)


@router.post("/orders/{order_id}/payment/verify", response_model=OrderRead)
def verify_payment(
    order_id: int,
    payload: PaymentVerify,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Order:
    """Confirm a Razorpay payment and release the order to the kitchen.

    The signature is checked server-side: a browser claiming success proves
    nothing on its own.
    """
    order = db.get(Order, order_id)
    if order is None:
        raise NotFoundError(f"Order {order_id} not found")
    if current_user.role != UserRole.ADMIN and order.passenger_id != current_user.id:
        raise ForbiddenError("You may only pay for your own orders")
    return order_service.confirm_payment(
        db, order, payload.razorpay_payment_id, payload.razorpay_signature
    )


@router.get("/passengers/{passenger_id}/orders", response_model=list[OrderRead])
def get_passenger_orders(
    passenger_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[Order]:
    """List a passenger's own orders. Passengers may only view their own; admins may view any."""
    if current_user.role != UserRole.ADMIN and current_user.id != passenger_id:
        raise ForbiddenError("You may only view your own orders")
    return db.query(Order).filter(Order.passenger_id == passenger_id).all()


@router.patch("/orders/{order_id}/cancel", response_model=OrderRead)
def cancel_order(
    order_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> Order:
    """Cancel an order. Only the owning passenger (or admin) may cancel, and only while unpaid, placed or accepted."""
    order = db.get(Order, order_id)
    if order is None:
        raise NotFoundError(f"Order {order_id} not found")
    if current_user.role != UserRole.ADMIN and order.passenger_id != current_user.id:
        raise ForbiddenError("You may only cancel your own orders")

    order_service.cancel_order(order)
    db.commit()
    db.refresh(order)
    return order
