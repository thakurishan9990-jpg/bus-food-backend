from datetime import datetime, timedelta, timezone

from app.config import settings
from app.models.dhaba import Dhaba, MenuItem
from app.models.route import Route
from app.models.stop import Stop
from app.models.trip import Trip, TripStatus
from app.models.user import UserRole
from app.utils.auth import create_access_token, decode_access_token
from tests.conftest import auth_header, make_user


def test_list_stops_for_route_returns_in_sequence_order(client, db_session):
    route = Route(name="Stops Order Route", origin="A", destination="B")
    db_session.add(route)
    db_session.flush()
    # Insert out of sequence order to prove the endpoint sorts, not just returns insert order.
    db_session.add(Stop(route_id=route.id, name="Third", lat=0, lng=0, sequence_order=3,
                         minutes_from_origin=60, halt_duration_minutes=5))
    db_session.add(Stop(route_id=route.id, name="First", lat=0, lng=0, sequence_order=1,
                         minutes_from_origin=10, halt_duration_minutes=5))
    db_session.add(Stop(route_id=route.id, name="Second", lat=0, lng=0, sequence_order=2,
                         minutes_from_origin=30, halt_duration_minutes=5))
    db_session.commit()

    make_user(db_session, "9996000001", UserRole.PASSENGER)
    headers = auth_header(client, "9996000001")

    resp = client.get(f"/routes/{route.id}/stops", headers=headers)
    assert resp.status_code == 200
    assert [s["name"] for s in resp.json()] == ["First", "Second", "Third"]


def test_list_stops_for_unknown_route_404s(client, db_session):
    make_user(db_session, "9996000002", UserRole.PASSENGER)
    headers = auth_header(client, "9996000002")
    resp = client.get("/routes/999999/stops", headers=headers)
    assert resp.status_code == 404


def test_me_returns_current_user(client, db_session):
    make_user(db_session, "9996000003", UserRole.DHABA)
    headers = auth_header(client, "9996000003")

    resp = client.get("/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["phone"] == "9996000003"
    assert body["role"] == "dhaba"


def test_me_requires_auth(client):
    resp = client.get("/me")
    assert resp.status_code == 401


def test_order_includes_dhaba_name_and_stop_name(client, db_session):
    route = Route(name="Order Names Route", origin="A", destination="B")
    db_session.add(route)
    db_session.flush()
    stop = Stop(route_id=route.id, name="Named Stop", lat=0, lng=0, sequence_order=1,
                minutes_from_origin=30, halt_duration_minutes=10)
    db_session.add(stop)
    db_session.flush()
    dhaba = Dhaba(stop_id=stop.id, name="Named Dhaba", avg_prep_time_minutes=10)
    db_session.add(dhaba)
    db_session.flush()
    menu_item = MenuItem(dhaba_id=dhaba.id, name="Dal", price_inr=100, is_veg=True)
    db_session.add(menu_item)
    trip = Trip(route_id=route.id, operator="Op", bus_number="NAMES-1",
                departure_time=datetime.now(timezone.utc) + timedelta(minutes=30),
                current_delay_minutes=0, status=TripStatus.IN_TRANSIT)
    db_session.add(trip)
    db_session.commit()

    make_user(db_session, "9996000004", UserRole.PASSENGER)
    headers = auth_header(client, "9996000004")

    resp = client.post(
        "/orders",
        json={
            "trip_id": trip.id, "stop_id": stop.id, "dhaba_id": dhaba.id,
            "seat_number": "A-12", "items": [{"menu_item_id": menu_item.id, "quantity": 1}],
        },
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["stop_name"] == "Named Stop"
    assert body["dhaba_name"] == "Named Dhaba"


def test_default_token_expiry_is_7_days():
    assert settings.access_token_expire_minutes == 60 * 24 * 7

    token = create_access_token({"sub": "1"})
    payload = decode_access_token(token)
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    delta = exp - datetime.now(timezone.utc)
    assert timedelta(days=6, hours=23) < delta <= timedelta(days=7)


def test_dish_images_are_served_under_static(client):
    resp = client.get("/static/dishes/butter-chicken.jpg")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"

    # The frontend mount at "/" still serves index.html.
    root = client.get("/")
    assert root.status_code == 200
    assert "text/html" in root.headers["content-type"]


def test_frontend_has_no_demo_login_shortcuts(client):
    page = client.get("/").text
    assert "<title>DhabaGo</title>" in page
    for leftover in ("Demo login", "Fill it in", "dhaba123", "admin123", "password123"):
        assert leftover not in page


def test_config_exposes_the_convenience_fee(client):
    body = client.get("/config").json()
    assert body["convenience_fee_inr"] == settings.convenience_fee_inr
    assert body["cuisines"]["punjabi"] == "North Indian"
