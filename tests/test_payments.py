"""Razorpay payment flow.

Razorpay itself is never called: respx intercepts the HTTP, and signatures are
built with the same HMAC the server checks, using a fake test secret.
"""

import hmac
import json
from hashlib import sha256

import httpx
import pytest
import respx

from app.config import settings
from app.models.dhaba import MenuItem
from app.models.order import Order, OrderStatus, PaymentStatus
from app.models.user import UserRole
from app.services import payment_service
from tests.conftest import auth_header, demo_headers, make_user, open_ordering

BUS = "UK07 PA 1187"
KEY_ID = "rzp_test_fake123"
KEY_SECRET = "fake_secret_value"
RZP_ORDER_ID = "order_TESTRZP001"
RZP_PAYMENT_ID = "pay_TESTRZP001"
RZP_ORDERS = "https://api.razorpay.com/v1/orders"


@pytest.fixture()
def meerut(seeded_session):
    """Ordering open at Meerut on UK07 PA 1187, with 30 minutes to the cut-off."""
    _, stop = open_ordering(seeded_session, BUS, stop_sequence=1, minutes_left=30)
    return stop


@pytest.fixture()
def payments_on(monkeypatch):
    monkeypatch.setattr(settings, "razorpay_key_id", KEY_ID)
    monkeypatch.setattr(settings, "razorpay_key_secret", KEY_SECRET)
    yield


@pytest.fixture()
def rzp():
    """Razorpay's order endpoint, mocked. Yields the route so tests can inspect the request."""
    with respx.mock:
        yield respx.post(RZP_ORDERS).mock(return_value=httpx.Response(200, json={"id": RZP_ORDER_ID}))


def _signature(order_id: str = RZP_ORDER_ID, payment_id: str = RZP_PAYMENT_ID) -> str:
    return hmac.new(KEY_SECRET.encode(), f"{order_id}|{payment_id}".encode(), sha256).hexdigest()


def _place(client, session, stop, qty=2, price_inr=180):
    """Order `qty` of the first Punjabi Rasoi dish, priced at `price_inr`, as the demo passenger."""
    first = client.get("/dhabas/ddn-punjabi-rasoi/menu").json()["items"][0]
    item = session.get(MenuItem, first["id"])
    item.price_inr = price_inr
    session.commit()
    headers = demo_headers(client, "passenger")
    resp = client.post(
        "/orders",
        json={"bus_number": BUS, "stop_id": stop.id, "seat_number": "A-12",
              "items": [{"menu_item_id": item.id, "quantity": qty}]},
        headers=headers,
    )
    return resp, headers


def _verify(client, order_id, headers, signature=None):
    return client.post(
        f"/orders/{order_id}/payment/verify",
        json={"razorpay_payment_id": RZP_PAYMENT_ID, "razorpay_signature": signature or _signature()},
        headers=headers,
    )


# --------------------------------------------------------------- payments off

@pytest.mark.parametrize("key_id, key_secret", [("", ""), (KEY_ID, ""), ("", KEY_SECRET)])
def test_without_both_keys_order_goes_straight_to_the_kitchen(
    seeded_client, seeded_session, meerut, monkeypatch, key_id, key_secret
):
    """Either Razorpay key missing -> payments off, and the app behaves exactly as before.

    This is what keeps the live site working until both env vars are set.
    """
    monkeypatch.setattr(settings, "razorpay_key_id", key_id)
    monkeypatch.setattr(settings, "razorpay_key_secret", key_secret)
    assert settings.payments_enabled is False

    with respx.mock:  # any call to Razorpay would fail the test
        resp, _ = _place(seeded_client, seeded_session, meerut)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "placed"
    assert body["payment_status"] == "not_required"
    assert body["payment"] is None

    kitchen = demo_headers(seeded_client, "dhaba")
    dhaba_id = seeded_session.get(Order, body["id"]).dhaba_id
    assert [o["id"] for o in seeded_client.get("/kitchen/orders", headers=kitchen).json()] == [body["id"]]
    queue = seeded_client.get(f"/dhabas/{dhaba_id}/incoming-orders", headers=kitchen).json()
    assert [o["id"] for o in queue] == [body["id"]]


# ---------------------------------------------------------------- payments on

def test_order_is_held_until_paid_and_carries_checkout_details(seeded_client, seeded_session, meerut, payments_on, rzp):
    resp, _ = _place(seeded_client, seeded_session, meerut)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "awaiting_payment"
    assert body["payment_status"] == "awaiting"
    assert body["payment"]["key_id"] == KEY_ID
    assert body["payment"]["razorpay_order_id"] == RZP_ORDER_ID
    assert body["payment"]["currency"] == "INR"


def test_razorpay_is_charged_the_total_including_the_fee(seeded_client, seeded_session, meerut, payments_on, rzp):
    """2 x ₹180 food + ₹7 fee = ₹367 -> 36700 paise, both to the browser and to Razorpay."""
    resp, _ = _place(seeded_client, seeded_session, meerut, qty=2, price_inr=180)
    body = resp.json()

    assert body["subtotal_inr"] == 360
    assert body["total_inr"] == 360 + settings.convenience_fee_inr == 367
    assert body["payment"]["amount_paise"] == 36700
    sent = json.loads(rzp.calls.last.request.content)
    assert sent["amount"] == 36700
    assert sent["currency"] == "INR"


def test_to_paise_is_exact_integer_arithmetic():
    assert payment_service.to_paise(367) == 36700
    assert isinstance(payment_service.to_paise(367), int)


def test_razorpay_refusing_the_order_is_reported(seeded_client, seeded_session, meerut, payments_on):
    with respx.mock:
        respx.post(RZP_ORDERS).mock(return_value=httpx.Response(401, json={"error": "bad key"}))
        resp, _ = _place(seeded_client, seeded_session, meerut)
    assert resp.status_code == 400
    assert seeded_session.query(Order).count() == 0


def test_kitchen_does_not_see_an_unpaid_order(seeded_client, seeded_session, meerut, payments_on, rzp):
    placed, _ = _place(seeded_client, seeded_session, meerut)
    order = seeded_session.get(Order, placed.json()["id"])
    kitchen = demo_headers(seeded_client, "dhaba")

    assert seeded_client.get("/kitchen/orders", headers=kitchen).json() == []
    legacy = seeded_client.get(f"/dhabas/{order.dhaba_id}/incoming-orders", headers=kitchen)
    assert legacy.status_code == 200 and legacy.json() == []
    # ...and can't act on it by guessing the id.
    poke = seeded_client.patch(f"/kitchen/orders/{order.id}", json={"status": "cancelled"}, headers=kitchen)
    assert poke.status_code == 404


def test_unpaid_orders_are_not_counted_as_income(seeded_client, seeded_session, meerut, payments_on, rzp):
    admin = demo_headers(seeded_client, "admin")
    before = seeded_client.get("/admin/business", headers=admin).json()["income_today"]
    _place(seeded_client, seeded_session, meerut)
    after = seeded_client.get("/admin/business", headers=admin).json()["income_today"]
    assert after == before


def test_verified_payment_releases_the_order_to_the_kitchen(seeded_client, seeded_session, meerut, payments_on, rzp):
    placed, headers = _place(seeded_client, seeded_session, meerut)
    order_id = placed.json()["id"]

    resp = _verify(seeded_client, order_id, headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "placed"
    assert resp.json()["payment_status"] == "paid"
    assert seeded_session.get(Order, order_id).razorpay_payment_id == RZP_PAYMENT_ID

    kitchen = demo_headers(seeded_client, "dhaba")
    assert [o["id"] for o in seeded_client.get("/kitchen/orders", headers=kitchen).json()] == [order_id]


def test_forged_signature_is_rejected(seeded_client, seeded_session, meerut, payments_on, rzp):
    placed, headers = _place(seeded_client, seeded_session, meerut)
    order_id = placed.json()["id"]

    resp = _verify(seeded_client, order_id, headers, signature="deadbeef")
    assert resp.status_code == 400
    assert seeded_session.get(Order, order_id).status == OrderStatus.AWAITING_PAYMENT


def test_signature_check_uses_constant_time_comparison(monkeypatch, payments_on):
    calls = []
    real = hmac.compare_digest
    monkeypatch.setattr(payment_service.hmac, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
    assert payment_service.verify_signature(RZP_ORDER_ID, RZP_PAYMENT_ID, _signature())
    assert not payment_service.verify_signature(RZP_ORDER_ID, RZP_PAYMENT_ID, "deadbeef")
    assert len(calls) == 2


def test_another_passenger_cannot_pay_for_your_order(seeded_client, seeded_session, meerut, payments_on, rzp):
    placed, _ = _place(seeded_client, seeded_session, meerut)
    make_user(seeded_session, "9000000009", UserRole.PASSENGER)
    intruder = auth_header(seeded_client, "9000000009")

    assert _verify(seeded_client, placed.json()["id"], intruder).status_code == 403
    assert seeded_client.get(f"/orders/{placed.json()['id']}/payment", headers=intruder).status_code == 403


def test_payment_landing_after_the_cutoff_is_refunded_and_cancelled(
    seeded_client, seeded_session, meerut, payments_on, rzp
):
    """The bus kept moving while the passenger was on the checkout screen."""
    refund_route = respx.post(f"https://api.razorpay.com/v1/payments/{RZP_PAYMENT_ID}/refund").mock(
        return_value=httpx.Response(200, json={"id": "rfnd_1", "status": "processed"})
    )
    placed, headers = _place(seeded_client, seeded_session, meerut)
    order_id = placed.json()["id"]

    # The cut-off passed five minutes ago.
    open_ordering(seeded_session, BUS, stop_sequence=1, minutes_left=-5)

    resp = _verify(seeded_client, order_id, headers)
    assert resp.status_code == 409
    assert refund_route.called

    order = seeded_session.get(Order, order_id)
    seeded_session.refresh(order)
    assert order.status == OrderStatus.CANCELLED
    assert order.payment_status == PaymentStatus.REFUNDED


def test_an_order_cannot_be_paid_for_twice(seeded_client, seeded_session, meerut, payments_on, rzp):
    placed, headers = _place(seeded_client, seeded_session, meerut)
    order_id = placed.json()["id"]

    assert _verify(seeded_client, order_id, headers).status_code == 200
    assert _verify(seeded_client, order_id, headers).status_code == 409


def test_unpaid_order_can_still_be_cancelled(seeded_client, seeded_session, meerut, payments_on, rzp):
    placed, headers = _place(seeded_client, seeded_session, meerut)

    resp = seeded_client.patch(f"/orders/{placed.json()['id']}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_checkout_can_be_reopened_after_the_window_is_closed(seeded_client, seeded_session, meerut, payments_on, rzp):
    """A passenger who dismisses the Razorpay window must be able to pay later."""
    placed, headers = _place(seeded_client, seeded_session, meerut)
    order_id = placed.json()["id"]

    again = seeded_client.get(f"/orders/{order_id}/payment", headers=headers)
    assert again.status_code == 200
    assert again.json()["razorpay_order_id"] == RZP_ORDER_ID
    assert again.json()["amount_paise"] == placed.json()["total_inr"] * 100

    _verify(seeded_client, order_id, headers)
    # Once paid there is nothing left to reopen.
    assert seeded_client.get(f"/orders/{order_id}/payment", headers=headers).status_code == 400
