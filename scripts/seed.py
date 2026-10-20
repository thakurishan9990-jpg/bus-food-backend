"""Seed the database from the prototype's demo export (data/dhabago_seed.json).

Idempotent: every row is upserted by a natural key, so re-running updates rather
than duplicates:

    route (code) · stop (route, sequence) · bus (bus_number_key) · today's trip (bus, IST date)
    dhaba (slug) · menu item (dhaba, dish_id) · ad campaign (advertiser, placement, route)
    user (phone)

Operational state is only set when a row is first created, so re-seeding never
undoes what admins, kitchens or passengers have done since: dhaba status, bus
is_active, menu item availability, a trip's reported delay, and ad campaign
status/views/taps/spend.

Passwords: the passenger and dhaba demo users use the passwords in the seed file.
The admin is not in the seed file: it is ADMIN_PHONE / ADMIN_NAME with ADMIN_PASSWORD,
or one random password generated and printed for this run when that's unset. An
admin entry in a seed file is ignored. Rows not in the seed file (e.g. older demo
users and their orders) are left untouched.

Usage:
    python -m scripts.seed [--file data/dhabago_seed.json]
"""
import argparse
import json
import secrets
from datetime import time
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.ad_campaign import AdArt, AdCampaign, AdPlacement, AdStatus
from app.models.bus import Bus, normalize_bus_number
from app.models.dhaba import Dhaba, DhabaStatus, MenuItem
from app.models.route import Route
from app.models.stop import Stop
from app.models.user import User, UserRole
from app.services.bus_service import get_or_create_todays_trip
from app.utils.auth import hash_password, verify_password

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SEED_FILE = REPO_ROOT / "data" / "dhabago_seed.json"

# Sponsored-dhaba creative, matching the prototype's promoAd().
SPONSORED_CTA = "See menu"
SPONSORED_COLORS = ("#14362E", "#2C6353")


def load_seed_file(path: str | Path = DEFAULT_SEED_FILE) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _validate(data: dict) -> None:
    """Fail before writing anything if the file references something it doesn't define."""
    dish_ids = {dish["id"] for dish in data["dishes"]}
    stop_keys = {(route["code"], stop["sequence"]) for route in data["routes"] for stop in route["stops"]}
    problems = []
    for dhaba in data["dhabas"]:
        if (dhaba["route_code"], dhaba["stop_sequence"]) not in stop_keys:
            problems.append(f"{dhaba['slug']}: no stop {dhaba['stop_sequence']} on {dhaba['route_code']}")
        if dhaba["cuisine"] not in data["cuisines"]:
            problems.append(f"{dhaba['slug']}: unknown cuisine {dhaba['cuisine']!r}")
        problems += [
            f"{dhaba['slug']}: unknown dish {item['dish_id']!r}"
            for item in dhaba["menu"] if item["dish_id"] not in dish_ids
        ]
    for user in data["demo_users"]:
        if user.get("dhaba_slug") and user["dhaba_slug"] not in {d["slug"] for d in data["dhabas"]}:
            problems.append(f"user {user['phone']}: unknown dhaba {user['dhaba_slug']!r}")
    if problems:
        raise ValueError("Seed file is inconsistent:\n  " + "\n  ".join(problems))


def _upsert(db: Session, existing: dict, key, model, fields: dict, on_create: dict | None = None):
    """Update the row at `key` in `existing`, or create it (with `on_create` extras). Returns (row, created)."""
    row = existing.get(key)
    if row is None:
        row = model(**fields, **(on_create or {}))
        db.add(row)
        existing[key] = row
        return row, True
    for field, value in fields.items():
        setattr(row, field, value)
    return row, False


def _seed_routes_stops_buses(db: Session, data: dict) -> tuple[dict, dict]:
    routes = {r.code: r for r in db.query(Route).filter(Route.code.isnot(None))}
    for r in data["routes"]:
        _upsert(db, routes, r["code"], Route, {
            "code": r["code"], "slug": r["slug"],
            "name": f"{r['origin']} → {r['destination']}",
            "origin": r["origin"], "destination": r["destination"],
            "highway": r["highway"], "operator": r["operator"], "duration": r["duration"],
        })
    db.flush()

    stops = {(s.route_id, s.sequence_order): s for s in db.query(Stop)}
    buses = {b.bus_number_key: b for b in db.query(Bus)}
    stops_by_code: dict[tuple[str, int], Stop] = {}
    seeded_buses: list[tuple[Bus, dict]] = []
    for r in data["routes"]:
        route = routes[r["code"]]
        for s in r["stops"]:
            stop, _ = _upsert(db, stops, (route.id, s["sequence"]), Stop, {
                "route_id": route.id, "sequence_order": s["sequence"], "name": s["name"],
                "minutes_from_origin": s["minutes_from_departure"],
                "halt_duration_minutes": s["halt_minutes"],
            })
            stops_by_code[(r["code"], s["sequence"])] = stop
        for b in r["buses"]:
            bus, _ = _upsert(db, buses, normalize_bus_number(b["bus_number"]), Bus, {
                "route_id": route.id, "bus_number": b["bus_number"],
                "departs": time.fromisoformat(b["departs"]),
                "bus_type": b["bus_type"], "operator": b["operator"],
            }, on_create={"is_active": True})
            seeded_buses.append((bus, b))
    db.flush()

    for bus, b in seeded_buses:
        trip = get_or_create_todays_trip(db, bus, delay_minutes=b["delay_minutes"])
        trip.route_id, trip.operator, trip.bus_number = bus.route_id, bus.operator, bus.bus_number
    return routes, stops_by_code


def _seed_dhabas_and_menus(db: Session, data: dict, stops_by_code: dict) -> dict[str, Dhaba]:
    dishes = {dish["id"]: dish for dish in data["dishes"]}
    dhabas = {d.slug: d for d in db.query(Dhaba).filter(Dhaba.slug.isnot(None))}
    for d in data["dhabas"]:
        _upsert(db, dhabas, d["slug"], Dhaba, {
            "slug": d["slug"], "name": d["name"],
            "stop_id": stops_by_code[(d["route_code"], d["stop_sequence"])].id,
            "cuisine": d["cuisine"], "avg_prep_time_minutes": d["prep_minutes"],
            "rating": Decimal(str(d["rating"])), "review_count": d["review_count"],
            "avg_bill_inr": d["avg_bill_inr"], "review_summary": d["review_summary"],
            "commission_pct": d["commission_pct"], "sponsored_offer": d["sponsored_offer"],
        }, on_create={"status": DhabaStatus.ACTIVE})
    db.flush()

    items = {(m.dhaba_id, m.dish_id): m for m in db.query(MenuItem).filter(MenuItem.dish_id.isnot(None))}
    for d in data["dhabas"]:
        dhaba = dhabas[d["slug"]]
        for entry in d["menu"]:
            dish = dishes[entry["dish_id"]]
            # Name, description and veg flag are the dish's; the price is this dhaba's.
            _upsert(db, items, (dhaba.id, dish["id"]), MenuItem, {
                "dhaba_id": dhaba.id, "dish_id": dish["id"], "name": dish["name"],
                "description": dish["description"], "is_veg": dish["is_veg"],
                "price_inr": entry["price_inr"], "image_url": dish["image"],
                "is_signature": entry["is_signature"],
            }, on_create={"is_available": True})
    db.flush()
    return dhabas


def _seed_ad_campaigns(db: Session, data: dict, routes: dict, dhabas: dict) -> list[AdCampaign]:
    campaigns = {(c.advertiser, c.placement, c.route_id): c for c in db.query(AdCampaign)}
    created: set[int] = set()

    def upsert(fields: dict) -> AdCampaign:
        campaign, was_created = _upsert(
            db, campaigns, (fields["advertiser"], fields["placement"], fields["route_id"]), AdCampaign, fields
        )
        if was_created:
            created.add(id(campaign))
        return campaign

    route_by_slug = {r.slug: r for r in routes.values()}
    route_by_code = routes
    for d in data["dhabas"]:
        if d["sponsored_offer"]:
            upsert({
                "advertiser": d["name"], "placement": AdPlacement.SPONSORED_DHABA,
                "route_id": route_by_code[d["route_code"]].id, "dhaba_id": dhabas[d["slug"]].id,
                "headline": d["sponsored_offer"], "detail": None, "cta": SPONSORED_CTA, "art": None,
                "color_from": SPONSORED_COLORS[0], "color_to": SPONSORED_COLORS[1],
                "addon_price_inr": None, "addon_item_name": None,
            })

    def brand_fields(ad: dict, placement: AdPlacement) -> dict:
        is_addon = placement == AdPlacement.MENU_ADDON
        return {
            "advertiser": ad["advertiser"], "placement": placement, "route_id": None, "dhaba_id": None,
            "headline": ad["headline"], "detail": ad["detail"], "cta": ad["cta"],
            "art": AdArt(ad["art"]) if ad["art"] else None,
            "color_from": ad["color_from"], "color_to": ad["color_to"],
            "addon_price_inr": ad["addon_price_inr"] if is_addon else None,
            "addon_item_name": ad["addon_item_name"] if is_addon else None,
        }

    brand_ads = data["ads"]["brand_ads"]
    for ad in brand_ads:
        if ad["addon_price_inr"] is not None:
            upsert(brand_fields(ad, AdPlacement.MENU_ADDON))
        if ad["key"] == "cover":
            upsert(brand_fields(ad, AdPlacement.TRIP_BANNER))

    # Stats rows may name an (advertiser, placement) the rules above didn't produce
    # (e.g. a brand also bought the trip banner); those reuse the brand's creative.
    brand_by_advertiser = {ad["advertiser"]: ad for ad in brand_ads}
    for stats in data["ads"]["campaigns"]:
        placement = AdPlacement(stats["placement"])
        route = route_by_slug[stats["route_slug"]] if stats["route_slug"] else None
        key = (stats["advertiser"], placement, route.id if route else None)
        campaign = campaigns.get(key)
        if campaign is None:
            ad = brand_by_advertiser.get(stats["advertiser"])
            if ad is None:
                raise ValueError(f"Campaign stats for {key} match no dhaba or brand ad")
            campaign = upsert({**brand_fields(ad, placement), "route_id": key[2]})
        if id(campaign) in created:
            campaign.views, campaign.taps = stats["views"], stats["taps"]
            campaign.spend_inr, campaign.status = stats["spend_inr"], AdStatus(stats["status"])
    db.flush()
    return list(campaigns.values())


def _seed_users(db: Session, data: dict, dhabas: dict) -> list[str]:
    """Upsert the demo users. Returns lines for the summary (never containing a seed-file password)."""
    demo_passwords = {settings.seed_user_password} | {u["password"] for u in data["demo_users"]}
    generated_password: str | None = None

    def admin_password_for(user: User | None) -> str | None:
        """The password an admin should get, or None to leave it as is."""
        nonlocal generated_password
        if settings.admin_password:
            return settings.admin_password
        if user is not None and not any(verify_password(p, user.hashed_password) for p in demo_passwords):
            return None  # already has a non-demo password; don't rotate it on every run
        generated_password = generated_password or secrets.token_urlsafe(12)
        return generated_password

    # The admin comes from settings, never from the file.
    file_users = [u for u in data["demo_users"] if u["role"] != UserRole.ADMIN.value]
    if len(file_users) < len(data["demo_users"]):
        print("  Note: ignoring the admin entry in the seed file; the admin comes from ADMIN_PHONE/ADMIN_PASSWORD.")
    users = file_users + [
        {"phone": settings.admin_phone, "name": settings.admin_name, "role": UserRole.ADMIN.value},
    ]

    lines = []
    for u in users:
        role = UserRole(u["role"])
        user = db.query(User).filter(User.phone == u["phone"]).first()
        if role == UserRole.ADMIN:
            password = admin_password_for(user)
        else:
            password = u["password"]
        dhaba_id = dhabas[u["dhaba_slug"]].id if u.get("dhaba_slug") else None
        if user is None:
            user = User(phone=u["phone"], name=u["name"], role=role, dhaba_id=dhaba_id,
                        hashed_password=hash_password(password))
            db.add(user)
        else:
            user.name, user.role, user.dhaba_id = u["name"], role, dhaba_id
            if password is not None:
                user.hashed_password = hash_password(password)
        lines.append((role, user))
    db.flush()

    # Any other admin (e.g. from the old hard-coded seed) gets the same treatment,
    # so no admin is left with a shared demo password.
    seeded_phones = {u["phone"] for u in users}
    for user in db.query(User).filter(User.role == UserRole.ADMIN, User.phone.notin_(seeded_phones)):
        password = admin_password_for(user)
        if password is not None:
            user.hashed_password = hash_password(password)
            lines.append((UserRole.ADMIN, user))

    summary = []
    for role, user in lines:
        line = f"    {role.value}: phone={user.phone} name={user.name}"
        if role != UserRole.ADMIN:
            line += " password=<from seed file>"
        elif settings.admin_password:
            line += " password=<from ADMIN_PASSWORD>"
        elif generated_password and verify_password(generated_password, user.hashed_password):
            line += f" password='{generated_password}' (generated; set ADMIN_PASSWORD to choose one)"
        else:
            line += " password=<unchanged>"
        summary.append(line)
    return summary


def seed(db: Session | None = None, path: str | Path = DEFAULT_SEED_FILE) -> dict[str, int]:
    """Seed (or, on re-run, update) everything in the seed file. Returns the seeded row counts.

    Pass an existing `db` (e.g. a test session) to seed into it directly; the
    caller then owns its lifecycle. With no argument, opens and closes its own
    SessionLocal, for CLI use.
    """
    data = load_seed_file(path)
    _validate(data)

    owns_session = db is None
    if db is None:
        db = SessionLocal()
    try:
        routes, stops_by_code = _seed_routes_stops_buses(db, data)
        dhabas = _seed_dhabas_and_menus(db, data, stops_by_code)
        campaigns = _seed_ad_campaigns(db, data, routes, dhabas)
        user_lines = _seed_users(db, data, dhabas)
        db.commit()

        route_ids = [r.id for r in routes.values()]
        counts = {
            "routes": len(routes),
            "buses": db.query(Bus).filter(Bus.route_id.in_(route_ids)).count(),
            "stops": db.query(Stop).filter(Stop.route_id.in_(route_ids)).count(),
            "dhabas": len(dhabas),
            "menu_items": db.query(MenuItem).filter(MenuItem.dhaba_id.in_([d.id for d in dhabas.values()])).count(),
            "ad_campaigns": len(campaigns),
        }
        expected = data["meta"]["counts"]
        print(f"Seed complete from {Path(path).name}:")
        for name, count in counts.items():
            check = ""
            if name in expected:
                check = "  ok" if count == expected[name] else f"  MISMATCH: seed file says {expected[name]}"
            print(f"  {name:<13}{count:>5}{check}")
        print("  Demo users:")
        print("\n".join(user_lines))
        return counts
    finally:
        if owns_session:
            db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--file", default=str(DEFAULT_SEED_FILE), help="seed JSON (default: %(default)s)")
    seed(path=parser.parse_args().file)


if __name__ == "__main__":
    main()
