from app.models.ad_campaign import AdCampaign, AdPlacement, AdStatus


def _campaign(db, advertiser, placement) -> AdCampaign:
    return db.query(AdCampaign).filter(AdCampaign.advertiser == advertiser, AdCampaign.placement == placement).one()


def test_view_and_tap_counters_increment(seeded_client, seeded_session):
    campaign = _campaign(seeded_session, "Pahadi Spring", AdPlacement.MENU_ADDON)
    views, taps = campaign.views, campaign.taps

    assert seeded_client.post(f"/ads/{campaign.id}/view").status_code == 204
    assert seeded_client.post(f"/ads/{campaign.id}/view").status_code == 204
    assert seeded_client.post(f"/ads/{campaign.id}/tap").status_code == 204
    seeded_session.refresh(campaign)

    assert (campaign.views, campaign.taps) == (views + 2, taps + 1)


def test_paused_campaign_is_not_returned_or_counted(seeded_client, seeded_session):
    paused = _campaign(seeded_session, "Pahadi Spring", AdPlacement.ORDER_WAIT)  # paused in the seed
    assert paused.status == AdStatus.PAUSED

    listed = seeded_client.get("/ads?placement=order_wait&route=DL-234").json()

    assert paused.id not in [a["id"] for a in listed]
    assert seeded_client.post(f"/ads/{paused.id}/view").status_code == 404
    assert seeded_client.post(f"/ads/{paused.id}/tap").status_code == 404


def test_pausing_a_live_campaign_removes_it(seeded_client, seeded_session):
    cover = _campaign(seeded_session, "SafarCover", AdPlacement.TRIP_BANNER)
    assert cover.id in [a["id"] for a in seeded_client.get("/ads?placement=trip_banner&route=DL-234").json()]

    cover.status = AdStatus.PAUSED
    seeded_session.commit()

    assert cover.id not in [a["id"] for a in seeded_client.get("/ads?placement=trip_banner&route=DL-234").json()]


def test_trip_banner_mixes_route_sponsored_dhabas_with_all_route_brands(seeded_client):
    banner = seeded_client.get("/ads?placement=trip_banner&route=DL-234").json()

    sponsored = [a for a in banner if a["placement"] == "sponsored_dhaba"]
    brands = [a for a in banner if a["placement"] == "trip_banner"]
    assert sponsored and brands
    assert all(a["dhaba_slug"].startswith("ddn-") for a in sponsored)  # only this route's dhabas
    assert banner[0]["placement"] == "sponsored_dhaba" and banner[1]["placement"] == "trip_banner"


def test_sponsored_dhabas_are_pinned_first_with_their_offer(seeded_client):
    listing = seeded_client.get("/stops/1/dhabas").json()

    pinned = [d["is_sponsored"] for d in listing]
    assert pinned[0] and listing[0]["sponsored_offer"]
    assert pinned == sorted(pinned, reverse=True)  # every sponsored dhaba comes before every other


def test_each_menu_has_one_live_addon_chosen_deterministically(seeded_client):
    first = seeded_client.get("/dhabas/ddn-punjabi-rasoi/menu").json()["addon"]
    again = seeded_client.get("/dhabas/ddn-punjabi-rasoi/menu").json()["addon"]

    assert first == again
    assert first["placement"] == "menu_addon" and first["addon_price_inr"] > 0
