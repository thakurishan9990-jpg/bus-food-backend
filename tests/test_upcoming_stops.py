from datetime import datetime, timedelta, timezone

from app.models.route import Route
from app.models.stop import Stop
from app.models.trip import Trip, TripStatus
from app.models.user import UserRole
from tests.conftest import auth_header, make_user


def _build_route_and_trip(db_session, stop_specs, departure_offset_minutes: int, status=TripStatus.IN_TRANSIT):
    """stop_specs: list of (name, minutes_from_origin, halt_duration_minutes)."""
    route = Route(name="Upcoming Test Route", origin="A", destination="B")
    db_session.add(route)
    db_session.flush()

    stops = []
    for i, (name, minutes_from_origin, halt_duration_minutes) in enumerate(stop_specs, start=1):
        stop = Stop(
            route_id=route.id, name=name, lat=0, lng=0, sequence_order=i,
            minutes_from_origin=minutes_from_origin, halt_duration_minutes=halt_duration_minutes,
        )
        db_session.add(stop)
        stops.append(stop)
    db_session.flush()

    departure_time = datetime.now(timezone.utc) + timedelta(minutes=departure_offset_minutes)
    trip = Trip(
        route_id=route.id, operator="Op", bus_number=f"TEST-{departure_offset_minutes}",
        departure_time=departure_time, current_delay_minutes=0, status=status,
    )
    db_session.add(trip)
    db_session.commit()
    return trip, stops


def test_mid_route_excludes_long_passed_stops_but_keeps_upcoming(client, db_session):
    # Departure was 40 min ago.
    # Stop A: eta = departure+10 = now-30, halt=5 -> eta+halt = now-25 < now -> excluded.
    # Stop B: eta = departure+60 = now+20 -> clearly ahead -> included.
    trip, stops = _build_route_and_trip(
        db_session,
        [("A", 10, 5), ("B", 60, 10)],
        departure_offset_minutes=-40,
    )
    make_user(db_session, "9993000001", UserRole.PASSENGER)
    headers = auth_header(client, "9993000001")

    resp = client.get(f"/trips/{trip.id}/upcoming-stops", headers=headers)
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()]
    assert names == ["B"]


def test_completed_trip_returns_empty_list(client, db_session):
    trip, stops = _build_route_and_trip(
        db_session,
        [("A", 10, 5), ("B", 60, 10)],
        departure_offset_minutes=-400,
        status=TripStatus.COMPLETED,
    )
    make_user(db_session, "9993000002", UserRole.PASSENGER)
    headers = auth_header(client, "9993000002")

    resp = client.get(f"/trips/{trip.id}/upcoming-stops", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_stop_within_halt_window_is_kept_with_negative_minutes(client, db_session):
    # Departure was 20 min ago.
    # Stop A: eta = departure+10 = now-10, halt=15 -> eta+halt = now+5 >= now -> kept, negative minutes.
    # Stop B: eta = departure+10 = now-10, halt=2 -> eta+halt = now-8 < now -> excluded (same eta, short halt).
    # Stop C: eta = departure+50 = now+30 -> clearly ahead -> included.
    trip, stops = _build_route_and_trip(
        db_session,
        [("InHalt", 10, 15), ("LongGone", 10, 2), ("Ahead", 50, 5)],
        departure_offset_minutes=-20,
    )
    make_user(db_session, "9993000003", UserRole.PASSENGER)
    headers = auth_header(client, "9993000003")

    resp = client.get(f"/trips/{trip.id}/upcoming-stops", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    names = [s["name"] for s in body]
    assert names == ["InHalt", "Ahead"]

    in_halt = next(s for s in body if s["name"] == "InHalt")
    assert in_halt["minutes_until_arrival"] < 0
