import pytest

from app.config import settings
from app.models.ad_campaign import AdCampaign, AdPlacement, AdStatus
from app.models.dhaba import MenuItem
from app.models.order import Order
from tests.conftest import demo_headers, open_ordering

BUS = "UK07 PA 1187"


@pytest.fixture()
def meerut(seeded_session):
    """Ordering open at Meerut on UK07 PA 1187, with 30 minutes to the cut-off."""
    _, stop = open_ordering(seeded_session, BUS, stop_sequence=1, minutes_left=30)
    return stop


def _menu(client, slug="ddn-punjabi-rasoi"):
    return client.get(f"/dhabas/{slug}/menu").json()


def _order(client, stop, items, **extra):
    body = {"bus_number": BUS, "stop_id": stop.id, "seat_number": "A-12", "items": items, **extra}
    return client.post("/orders", json=body, headers=demo_headers(client, "passenger"))


def test_order_totals_are_computed_on_the_server(seeded_client, meerut):
    menu = _menu(seeded_client)
    a, b = menu["items"][0], menu["items"][1]

    resp = _order(seeded_client, meerut, [
        {"menu_item_id": a["id"], "quantity": 1, "price_inr": 1, "unit_price_inr": 1},
        {"menu_item_id": b["id"], "quantity": 2},
    ], subtotal_inr=1, total_inr=1, commission_inr=0)

    assert resp.status_code == 201, resp.text
    order = resp.json()
    subtotal = a["price_inr"] + 2 * b["price_inr"]
    assert order["subtotal_inr"] == subtotal
    assert order["convenience_fee_inr"] == settings.convenience_fee_inr == 7
    assert order["total_inr"] == subtotal + 7
    assert [i["unit_price_inr"] for i in order["items"]] == [a["price_inr"], b["price_inr"]]
    assert order["bus_number"] == BUS and order["seat_number"] == "A-12"


@pytest.mark.parametrize("food_inr, commission_inr", [(335, 40), (505, 61), (250, 30), (85, 10)])
def test_commission_is_12_percent_rounded(seeded_client, seeded_session, meerut, food_inr, commission_inr):
    menu = _menu(seeded_client)
    item = seeded_session.get(MenuItem, menu["items"][0]["id"])
    item.price_inr = food_inr
    seeded_session.commit()

    order = _order(seeded_client, meerut, [{"menu_item_id": item.id, "quantity": 1}]).json()

    assert order["commission_inr"] == commission_inr == round(food_inr * 12 / 100)
    stored = seeded_session.get(Order, order["id"])
    assert stored.commission_inr == commission_inr  # saved at order time


def test_addon_lines_count_toward_the_total_but_not_the_commission(seeded_client, meerut):
    menu = _menu(seeded_client)
    food, addon = menu["items"][0], menu["addon"]

    order = _order(seeded_client, meerut, [
        {"menu_item_id": food["id"], "quantity": 1},
        {"addon_campaign_id": addon["id"], "quantity": 2},
    ]).json()

    assert order["subtotal_inr"] == food["price_inr"] + 2 * addon["addon_price_inr"]
    assert order["total_inr"] == order["subtotal_inr"] + 7
    assert order["commission_inr"] == round(food["price_inr"] * 12 / 100)
    assert order["items"][1]["name"] == addon["addon_item_name"]


def test_paused_or_non_addon_campaign_cannot_be_ordered(seeded_client, seeded_session, meerut):
    food = _menu(seeded_client)["items"][0]
    banner = seeded_session.query(AdCampaign).filter(AdCampaign.placement == AdPlacement.TRIP_BANNER).first()
    addon = seeded_session.query(AdCampaign).filter(AdCampaign.placement == AdPlacement.MENU_ADDON).first()
    addon.status = AdStatus.PAUSED
    seeded_session.commit()

    for campaign in (banner, addon):
        resp = _order(seeded_client, meerut, [
            {"menu_item_id": food["id"], "quantity": 1}, {"addon_campaign_id": campaign.id, "quantity": 1},
        ])
        assert resp.status_code == 400


def test_items_from_two_dhabas_are_rejected(seeded_client, meerut):
    others = [d for d in seeded_client.get(f"/stops/{meerut.id}/dhabas").json() if d["slug"] != "ddn-punjabi-rasoi"]
    mine, theirs = _menu(seeded_client)["items"][0], _menu(seeded_client, others[0]["slug"])["items"][0]

    resp = _order(seeded_client, meerut, [
        {"menu_item_id": mine["id"], "quantity": 1}, {"menu_item_id": theirs["id"], "quantity": 1},
    ])

    assert resp.status_code == 400
    assert resp.json()["detail"] == "An order can only contain items from one dhaba"


def test_order_after_the_cutoff_is_rejected(seeded_client, seeded_session):
    _, stop = open_ordering(seeded_session, BUS, stop_sequence=1, minutes_left=-1)
    food = _menu(seeded_client)["items"][0]

    resp = _order(seeded_client, stop, [{"menu_item_id": food["id"], "quantity": 1}])

    assert resp.status_code == 409
    assert "Too late to order" in resp.json()["detail"]


def test_order_just_before_the_cutoff_is_accepted(seeded_client, seeded_session):
    _, stop = open_ordering(seeded_session, BUS, stop_sequence=1, minutes_left=1)
    food = _menu(seeded_client)["items"][0]

    assert _order(seeded_client, stop, [{"menu_item_id": food["id"], "quantity": 1}]).status_code == 201


def test_seat_number_is_required(seeded_client, meerut):
    food = _menu(seeded_client)["items"][0]

    for seat in (None, "", "   "):
        body = {"bus_number": BUS, "stop_id": meerut.id, "items": [{"menu_item_id": food["id"], "quantity": 1}]}
        if seat is not None:
            body["seat_number"] = seat
        resp = seeded_client.post("/orders", json=body, headers=demo_headers(seeded_client, "passenger"))
        assert resp.status_code == 422


def test_ordering_needs_a_passenger_login(seeded_client, meerut):
    food = _menu(seeded_client)["items"][0]
    body = {"bus_number": BUS, "stop_id": meerut.id, "seat_number": "A-12",
            "items": [{"menu_item_id": food["id"], "quantity": 1}]}

    assert seeded_client.post("/orders", json=body).status_code == 401
    for role in ("dhaba", "admin"):
        assert seeded_client.post("/orders", json=body, headers=demo_headers(seeded_client, role)).status_code == 403
