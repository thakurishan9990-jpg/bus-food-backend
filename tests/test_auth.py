from datetime import timedelta

import pytest
from jose import JWTError

from app.models.dhaba import Dhaba
from app.models.user import UserRole
from app.utils.auth import create_access_token, decode_access_token, hash_password, verify_password
from tests.conftest import auth_header, make_user


# ---- Pure token/password mechanics (no DB) ----

def test_password_hash_roundtrip():
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert verify_password("secret123", hashed)
    assert not verify_password("wrong-password", hashed)


def test_token_roundtrip_contains_claims():
    token = create_access_token({"sub": "42", "role": "admin"})
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "admin"


def test_expired_token_raises():
    token = create_access_token({"sub": "1"}, expires_delta=timedelta(minutes=-1))
    with pytest.raises(JWTError):
        decode_access_token(token)


# ---- Signup / login endpoints ----

def test_signup_creates_passenger_and_returns_token(client):
    resp = client.post(
        "/auth/signup", json={"phone": "9990001111", "name": "New User", "password": "secret123"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["role"] == "passenger"
    assert "access_token" in body


def test_duplicate_signup_rejected(client):
    client.post("/auth/signup", json={"phone": "9990002222", "name": "A", "password": "secret123"})
    resp = client.post("/auth/signup", json={"phone": "9990002222", "name": "B", "password": "secret123"})
    assert resp.status_code == 409


def test_login_wrong_password_rejected(client, db_session):
    make_user(db_session, "9990003333", UserRole.PASSENGER)
    resp = client.post("/auth/login", data={"username": "9990003333", "password": "wrong"})
    assert resp.status_code == 401


def test_login_unknown_phone_rejected(client):
    resp = client.post("/auth/login", data={"username": "0000000000", "password": "whatever"})
    assert resp.status_code == 401


# ---- RBAC ----

def test_missing_token_rejected(client):
    # Passenger browsing (e.g. /routes) is public; role-gated endpoints still need a token.
    resp = client.get("/kitchen/orders")
    assert resp.status_code == 401


def test_authenticated_passenger_can_list_routes(client, db_session):
    make_user(db_session, "9990007777", UserRole.PASSENGER)
    headers = auth_header(client, "9990007777")
    resp = client.get("/routes", headers=headers)
    assert resp.status_code == 200


def test_passenger_cannot_access_admin_routes(client, db_session):
    make_user(db_session, "9990004444", UserRole.PASSENGER)
    headers = auth_header(client, "9990004444")
    resp = client.post(
        "/admin/routes", json={"name": "X", "origin": "A", "destination": "B"}, headers=headers
    )
    assert resp.status_code == 403


def test_admin_can_access_admin_routes(client, db_session):
    make_user(db_session, "9990005555", UserRole.ADMIN)
    headers = auth_header(client, "9990005555")
    resp = client.post(
        "/admin/routes", json={"name": "X", "origin": "A", "destination": "B"}, headers=headers
    )
    assert resp.status_code == 201


def test_dhaba_staff_cannot_access_other_dhabas_orders(client, db_session, seeded_route_and_dhaba):
    _, stop, dhaba = seeded_route_and_dhaba
    other_dhaba = Dhaba(stop_id=stop.id, name="Other Dhaba", avg_prep_time_minutes=10)
    db_session.add(other_dhaba)
    db_session.commit()

    make_user(db_session, "9990006666", UserRole.DHABA, dhaba_id=dhaba.id)
    headers = auth_header(client, "9990006666")

    resp = client.get(f"/dhabas/{other_dhaba.id}/incoming-orders", headers=headers)
    assert resp.status_code == 403


def test_dhaba_staff_can_access_own_dhaba_orders(client, db_session, seeded_route_and_dhaba):
    _, _, dhaba = seeded_route_and_dhaba
    make_user(db_session, "9990008888", UserRole.DHABA, dhaba_id=dhaba.id)
    headers = auth_header(client, "9990008888")

    resp = client.get(f"/dhabas/{dhaba.id}/incoming-orders", headers=headers)
    assert resp.status_code == 200
