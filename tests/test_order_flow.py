from datetime import datetime, timedelta, timezone

from app.config import settings
from app.models.dhaba import Dhaba, MenuItem
from app.models.route import Route
from app.models.stop import Stop
from app.models.trip import Trip, TripStatus
from app.models.user import UserRole
from tests.conftest import auth_header, make_user


def _build_trip_and_dhaba(db_session, minutes_until_eta: int, prep_time: int = 10):
    """Build a route/stop/dhaba/menu_item/trip where the stop's ETA is
    `minutes_until_eta` minutes from "now" (i.e. from trip.departure_time, used as `now`
    in the cutoff check in tests below).
    """
    route = Route(name="Flow Route", origin="A", destination="B")
    db_session.add(route)
    db_session.flush()

    stop = Stop(
        route_id=route.id, name="Stop1", lat=0, lng=0, sequence_order=1,
        minutes_from_origin=30, halt_duration_minutes=10,
    )
    db_session.add(stop)
    db_session.flush()

    dhaba = Dhaba(stop_id=stop.id, name="Flow Dhaba", avg_prep_time_minutes=prep_time)
    db_session.add(dhaba)
    db_session.flush()

    menu_item = MenuItem(dhaba_id=dhaba.id, name="Dal", price_inr=100, is_veg=True)
    db_session.add(menu_item)

    departure_time = datetime.now(timezone.utc) + timedelta(minutes=minutes_until_eta - stop.minutes_from_origin)
    trip = Trip(
        route_id=route.id, operator="Op", bus_number="B1", departure_time=departure_time,
        current_delay_minutes=0, status=TripStatus.IN_TRANSIT,
    )
    db_session.add(trip)
    db_session.commit()
    return trip, stop, dhaba, menu_item


def test_place_order_succeeds_with_enough_lead_time(client, db_session):
    trip, stop, dhaba, menu_item = _build_trip_and_dhaba(db_session, minutes_until_eta=60)
    make_user(db_session, "9991000001", UserRole.PASSENGER)
    headers = auth_header(client, "9991000001")

    resp = client.post(
        "/orders",
        json={
            "trip_id": trip.id, "stop_id": stop.id, "dhaba_id": dhaba.id,
            "seat_number": "A-12", "items": [{"menu_item_id": menu_item.id, "quantity": 2}],
        },
        headers=headers,
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "placed"
    assert body["subtotal_inr"] == 200
    assert body["total_inr"] == 200 + settings.convenience_fee_inr


def test_place_order_rejected_when_past_cutoff(client, db_session):
    trip, stop, dhaba, menu_item = _build_trip_and_dhaba(db_session, minutes_until_eta=5, prep_time=15)
    make_user(db_session, "9991000002", UserRole.PASSENGER)
    headers = auth_header(client, "9991000002")

    resp = client.post(
        "/orders",
        json={
            "trip_id": trip.id, "stop_id": stop.id, "dhaba_id": dhaba.id,
            "seat_number": "A-12", "items": [{"menu_item_id": menu_item.id, "quantity": 1}],
        },
        headers=headers,
    )

    assert resp.status_code == 409
    assert "Too late to order" in resp.json()["detail"]


def test_passenger_cannot_view_other_passengers_orders(client, db_session):
    _build_trip_and_dhaba(db_session, minutes_until_eta=60)
    user1 = make_user(db_session, "9991000003", UserRole.PASSENGER)
    make_user(db_session, "9991000004", UserRole.PASSENGER)
    headers2 = auth_header(client, "9991000004")

    resp = client.get(f"/passengers/{user1.id}/orders", headers=headers2)
    assert resp.status_code == 403


def test_full_status_flow_and_cancel_rules(client, db_session):
    trip, stop, dhaba, menu_item = _build_trip_and_dhaba(db_session, minutes_until_eta=60)
    make_user(db_session, "9991000005", UserRole.PASSENGER)
    make_user(db_session, "9991000006", UserRole.DHABA, dhaba_id=dhaba.id)

    passenger_headers = auth_header(client, "9991000005")
    dhaba_headers = auth_header(client, "9991000006")

    create_resp = client.post(
        "/orders",
        json={
            "trip_id": trip.id, "stop_id": stop.id, "dhaba_id": dhaba.id,
            "seat_number": "A-12", "items": [{"menu_item_id": menu_item.id, "quantity": 1}],
        },
        headers=passenger_headers,
    )
    order_id = create_resp.json()["id"]

    resp = client.patch(f"/orders/{order_id}/status", json={"status": "accepted"}, headers=dhaba_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"

    # cannot skip straight to picked_up
    resp = client.patch(f"/orders/{order_id}/status", json={"status": "picked_up"}, headers=dhaba_headers)
    assert resp.status_code == 400

    resp = client.patch(f"/orders/{order_id}/status", json={"status": "preparing"}, headers=dhaba_headers)
    assert resp.status_code == 200

    # once preparing, passenger can no longer cancel
    resp = client.patch(f"/orders/{order_id}/cancel", headers=passenger_headers)
    assert resp.status_code == 409


def test_delay_update_recalculates_order_eta(client, db_session):
    trip, stop, dhaba, menu_item = _build_trip_and_dhaba(db_session, minutes_until_eta=90)
    make_user(db_session, "9991000007", UserRole.PASSENGER)
    make_user(db_session, "9991000008", UserRole.ADMIN)

    passenger_headers = auth_header(client, "9991000007")
    admin_headers = auth_header(client, "9991000008")

    create_resp = client.post(
        "/orders",
        json={
            "trip_id": trip.id, "stop_id": stop.id, "dhaba_id": dhaba.id,
            "seat_number": "A-12", "items": [{"menu_item_id": menu_item.id, "quantity": 1}],
        },
        headers=passenger_headers,
    )
    order_id = create_resp.json()["id"]
    original_eta = create_resp.json()["expected_arrival_time"]

    resp = client.patch(f"/trips/{trip.id}/delay", json={"current_delay_minutes": 20}, headers=admin_headers)
    assert resp.status_code == 200

    updated_order = client.get(f"/passengers/{create_resp.json()['passenger_id']}/orders", headers=passenger_headers)
    updated_eta = next(o for o in updated_order.json() if o["id"] == order_id)["expected_arrival_time"]

    assert updated_eta != original_eta
