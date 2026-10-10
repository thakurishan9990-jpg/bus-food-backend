from datetime import datetime, timezone

from app.models.user import UserRole
from tests.conftest import auth_header, make_user


def test_admin_can_create_trip(client, db_session, seeded_route_and_dhaba):
    route, _, _ = seeded_route_and_dhaba
    make_user(db_session, "9992000001", UserRole.ADMIN)
    headers = auth_header(client, "9992000001")

    resp = client.post(
        "/admin/trips",
        json={
            "route_id": route.id,
            "operator": "UPSRTC",
            "bus_number": "UP15-AB-9999",
            "departure_time": datetime.now(timezone.utc).isoformat(),
        },
        headers=headers,
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["route_id"] == route.id
    assert body["status"] == "scheduled"
    assert body["current_delay_minutes"] == 0


def test_create_trip_with_unknown_route_404s(client, db_session):
    make_user(db_session, "9992000002", UserRole.ADMIN)
    headers = auth_header(client, "9992000002")

    resp = client.post(
        "/admin/trips",
        json={
            "route_id": 999999,
            "operator": "UPSRTC",
            "bus_number": "UP15-AB-0000",
            "departure_time": datetime.now(timezone.utc).isoformat(),
        },
        headers=headers,
    )
    assert resp.status_code == 404


def test_admin_can_update_trip(client, db_session, seeded_route_and_dhaba):
    route, _, _ = seeded_route_and_dhaba
    make_user(db_session, "9992000003", UserRole.ADMIN)
    headers = auth_header(client, "9992000003")

    create_resp = client.post(
        "/admin/trips",
        json={
            "route_id": route.id,
            "operator": "UPSRTC",
            "bus_number": "UP15-AB-1111",
            "departure_time": datetime.now(timezone.utc).isoformat(),
        },
        headers=headers,
    )
    trip_id = create_resp.json()["id"]

    resp = client.patch(
        f"/admin/trips/{trip_id}",
        json={"status": "in_transit", "bus_number": "UP15-AB-2222"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "in_transit"
    assert body["bus_number"] == "UP15-AB-2222"


def test_update_unknown_trip_404s(client, db_session):
    make_user(db_session, "9992000004", UserRole.ADMIN)
    headers = auth_header(client, "9992000004")
    resp = client.patch("/admin/trips/999999", json={"status": "cancelled"}, headers=headers)
    assert resp.status_code == 404


def test_admin_can_delete_trip(client, db_session, seeded_route_and_dhaba):
    route, _, _ = seeded_route_and_dhaba
    make_user(db_session, "9992000005", UserRole.ADMIN)
    headers = auth_header(client, "9992000005")

    create_resp = client.post(
        "/admin/trips",
        json={
            "route_id": route.id,
            "operator": "UPSRTC",
            "bus_number": "UP15-AB-3333",
            "departure_time": datetime.now(timezone.utc).isoformat(),
        },
        headers=headers,
    )
    trip_id = create_resp.json()["id"]

    resp = client.delete(f"/admin/trips/{trip_id}", headers=headers)
    assert resp.status_code == 204

    resp = client.patch(f"/admin/trips/{trip_id}", json={"status": "cancelled"}, headers=headers)
    assert resp.status_code == 404


def test_delete_unknown_trip_404s(client, db_session):
    make_user(db_session, "9992000006", UserRole.ADMIN)
    headers = auth_header(client, "9992000006")
    resp = client.delete("/admin/trips/999999", headers=headers)
    assert resp.status_code == 404


def test_passenger_cannot_create_trip(client, db_session, seeded_route_and_dhaba):
    route, _, _ = seeded_route_and_dhaba
    make_user(db_session, "9992000007", UserRole.PASSENGER)
    headers = auth_header(client, "9992000007")

    resp = client.post(
        "/admin/trips",
        json={
            "route_id": route.id,
            "operator": "UPSRTC",
            "bus_number": "UP15-AB-4444",
            "departure_time": datetime.now(timezone.utc).isoformat(),
        },
        headers=headers,
    )
    assert resp.status_code == 403
