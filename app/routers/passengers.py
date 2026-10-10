from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.dhaba import Dhaba, MenuItem
from app.models.order import Order
from app.models.route import Route
from app.models.stop import Stop
from app.models.trip import Trip, TripStatus
from app.models.user import User, UserRole
from app.schemas.dhaba import DhabaWithReviews, MenuItemRead
from app.schemas.order import OrderCreate, OrderRead
from app.schemas.route import RouteRead
from app.schemas.stop import StopRead, UpcomingStop
from app.schemas.trip import TripRead
from app.schemas.user import UserRead
from app.services import order_service, places_service
from app.services.eta_service import compute_eta, minutes_until
from app.utils.errors import ForbiddenError, NotFoundError
from app.utils.security import get_current_user, require_role

router = APIRouter(tags=["passengers"])


@router.get("/me", response_model=UserRead)
def get_me(current_user: User = Depends(get_current_user)) -> User:
    """Return the current authenticated user, so a client can restore a session from a stored token."""
    return current_user


@router.get("/routes", response_model=list[RouteRead])
def list_routes(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> list[Route]:
    """List all bus routes."""
    return db.query(Route).all()


@router.get("/routes/{route_id}/trips", response_model=list[TripRead])
def list_trips_for_route(
    route_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> list[Trip]:
    """List all trips scheduled on a route."""
    if db.get(Route, route_id) is None:
        raise NotFoundError(f"Route {route_id} not found")
    return db.query(Trip).filter(Trip.route_id == route_id).all()


@router.get("/routes/{route_id}/stops", response_model=list[StopRead])
def list_stops_for_route(
    route_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> list[Stop]:
    """List every stop on a route, in sequence order (for drawing a full route map)."""
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


@router.get("/stops/{stop_id}/dhabas", response_model=list[DhabaWithReviews])
def list_dhabas_at_stop(
    stop_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> list[DhabaWithReviews]:
    """Dhabas at a stop, enriched with Google rating + AI-summarized reviews."""
    if db.get(Stop, stop_id) is None:
        raise NotFoundError(f"Stop {stop_id} not found")

    dhabas = db.query(Dhaba).filter(Dhaba.stop_id == stop_id, Dhaba.is_active.is_(True)).all()

    results = []
    for dhaba in dhabas:
        cache = places_service.get_or_refresh_reviews(db, dhaba)
        results.append(
            DhabaWithReviews(
                id=dhaba.id,
                stop_id=dhaba.stop_id,
                name=dhaba.name,
                google_place_id=dhaba.google_place_id,
                avg_prep_time_minutes=dhaba.avg_prep_time_minutes,
                is_active=dhaba.is_active,
                rating=cache.rating if cache else None,
                total_reviews=cache.total_reviews if cache else None,
                ai_summary=cache.ai_summary if cache else None,
            )
        )
    return results


@router.get("/dhabas/{dhaba_id}/menu", response_model=list[MenuItemRead])
def get_dhaba_menu(
    dhaba_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> list[MenuItem]:
    """List menu items for a dhaba."""
    if db.get(Dhaba, dhaba_id) is None:
        raise NotFoundError(f"Dhaba {dhaba_id} not found")
    return db.query(MenuItem).filter(MenuItem.dhaba_id == dhaba_id).all()


@router.post("/orders", response_model=OrderRead, status_code=201)
def place_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.PASSENGER)),
) -> Order:
    """Place an order. Validates the order cutoff (prep time + arrival buffer)."""
    return order_service.create_order(db, current_user, payload)


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
    """Cancel an order. Only the owning passenger (or admin) may cancel, and only while placed/accepted."""
    order = db.get(Order, order_id)
    if order is None:
        raise NotFoundError(f"Order {order_id} not found")
    if current_user.role != UserRole.ADMIN and order.passenger_id != current_user.id:
        raise ForbiddenError("You may only cancel your own orders")

    order_service.cancel_order(order)
    db.commit()
    db.refresh(order)
    return order
