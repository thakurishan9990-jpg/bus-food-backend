from datetime import datetime, timedelta, timezone
from app.config import settings

from app.models.dhaba import Dhaba, MenuItem
from app.models.route import Route
from app.models.stop import Stop
from app.models.trip import Trip, TripStatus
from app.models.user import UserRole
from tests.conftest import auth_header, make_user


def _build_route_stop_dhaba_menu(db_session, stop_name="Stop1", minutes_from_origin=30, prep_time=10):
    route = Route(name="Validation Test Route", origin="A", destination="B")
    db_session.add(route)
    db_session.flush()

    stop = Stop(
        route_id=route.id, name=stop_name, lat=0, lng=0, sequence_order=1,
        minutes_from_origin=minutes_from_origin, halt_duration_minutes=10,
    )
    db_session.add(stop)
    db_session.flush()

    dhaba = Dhaba(stop_id=stop.id, name="Validation Dhaba", avg_prep_time_minutes=prep_time)
    db_session.add(dhaba)
    db_session.flush()

    menu_item = MenuItem(dhaba_id=dhaba.id, name="Dal", price_inr=100, is_veg=True)
    db_session.add(menu_item)
    db_session.commit()
    return route, stop, dhaba, menu_item


def _trip(db_session, route, minutes_until_eta_at_stop, status=TripStatus.IN_TRANSIT, delay=0, stop_minutes_from_origin=30):
    departure_time = datetime.now(timezone.utc) + timedelta(
        minutes=minutes_until_eta_at_stop - stop_minutes_from_origin - delay
    )
    trip = Trip(
        route_id=route.id, operator="Op", bus_number=f"VAL-{minutes_until_eta_at_stop}-{status.value}-{delay}",
        departure_time=departure_time, current_delay_minutes=delay, status=status,
    )
    db_session.add(trip)
    db_session.commit()
    return trip


# 1. totals are computed server-side, never trusted from the client.

def test_client_supplied_total_is_ignored(client, db_session):
    route, stop, dhaba, menu_item = _build_route_stop_dhaba_menu(db_session)
    trip = _trip(db_session, route, minutes_until_eta_at_stop=60)
    make_user(db_session, "9995000001", UserRole.PASSENGER)
    headers = auth_header(client, "9995000001")

    resp = client.post(
        "/orders",
        json={
            "trip_id": trip.id, "stop_id": stop.id, "dhaba_id": dhaba.id,
            "total_inr": 1,  # attempted spoof; schema doesn't even accept this field
            "seat_number": "A-12", "items": [{"menu_item_id": menu_item.id, "quantity": 2}],
        },
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["subtotal_inr"] == 200
    assert body["total_inr"] == 200 + settings.convenience_fee_inr


# 2. unit_price_inr is snapshotted onto OrderItem at creation.

def test_unit_price_is_snapshotted_on_order_item(client, db_session):
    route, stop, dhaba, menu_item = _build_route_stop_dhaba_menu(db_session)
    trip = _trip(db_session, route, minutes_until_eta_at_stop=60)
    make_user(db_session, "9995000002", UserRole.PASSENGER)
    headers = auth_header(client, "9995000002")

    resp = client.post(
        "/orders",
        json={
            "trip_id": trip.id, "stop_id": stop.id, "dhaba_id": dhaba.id,
            "seat_number": "A-12", "items": [{"menu_item_id": menu_item.id, "quantity": 1}],
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["items"][0]["unit_price_inr"] == 100

    # Now change the menu price -- the already-placed order must not change.
    menu_item.price_inr = 500
    db_session.commit()

    order_id = resp.json()["id"]
    get_resp = client.get(f"/passengers/{resp.json()['passenger_id']}/orders", headers=headers)
    order = next(o for o in get_resp.json() if o["id"] == order_id)
    assert order["items"][0]["unit_price_inr"] == 100
    assert order["subtotal_inr"] == 100


# 3. the cutoff check uses the trip's CURRENT delay at the moment of ordering.

def test_cutoff_uses_current_delay_not_zero(client, db_session):
    route, stop, dhaba, menu_item = _build_route_stop_dhaba_menu(db_session, prep_time=15)
    # stop.minutes_from_origin=30. departure was 20 min ago, so with delay=0 the ETA
    # would be departure+30 = now+10 (needs prep 15 + buffer 10 = 25 -> would 409).
    # But the trip already has a 30 min delay on record, pushing the real ETA to
    # now+40, which is enough. If the code used delay=0 here this would 409 instead.
    departure_time = datetime.now(timezone.utc) - timedelta(minutes=20)
    trip = Trip(
        route_id=route.id, operator="Op", bus_number="VAL-delay-check",
        departure_time=departure_time, current_delay_minutes=30, status=TripStatus.IN_TRANSIT,
    )
    db_session.add(trip)
    db_session.commit()
    make_user(db_session, "9995000003", UserRole.PASSENGER)
    headers = auth_header(client, "9995000003")

    resp = client.post(
        "/orders",
        json={
            "trip_id": trip.id, "stop_id": stop.id, "dhaba_id": dhaba.id,
            "seat_number": "A-12", "items": [{"menu_item_id": menu_item.id, "quantity": 1}],
        },
        headers=headers,
    )
    assert resp.status_code == 201


# 4. ordering from a dhaba whose stop_id doesn't match the order's stop_id is rejected (400).

def test_dhaba_stop_mismatch_rejected(client, db_session):
    route, stop, dhaba, menu_item = _build_route_stop_dhaba_menu(db_session)
    other_stop = Stop(
        route_id=route.id, name="OtherStop", lat=0, lng=0, sequence_order=2,
        minutes_from_origin=60, halt_duration_minutes=10,
    )
    db_session.add(other_stop)
    db_session.commit()

    trip = _trip(db_session, route, minutes_until_eta_at_stop=60)
    make_user(db_session, "9995000004", UserRole.PASSENGER)
    headers = auth_header(client, "9995000004")

    resp = client.post(
        "/orders",
        json={
            "trip_id": trip.id, "stop_id": other_stop.id, "dhaba_id": dhaba.id,  # dhaba is at `stop`, not `other_stop`
            "seat_number": "A-12", "items": [{"menu_item_id": menu_item.id, "quantity": 1}],
        },
        headers=headers,
    )
    assert resp.status_code == 400


# 5. ordering on a trip whose status is completed or cancelled is rejected (400).

def test_order_on_completed_trip_rejected(client, db_session):
    route, stop, dhaba, menu_item = _build_route_stop_dhaba_menu(db_session)
    trip = _trip(db_session, route, minutes_until_eta_at_stop=60, status=TripStatus.COMPLETED)
    make_user(db_session, "9995000005", UserRole.PASSENGER)
    headers = auth_header(client, "9995000005")

    resp = client.post(
        "/orders",
        json={
            "trip_id": trip.id, "stop_id": stop.id, "dhaba_id": dhaba.id,
            "seat_number": "A-12", "items": [{"menu_item_id": menu_item.id, "quantity": 1}],
        },
        headers=headers,
    )
    assert resp.status_code == 400


def test_order_on_cancelled_trip_rejected(client, db_session):
    route, stop, dhaba, menu_item = _build_route_stop_dhaba_menu(db_session)
    trip = _trip(db_session, route, minutes_until_eta_at_stop=60, status=TripStatus.CANCELLED)
    make_user(db_session, "9995000006", UserRole.PASSENGER)
    headers = auth_header(client, "9995000006")

    resp = client.post(
        "/orders",
        json={
            "trip_id": trip.id, "stop_id": stop.id, "dhaba_id": dhaba.id,
            "seat_number": "A-12", "items": [{"menu_item_id": menu_item.id, "quantity": 1}],
        },
        headers=headers,
    )
    assert resp.status_code == 400


def test_order_on_scheduled_trip_still_allowed(client, db_session):
    # Sanity check: "scheduled" (not yet departed) must NOT be blocked by the new check --
    # only completed/cancelled are.
    route, stop, dhaba, menu_item = _build_route_stop_dhaba_menu(db_session)
    trip = _trip(db_session, route, minutes_until_eta_at_stop=60, status=TripStatus.SCHEDULED)
    make_user(db_session, "9995000007", UserRole.PASSENGER)
    headers = auth_header(client, "9995000007")

    resp = client.post(
        "/orders",
        json={
            "trip_id": trip.id, "stop_id": stop.id, "dhaba_id": dhaba.id,
            "seat_number": "A-12", "items": [{"menu_item_id": menu_item.id, "quantity": 1}],
        },
        headers=headers,
    )
    assert resp.status_code == 201
