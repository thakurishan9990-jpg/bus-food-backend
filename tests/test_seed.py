import json
from datetime import datetime, timezone

import pytest

from app.config import settings
from app.models.ad_campaign import AdCampaign, AdPlacement, AdStatus
from app.models.bus import Bus
from app.models.dhaba import Dhaba, DhabaStatus, MenuItem
from app.models.route import Route
from app.models.stop import Stop
from app.models.trip import Trip
from app.models.user import User, UserRole
from app.services.bus_service import IST
from app.utils.auth import hash_password, verify_password
from scripts.seed import load_seed_file, seed

SEED_DATA = load_seed_file()
TABLES = [Route, Stop, Bus, Trip, Dhaba, MenuItem, AdCampaign, User]
EXPECTED = {"routes": 8, "buses": 32, "stops": 39, "dhabas": 284, "menu_items": 2245}


def _counts(db_session) -> dict:
    return {model.__name__: db_session.query(model).count() for model in TABLES}


def _demo_user(role: str) -> dict:
    return next(u for u in SEED_DATA["demo_users"] if u["role"] == role)


def _user(db_session, phone: str) -> User:
    return db_session.query(User).filter(User.phone == phone).one()


@pytest.fixture(autouse=True)
def _no_admin_password_by_default(monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "")


# ---- counts and idempotency ----

def test_seed_loads_the_checkpoint_counts(db_session):
    counts = seed(db_session)

    assert {k: counts[k] for k in EXPECTED} == EXPECTED
    assert EXPECTED == {k: SEED_DATA["meta"]["counts"][k] for k in EXPECTED}
    table_counts = _counts(db_session)
    assert table_counts["Route"] == 8
    assert table_counts["Bus"] == 32
    assert table_counts["Trip"] == 32  # one trip today per bus
    assert table_counts["Stop"] == 39
    assert table_counts["Dhaba"] == 284
    assert table_counts["MenuItem"] == 2245
    assert table_counts["User"] == 3


def test_seed_twice_does_not_duplicate(db_session):
    seed(db_session)
    first_counts = _counts(db_session)
    seed(db_session)

    assert _counts(db_session) == first_counts
    assert db_session.query(Bus).filter(Bus.bus_number_key == "UK07PA1187").count() == 1
    assert db_session.query(Dhaba).filter(Dhaba.slug == "ddn-punjabi-rasoi").count() == 1


def test_reseed_keeps_operational_state(db_session):
    seed(db_session)
    dhaba = db_session.query(Dhaba).filter(Dhaba.slug == "ddn-punjabi-rasoi").one()
    dhaba.status = DhabaStatus.BLOCKED
    dhaba.menu_items[0].is_available = False
    bus = db_session.query(Bus).filter(Bus.bus_number_key == "UK07PA1187").one()
    bus.trips[0].current_delay_minutes = 40
    campaign = db_session.query(AdCampaign).filter(AdCampaign.placement == AdPlacement.MENU_ADDON).first()
    campaign.views += 1
    views = campaign.views
    db_session.commit()

    seed(db_session)
    db_session.expire_all()

    assert dhaba.status == DhabaStatus.BLOCKED
    assert dhaba.menu_items[0].is_available is False
    assert bus.trips[0].current_delay_minutes == 40
    assert campaign.views == views


def test_seed_rejects_an_inconsistent_file(db_session, tmp_path):
    broken = {**SEED_DATA, "dhabas": [{**SEED_DATA["dhabas"][0], "menu": [
        {"dish_id": "no-such-dish", "price_inr": 10, "is_signature": True}
    ]}]}
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(broken))

    with pytest.raises(ValueError, match="no-such-dish"):
        seed(db_session, path=path)
    assert db_session.query(Route).count() == 0  # validated before writing anything


# ---- what gets loaded ----

def test_bus_and_todays_trip(db_session):
    seed(db_session)
    bus = db_session.query(Bus).filter(Bus.bus_number_key == "UK07PA1187").one()

    assert bus.bus_number == "UK07 PA 1187"
    assert bus.route.code == "DL-234"
    trip = bus.trips[0]
    assert trip.current_delay_minutes == 15
    departure = trip.departure_time.replace(tzinfo=trip.departure_time.tzinfo or timezone.utc)
    assert departure.astimezone(IST).time().isoformat() == "08:00:00"
    assert departure.astimezone(IST).date() == datetime.now(IST).date()


def test_menu_item_takes_dish_details_and_dhaba_price(db_session):
    seed(db_session)
    dhaba = db_session.query(Dhaba).filter(Dhaba.slug == "ddn-punjabi-rasoi").one()
    item = next(m for m in dhaba.menu_items if m.dish_id == "butter-chicken")
    dish = next(d for d in SEED_DATA["dishes"] if d["id"] == "butter-chicken")
    menu_entry = next(
        m for d in SEED_DATA["dhabas"] if d["slug"] == "ddn-punjabi-rasoi"
        for m in d["menu"] if m["dish_id"] == "butter-chicken"
    )

    assert (item.name, item.description, item.is_veg) == (dish["name"], dish["description"], dish["is_veg"])
    assert item.price_inr == menu_entry["price_inr"] != dish["base_price_inr"]
    assert item.image_url == "/static/dishes/butter-chicken.jpg"
    assert item.is_signature is True
    assert dhaba.stop.name == "Meerut" and dhaba.avg_prep_time_minutes == 18


def test_is_pure_veg_matches_the_seed_file(db_session):
    seed(db_session)
    expected = {d["slug"]: d["is_pure_veg"] for d in SEED_DATA["dhabas"]}

    actual = {d.slug: d.is_pure_veg for d in db_session.query(Dhaba)}
    assert actual == expected
    assert any(expected.values()) and not all(expected.values())


def test_ad_campaigns(db_session):
    seed(db_session)
    by_key = {(c.advertiser, c.placement): c for c in db_session.query(AdCampaign)}

    sponsored = [c for c in by_key.values() if c.placement == AdPlacement.SPONSORED_DHABA]
    assert len(sponsored) == sum(1 for d in SEED_DATA["dhabas"] if d["sponsored_offer"])
    assert all(c.dhaba is not None and c.headline == c.dhaba.sponsored_offer for c in sponsored)
    assert all(c.route_id == c.dhaba.stop.route_id for c in sponsored)

    water = by_key[("Pahadi Spring", AdPlacement.MENU_ADDON)]
    assert (water.addon_price_inr, water.route_id) == (20, None)
    assert by_key[("Bhujiawala & Sons", AdPlacement.MENU_ADDON)].addon_price_inr == 45
    assert by_key[("SafarCover", AdPlacement.TRIP_BANNER)].addon_price_inr is None

    # Stats from ads.campaigns, including rows the brand-ad rules don't produce.
    for stats in SEED_DATA["ads"]["campaigns"]:
        campaign = by_key[(stats["advertiser"], AdPlacement(stats["placement"]))]
        assert (campaign.views, campaign.taps, campaign.spend_inr) == (
            stats["views"], stats["taps"], stats["spend_inr"]
        )
    assert by_key[("Pahadi Spring", AdPlacement.ORDER_WAIT)].status == AdStatus.PAUSED
    assert by_key[("Bhujiawala & Sons", AdPlacement.TRIP_BANNER)].headline == "Snacks for the long stretch"


# ---- demo users and passwords ----

def test_passenger_and_dhaba_users_use_seed_file_passwords(db_session):
    seed(db_session)
    passenger, dhaba_user = _demo_user("passenger"), _demo_user("dhaba")

    assert verify_password(passenger["password"], _user(db_session, passenger["phone"]).hashed_password)
    user = _user(db_session, dhaba_user["phone"])
    assert verify_password(dhaba_user["password"], user.hashed_password)
    assert user.role == UserRole.DHABA
    assert user.dhaba.slug == "ddn-punjabi-rasoi"


def test_committed_seed_file_has_no_admin():
    assert [u["role"] for u in SEED_DATA["demo_users"]] == ["passenger", "dhaba"]
    assert settings.admin_phone not in json.dumps(SEED_DATA)


def test_admin_comes_from_settings(db_session, monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "s3cret-admin")
    seed(db_session)
    admin = _user(db_session, settings.admin_phone)

    assert (admin.role, admin.name) == (UserRole.ADMIN, settings.admin_name)
    assert verify_password("s3cret-admin", admin.hashed_password)


def test_admin_entry_in_another_seed_file_is_ignored(db_session, tmp_path, monkeypatch, capsys):
    # e.g. the original kit export, which still lists an admin with a password
    with_admin = {**SEED_DATA, "demo_users": SEED_DATA["demo_users"] + [
        {"name": "File Admin", "phone": "9111111111", "password": "from-the-file", "role": "admin"},
    ]}
    path = tmp_path / "with_admin.json"
    path.write_text(json.dumps(with_admin))
    monkeypatch.setattr(settings, "admin_password", "s3cret-admin")

    seed(db_session, path=path)

    assert db_session.query(User).filter(User.phone == "9111111111").first() is None
    assert verify_password("s3cret-admin", _user(db_session, settings.admin_phone).hashed_password)
    assert "ignoring the admin entry" in capsys.readouterr().out


def test_admin_password_is_random_and_printed_once_when_unset(db_session, capsys):
    seed(db_session)
    admin = _user(db_session, settings.admin_phone)
    hashed = admin.hashed_password
    admin_line = next(line for line in capsys.readouterr().out.splitlines() if "admin:" in line)
    generated = admin_line.split("password='")[1].split("'")[0]
    assert verify_password(generated, hashed)

    seed(db_session)  # no ADMIN_PASSWORD on re-run: keep it, don't print a new one

    assert admin.hashed_password == hashed
    assert "password='" not in capsys.readouterr().out


def test_reseed_updates_admin_password_when_env_changes(db_session, monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "first-password")
    seed(db_session)
    monkeypatch.setattr(settings, "admin_password", "second-password")
    seed(db_session)

    assert db_session.query(User).filter(User.role == UserRole.ADMIN).count() == 1
    assert verify_password("second-password", _user(db_session, settings.admin_phone).hashed_password)


def test_older_accounts_are_kept_and_old_admin_loses_demo_password(db_session):
    # As left by the previous hard-coded seed, before ADMIN_PASSWORD existed.
    db_session.add_all([
        User(phone="9876543211", name="Rajesh", role=UserRole.DHABA, hashed_password=hash_password("password123")),
        User(phone="9876543212", name="Admin", role=UserRole.ADMIN, hashed_password=hash_password("password123")),
        User(phone="9876543213", name="Ops", role=UserRole.ADMIN, hashed_password=hash_password("own-strong-pw")),
    ])
    db_session.commit()

    seed(db_session)

    assert db_session.query(User).count() == 6
    assert verify_password("password123", _user(db_session, "9876543211").hashed_password)
    assert not verify_password("password123", _user(db_session, "9876543212").hashed_password)
    assert verify_password("own-strong-pw", _user(db_session, "9876543213").hashed_password)


def test_older_admin_gets_admin_password_when_set(db_session, monkeypatch):
    db_session.add(User(phone="9876543212", name="Admin", role=UserRole.ADMIN,
                        hashed_password=hash_password("password123")))
    db_session.commit()
    monkeypatch.setattr(settings, "admin_password", "s3cret-admin")

    seed(db_session)

    assert verify_password("s3cret-admin", _user(db_session, "9876543212").hashed_password)
