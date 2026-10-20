from app.models.dhaba import Dhaba
from app.models.user import UserRole
from tests.conftest import auth_header, make_user


def test_dhaba_staff_can_create_menu_item_for_own_dhaba(client, db_session, seeded_route_and_dhaba):
    _, _, dhaba = seeded_route_and_dhaba
    make_user(db_session, "9994000001", UserRole.DHABA, dhaba_id=dhaba.id)
    headers = auth_header(client, "9994000001")

    resp = client.post(
        f"/dhabas/{dhaba.id}/menu-items",
        json={"name": "Chai", "price_inr": 20, "is_veg": True, "dhaba_id": 0},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["dhaba_id"] == dhaba.id
    assert body["is_available"] is True


def test_dhaba_staff_cannot_create_menu_item_for_other_dhaba(client, db_session, seeded_route_and_dhaba):
    _, stop, dhaba = seeded_route_and_dhaba
    other_dhaba = Dhaba(stop_id=stop.id, name="Other Dhaba", avg_prep_time_minutes=10)
    db_session.add(other_dhaba)
    db_session.commit()

    make_user(db_session, "9994000002", UserRole.DHABA, dhaba_id=dhaba.id)
    headers = auth_header(client, "9994000002")

    resp = client.post(
        f"/dhabas/{other_dhaba.id}/menu-items",
        json={"name": "Chai", "price_inr": 20, "is_veg": True, "dhaba_id": 0},
        headers=headers,
    )
    assert resp.status_code == 403


def test_path_dhaba_id_overrides_body_dhaba_id(client, db_session, seeded_route_and_dhaba):
    _, stop, dhaba = seeded_route_and_dhaba
    other_dhaba = Dhaba(stop_id=stop.id, name="Other Dhaba", avg_prep_time_minutes=10)
    db_session.add(other_dhaba)
    db_session.commit()

    make_user(db_session, "9994000003", UserRole.DHABA, dhaba_id=dhaba.id)
    headers = auth_header(client, "9994000003")

    # body claims dhaba_id=other_dhaba.id, but the path (dhaba.id, their own) must win.
    resp = client.post(
        f"/dhabas/{dhaba.id}/menu-items",
        json={"name": "Chai", "price_inr": 20, "is_veg": True, "dhaba_id": other_dhaba.id},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["dhaba_id"] == dhaba.id


def test_admin_can_create_menu_item_for_any_dhaba(client, db_session, seeded_route_and_dhaba):
    _, _, dhaba = seeded_route_and_dhaba
    make_user(db_session, "9994000004", UserRole.ADMIN)
    headers = auth_header(client, "9994000004")

    resp = client.post(
        f"/dhabas/{dhaba.id}/menu-items",
        json={"name": "Chai", "price_inr": 20, "is_veg": True, "dhaba_id": 0},
        headers=headers,
    )
    assert resp.status_code == 201


def test_passenger_cannot_create_menu_item(client, db_session, seeded_route_and_dhaba):
    _, _, dhaba = seeded_route_and_dhaba
    make_user(db_session, "9994000005", UserRole.PASSENGER)
    headers = auth_header(client, "9994000005")

    resp = client.post(
        f"/dhabas/{dhaba.id}/menu-items",
        json={"name": "Chai", "price_inr": 20, "is_veg": True, "dhaba_id": 0},
        headers=headers,
    )
    assert resp.status_code == 403


def test_dhaba_staff_can_mark_own_item_unavailable(client, db_session, seeded_route_and_dhaba):
    _, _, dhaba = seeded_route_and_dhaba
    make_user(db_session, "9994000006", UserRole.DHABA, dhaba_id=dhaba.id)
    headers = auth_header(client, "9994000006")

    create_resp = client.post(
        f"/dhabas/{dhaba.id}/menu-items",
        json={"name": "Chai", "price_inr": 20, "is_veg": True, "dhaba_id": 0},
        headers=headers,
    )
    item_id = create_resp.json()["id"]

    resp = client.patch(
        f"/dhabas/{dhaba.id}/menu-items/{item_id}", json={"is_available": False}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["is_available"] is False

    # The passenger menu only lists available items.
    menu_resp = client.get(f"/dhabas/{dhaba.id}/menu")
    assert item_id not in [i["id"] for i in menu_resp.json()["items"]]


def test_dhaba_staff_cannot_update_other_dhabas_item(client, db_session, seeded_route_and_dhaba):
    _, stop, dhaba = seeded_route_and_dhaba
    other_dhaba = Dhaba(stop_id=stop.id, name="Other Dhaba", avg_prep_time_minutes=10)
    db_session.add(other_dhaba)
    db_session.commit()

    make_user(db_session, "9994000007", UserRole.DHABA, dhaba_id=other_dhaba.id)
    make_user(db_session, "9994000008", UserRole.ADMIN)
    admin_headers = auth_header(client, "9994000008")
    create_resp = client.post(
        f"/dhabas/{dhaba.id}/menu-items",
        json={"name": "Chai", "price_inr": 20, "is_veg": True, "dhaba_id": 0},
        headers=admin_headers,
    )
    item_id = create_resp.json()["id"]

    other_staff_headers = auth_header(client, "9994000007")
    resp = client.patch(
        f"/dhabas/{dhaba.id}/menu-items/{item_id}", json={"is_available": False}, headers=other_staff_headers
    )
    assert resp.status_code == 403


def test_dhaba_staff_can_delete_own_item(client, db_session, seeded_route_and_dhaba):
    _, _, dhaba = seeded_route_and_dhaba
    make_user(db_session, "9994000009", UserRole.DHABA, dhaba_id=dhaba.id)
    headers = auth_header(client, "9994000009")

    create_resp = client.post(
        f"/dhabas/{dhaba.id}/menu-items",
        json={"name": "Chai", "price_inr": 20, "is_veg": True, "dhaba_id": 0},
        headers=headers,
    )
    item_id = create_resp.json()["id"]

    resp = client.delete(f"/dhabas/{dhaba.id}/menu-items/{item_id}", headers=headers)
    assert resp.status_code == 204

    resp = client.patch(f"/dhabas/{dhaba.id}/menu-items/{item_id}", json={"is_available": False}, headers=headers)
    assert resp.status_code == 404
