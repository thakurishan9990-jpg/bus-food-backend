from app.models.dhaba import Dhaba
from app.models.stop import Stop
from tests.conftest import SEED_DATA

PURE_VEG = {d["slug"] for d in SEED_DATA["dhabas"] if d["is_pure_veg"]}


def test_nonveg_hides_every_pure_veg_dhaba(seeded_client, seeded_session):
    shown = set()
    for stop in seeded_session.query(Stop):
        listing = seeded_client.get(f"/stops/{stop.id}/dhabas?diet=nonveg").json()
        shown |= {d["slug"] for d in listing}
        assert not any(d["is_pure_veg"] for d in listing)

    assert PURE_VEG  # the seed has pure-veg dhabas to hide...
    assert shown.isdisjoint(PURE_VEG)
    assert len(shown) == 284 - len(PURE_VEG)  # ...and every other dhaba still shows


def test_veg_and_all_listings(seeded_client, seeded_session):
    stop = seeded_session.query(Stop).filter(Stop.dhabas.any(Dhaba.slug.in_(PURE_VEG))).first()
    everyone = seeded_client.get(f"/stops/{stop.id}/dhabas?diet=all").json()
    veg = seeded_client.get(f"/stops/{stop.id}/dhabas?diet=veg").json()

    assert len(everyone) == len(stop.dhabas)
    assert {d["slug"] for d in veg} <= {d["slug"] for d in everyone}
    assert all(d["matching_item_count"] > 0 for d in veg)


def test_stop_listing_is_sponsored_first_then_by_rating(seeded_client, seeded_session):
    for stop in seeded_session.query(Stop):
        listing = seeded_client.get(f"/stops/{stop.id}/dhabas").json()
        keys = [(not d["is_sponsored"], -d["rating"]) for d in listing]
        assert keys == sorted(keys)


def test_face_image_matches_the_diet(seeded_client):
    # Pind Di Rasoi's signature is veg, so with nonveg its card shows its first non-veg dish instead.
    menus = {}
    for diet in ("veg", "nonveg"):
        for d in seeded_client.get(f"/stops/1/dhabas?diet={diet}").json():
            menu = menus.setdefault(d["slug"], seeded_client.get(f"/dhabas/{d['slug']}/menu").json())
            face = next(i for i in menu["items"] if i["image_url"] == d["face_image"])
            assert face["is_veg"] == (diet == "veg")


def test_veg_menus_have_no_nonveg_items_and_counts_add_up(seeded_client, seeded_session):
    for dhaba in seeded_session.query(Dhaba):
        menu = seeded_client.get(f"/dhabas/{dhaba.slug}/menu?diet=veg").json()
        counts = menu["counts"]

        assert all(item["is_veg"] for item in menu["items"])
        assert len(menu["items"]) == counts["veg"]
        assert counts["all"] == counts["veg"] + counts["nonveg"] == len(dhaba.menu_items)


def test_pure_veg_dhaba_with_nonveg_diet_is_empty_with_a_reason(seeded_client):
    slug = sorted(PURE_VEG)[0]
    menu = seeded_client.get(f"/dhabas/{slug}/menu?diet=nonveg").json()

    assert menu["items"] == []
    assert menu["empty_reason"] == "pure_veg"
    assert menu["counts"]["nonveg"] == 0 and menu["counts"]["veg"] > 0


def test_unavailable_items_leave_the_menu(seeded_client, seeded_session):
    dhaba = seeded_session.query(Dhaba).filter(Dhaba.slug == "ddn-punjabi-rasoi").one()
    item = dhaba.menu_items[0]
    item.is_available = False
    seeded_session.commit()

    menu = seeded_client.get("/dhabas/ddn-punjabi-rasoi/menu").json()
    assert item.id not in [i["id"] for i in menu["items"]]
    assert menu["counts"]["all"] == len(dhaba.menu_items) - 1


def test_bus_stops_count_dhabas_for_the_diet(seeded_client):
    everyone = seeded_client.get("/buses/UK07 PA 1187/stops").json()["stops"]
    nonveg = seeded_client.get("/buses/UK07 PA 1187/stops?diet=nonveg").json()["stops"]

    for a, n in zip(everyone, nonveg):
        assert a["dhaba_count"] == n["dhaba_count"]
        assert n["dhaba_count_for_diet"] <= n["dhaba_count"]
    assert any(n["dhaba_count_for_diet"] < n["dhaba_count"] for n in nonveg)


def test_search_respects_diet_and_reports_the_matched_dish(seeded_client):
    res = seeded_client.get("/search?q=dosa&scope=all&diet=veg").json()

    assert 0 < len(res["results"]) <= 60
    assert all(r["matched_item"] is None or r["matched_item"]["is_veg"] for r in res["results"])
    assert any(r["matched_item"] and "dosa" in r["matched_item"]["name"].lower() for r in res["results"])
    sponsored = [r["dhaba"]["is_sponsored"] for r in res["results"]]
    assert sponsored == sorted(sponsored, reverse=True)


def test_search_caps_results_at_60(seeded_client):
    res = seeded_client.get("/search?scope=all").json()

    assert res["total"] == 284
    assert len(res["results"]) == 60


def test_search_filters(seeded_client):
    res = seeded_client.get("/search?scope=route&route=DL-234&pure_veg=true&max_prep=15&min_rating=4").json()

    assert res["results"]
    for r in res["results"]:
        d = r["dhaba"]
        assert d["route_code"] == "DL-234" and d["is_pure_veg"]
        assert d["prep_minutes"] <= 15 and d["rating"] >= 4
