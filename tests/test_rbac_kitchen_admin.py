import pytest

from app.config import settings
from tests.conftest import demo_headers, open_ordering

BUS = "UK07 PA 1187"


@pytest.fixture()
def orders(seeded_client, seeded_session):
    """One order at the demo dhaba user's own dhaba (Punjabi Rasoi) and one at another Meerut dhaba."""
    _, stop = open_ordering(seeded_session, BUS, stop_sequence=1, minutes_left=30)
    other_slug = next(d["slug"] for d in seeded_client.get(f"/stops/{stop.id}/dhabas").json()
                      if d["slug"] != "ddn-punjabi-rasoi")
    placed = {}
    for slug in ("ddn-punjabi-rasoi", other_slug):
        item = seeded_client.get(f"/dhabas/{slug}/menu").json()["items"][0]
        resp = seeded_client.post("/orders", headers=demo_headers(seeded_client, "passenger"), json={
            "bus_number": BUS, "stop_id": stop.id, "seat_number": "B-08",
            "items": [{"menu_item_id": item["id"], "quantity": 1}],
        })
        assert resp.status_code == 201, resp.text
        placed[slug] = resp.json()
    return placed["ddn-punjabi-rasoi"], placed[other_slug]


# ---- role checks ----

@pytest.mark.parametrize("path", ["/admin/operations", "/admin/business"])
@pytest.mark.parametrize("role", ["passenger", "dhaba"])
def test_non_admins_get_403_on_admin(seeded_client, role, path):
    assert seeded_client.get(path, headers=demo_headers(seeded_client, role)).status_code == 403


@pytest.mark.parametrize("path", ["/admin/operations", "/admin/business", "/kitchen/orders"])
def test_anonymous_gets_401_on_role_endpoints(seeded_client, path):
    assert seeded_client.get(path).status_code == 401


@pytest.mark.parametrize("role", ["passenger", "admin"])
def test_only_dhaba_staff_use_the_kitchen(seeded_client, orders, role):
    own, _ = orders
    headers = demo_headers(seeded_client, role)

    assert seeded_client.get("/kitchen/orders", headers=headers).status_code == 403
    assert seeded_client.patch(f"/kitchen/orders/{own['id']}", json={"status": "accepted"},
                               headers=headers).status_code == 403


def test_passenger_browsing_is_public(seeded_client):
    for path in ("/routes", "/routes/DL-234/buses", "/buses/UK07PA1187", "/buses/UK07PA1187/stops",
                 "/stops/1/dhabas", "/dhabas/ddn-punjabi-rasoi/menu", "/search?scope=all",
                 "/ads?placement=trip_banner&route=DL-234", "/config"):
        assert seeded_client.get(path).status_code == 200, path


# ---- kitchen ----

def test_kitchen_lists_only_the_callers_own_open_orders(seeded_client, orders):
    own, other = orders

    listed = seeded_client.get("/kitchen/orders", headers=demo_headers(seeded_client, "dhaba")).json()

    assert [o["id"] for o in listed] == [own["id"]]
    assert listed[0]["passenger_name"] and listed[0]["seat_number"] == "B-08"


def test_kitchen_orders_are_sorted_by_bus_arrival(seeded_client, seeded_session, orders):
    own, _ = orders
    # A second order for a later bus at the same stop.
    _, stop = open_ordering(seeded_session, "UK07 PA 2341", stop_sequence=1, minutes_left=90)
    item = seeded_client.get("/dhabas/ddn-punjabi-rasoi/menu").json()["items"][0]
    later = seeded_client.post("/orders", headers=demo_headers(seeded_client, "passenger"), json={
        "bus_number": "UK07 PA 2341", "stop_id": stop.id, "seat_number": "C-04",
        "items": [{"menu_item_id": item["id"], "quantity": 1}],
    }).json()

    listed = seeded_client.get("/kitchen/orders", headers=demo_headers(seeded_client, "dhaba")).json()

    assert [o["id"] for o in listed] == [own["id"], later["id"]]


def test_dhaba_user_gets_403_on_another_dhabas_order(seeded_client, orders):
    _, other = orders

    resp = seeded_client.patch(f"/kitchen/orders/{other['id']}", json={"status": "accepted"},
                               headers=demo_headers(seeded_client, "dhaba"))

    assert resp.status_code == 403


def test_kitchen_status_flow(seeded_client, orders):
    own, _ = orders
    headers = demo_headers(seeded_client, "dhaba")

    def move(status):
        return seeded_client.patch(f"/kitchen/orders/{own['id']}", json={"status": status}, headers=headers)

    assert move("ready").status_code == 400  # no skipping
    for status in ("accepted", "preparing", "ready", "picked_up"):
        resp = move(status)
        assert resp.status_code == 200 and resp.json()["status"] == status
    assert move("cancelled").status_code == 409  # too late to cancel
    assert seeded_client.get("/kitchen/orders", headers=headers).json() == []  # no longer open


def test_kitchen_can_cancel_a_new_order(seeded_client, orders):
    own, _ = orders

    resp = seeded_client.patch(f"/kitchen/orders/{own['id']}", json={"status": "cancelled"},
                               headers=demo_headers(seeded_client, "dhaba"))

    assert resp.status_code == 200 and resp.json()["status"] == "cancelled"


# ---- admin ----

def test_operations(seeded_client, orders):
    ops = seeded_client.get("/admin/operations", headers=demo_headers(seeded_client, "admin")).json()

    assert ops["kpis"]["active_trips"] == 8
    assert ops["kpis"]["open_orders"] == 2
    assert (ops["kpis"]["dhabas_online"], ops["kpis"]["dhabas_total"]) == (284, 284)
    assert ops["kpis"]["ad_revenue_today_inr"] > 0
    by_route = {r["route_code"]: r["open_orders"] for r in ops["orders_by_route"]}
    assert by_route["DL-234"] == 2 and sum(by_route.values()) == 2
    dl = next(t for t in ops["live_trips"] if t["route_code"] == "DL-234")
    assert (dl["bus_count"], dl["stop_count"], dl["highway"], dl["open_orders"]) == (5, 5, "NH-334", 2)


def test_operations_flags_a_kitchen_that_cannot_keep_up(seeded_client, seeded_session):
    # 4 orders x 18 min prep = 72 min of cooking, with the bus 38 min away (cut-off 10 min away).
    _, stop = open_ordering(seeded_session, BUS, stop_sequence=1, minutes_left=10)
    item = seeded_client.get("/dhabas/ddn-punjabi-rasoi/menu").json()["items"][0]
    for seat in ("1", "2", "3", "4"):
        seeded_client.post("/orders", headers=demo_headers(seeded_client, "passenger"), json={
            "bus_number": BUS, "stop_id": stop.id, "seat_number": seat,
            "items": [{"menu_item_id": item["id"], "quantity": 1}],
        })

    flags = seeded_client.get("/admin/operations", headers=demo_headers(seeded_client, "admin")).json()["flags"]

    flag = next(f for f in flags if f["dhaba_slug"] == "ddn-punjabi-rasoi")
    assert (flag["open_orders"], flag["prep_minutes"], flag["queue_minutes"]) == (4, 18, 72)
    assert flag["minutes_until_arrival"] < flag["queue_minutes"]


def test_business(seeded_client, orders):
    biz = seeded_client.get("/admin/business", headers=demo_headers(seeded_client, "admin")).json()

    assert biz["example_order"] == {
        "food": 250, "dhaba_keeps": 220, "commission": 30, "commission_pct": 12, "fee": 7, "dhabago_earns": 37,
    }
    income = biz["income_today"]
    assert income["orders"] == 2
    assert income["convenience_fees_inr"] == 2 * settings.convenience_fee_inr
    assert income["commission_inr"] == sum(o["commission_inr"] for o in orders)
    assert income["total"] == (income["commission_inr"] + income["convenience_fees_inr"]
                               + income["ads_inr"] + income["addon_sales_inr"])


def test_example_order_follows_config(seeded_client, monkeypatch):
    monkeypatch.setattr(settings, "default_commission_pct", 15)
    monkeypatch.setattr(settings, "convenience_fee_inr", 9)

    example = seeded_client.get("/admin/business", headers=demo_headers(seeded_client, "admin")).json()["example_order"]

    assert example == {"food": 250, "dhaba_keeps": 212, "commission": 38, "commission_pct": 15,
                       "fee": 9, "dhabago_earns": 47}
