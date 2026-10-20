from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models.bus import Bus
from app.models.dhaba import Dhaba
from app.models.route import Route
from app.models.stop import Stop
from app.schemas.catalog import BusLookup, BusStops, BusSummary, StopTiming
from app.services.bus_service import find_bus, todays_run
from app.services.catalog_service import (
    Diet, cuisine_label, face_item, is_live, listed_routes, shown_for_diet, sponsored_first, stop_cutoff,
)
from app.services.listing_service import bus_summary, route_summary
from app.utils.errors import NotFoundError

router = APIRouter(tags=["passenger"])


@router.get("/routes/{code}/buses", response_model=list[BusSummary])
def list_buses_for_route(code: str, db: Session = Depends(get_db)) -> list[BusSummary]:
    """Active buses on a route (by route code, e.g. DL-234), earliest departure first, with today's delay. Public."""
    route = listed_routes(db).filter(Route.code == code).first()
    if route is None:
        raise NotFoundError(f"Route {code} not found")
    buses = (
        db.query(Bus)
        .filter(Bus.route_id == route.id, Bus.is_active.is_(True))
        .order_by(Bus.departs, Bus.id)
        .all()
    )
    return [bus_summary(todays_run(db, bus)) for bus in buses]


def _route_with_stops(db: Session, route_id: int) -> Route:
    return (
        db.query(Route)
        .options(
            selectinload(Route.buses),
            selectinload(Route.stops).selectinload(Stop.dhabas).selectinload(Dhaba.menu_items),
        )
        .filter(Route.id == route_id)
        .one()
    )


@router.get("/buses/{bus_number}", response_model=BusLookup)
def get_bus(bus_number: str, db: Session = Depends(get_db)) -> BusLookup:
    """Find a bus by its number, ignoring case and spaces; a unique partial number (e.g. "PA 1187") also works. Public."""
    bus = find_bus(db, bus_number)
    return BusLookup(bus=bus_summary(todays_run(db, bus)), route=route_summary(_route_with_stops(db, bus.route_id)))


@router.get("/buses/{bus_number}/stops", response_model=BusStops)
def get_bus_stops(bus_number: str, diet: Diet = Query("all"), db: Session = Depends(get_db)) -> BusStops:
    """Every stop on this bus's run today: scheduled and expected arrival, order cut-off, and dhaba counts. Public.

    expected_arrival = departure + minutes_from_departure + delay;
    order_cutoff = min(expected_arrival - prep - 10) over the stop's live dhabas.
    """
    bus = find_bus(db, bus_number)
    run = todays_run(db, bus)
    route = _route_with_stops(db, bus.route_id)
    now = datetime.now(timezone.utc)

    stops = []
    for stop in sorted(route.stops, key=lambda s: s.sequence_order):
        live = [d for d in stop.dhabas if is_live(d)]
        shown = sponsored_first([d for d in live if shown_for_diet(d, diet)])
        faces = [face_item(d, diet) for d in shown]
        offer = next((d for d in shown if d.sponsored_offer), None)
        expected = run.expected_at(stop)
        cutoff = stop_cutoff(expected, stop)
        stops.append(StopTiming(
            stop_id=stop.id, sequence=stop.sequence_order, name=stop.name,
            minutes_from_departure=stop.minutes_from_origin, halt_minutes=stop.halt_duration_minutes,
            scheduled=run.scheduled_at(stop), expected_arrival=expected, order_cutoff=cutoff,
            ordering_open=cutoff is not None and now <= cutoff,
            dhaba_count=len(live),
            dhaba_count_for_diet=len(shown),
            has_offer=any(d.sponsored_offer for d in live),
            offer_dhaba_name=offer.name if offer else None,
            face_images=[f.image_url for f in faces if f is not None and f.image_url],
            cuisines=list(dict.fromkeys(label for d in shown if (label := cuisine_label(d)))),
        ))
    return BusStops(bus=bus_summary(run), diet=diet, stops=stops)
