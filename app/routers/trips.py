from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.stop import Stop
from app.models.trip import Trip
from app.models.user import User, UserRole
from app.schemas.trip import TripDelayUpdate, TripLastPassedStopUpdate, TripRead
from app.services.eta_service import recalculate_order_etas
from app.utils.errors import BadRequestError, NotFoundError
from app.utils.security import require_role

router = APIRouter(prefix="/trips", tags=["trips"])


@router.patch("/{trip_id}/delay", response_model=TripRead)
def update_delay(
    trip_id: int,
    payload: TripDelayUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> Trip:
    """Update a trip's delay. Recalculates expected_arrival_time for all active orders."""
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError(f"Trip {trip_id} not found")

    trip.current_delay_minutes = payload.current_delay_minutes
    db.commit()
    recalculate_order_etas(db, trip)
    db.refresh(trip)
    return trip


@router.patch("/{trip_id}/last-passed-stop", response_model=TripRead)
def update_last_passed_stop(
    trip_id: int,
    payload: TripLastPassedStopUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> Trip:
    """Mark a stop as passed by the bus."""
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError(f"Trip {trip_id} not found")

    stop = db.get(Stop, payload.last_passed_stop_id)
    if stop is None:
        raise NotFoundError(f"Stop {payload.last_passed_stop_id} not found")
    if stop.route_id != trip.route_id:
        raise BadRequestError("This stop is not on the trip's route")

    trip.last_passed_stop_id = stop.id
    db.commit()
    db.refresh(trip)
    return trip
