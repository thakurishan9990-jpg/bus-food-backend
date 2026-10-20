"""Passenger-facing catalogue rules shared by the stop, menu, search and bus endpoints.

These mirror the approved prototype (dhabago_prototype.html, kept outside the repo):
diet filtering, which dhabas a diet hides, the dish shown on a dhaba's card,
sponsored-first ordering, and a stop's order cut-off.
"""
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy.orm import Query, Session, selectinload

from app.config import settings
from app.models.dhaba import Dhaba, DhabaStatus, MenuItem
from app.models.route import Route
from app.models.stop import Stop

Diet = Literal["all", "veg", "nonveg"]

# Labels for Dhaba.cuisine keys; the seed refuses a file whose `cuisines` differ.
CUISINE_LABELS: dict[str, str] = {
    "punjabi": "North Indian",
    "vaishno": "Pure veg",
    "paratha": "Paratha house",
    "south": "South Indian",
    "chinese": "Chinese",
    "chai": "Chai & snacks",
    "mughlai": "Mughlai",
    "rajasthani": "Rajasthani",
    "pahadi": "Pahadi",
    "mithai": "Sweets & chaat",
    "foodcourt": "Multi-cuisine",
}


def listed_routes(db: Session) -> Query:
    """Routes passengers can browse. Legacy pre-seed routes have no code and stay hidden."""
    return db.query(Route).filter(Route.code.isnot(None))


def dhabas_with_menus(db: Session) -> Query:
    return db.query(Dhaba).options(selectinload(Dhaba.menu_items), selectinload(Dhaba.stop))


def cuisine_label(dhaba: Dhaba) -> str | None:
    return CUISINE_LABELS.get(dhaba.cuisine, dhaba.cuisine) if dhaba.cuisine else None


def item_matches_diet(item: MenuItem, diet: Diet) -> bool:
    return diet == "all" or item.is_veg == (diet == "veg")


def visible_items(dhaba: Dhaba, diet: Diet) -> list[MenuItem]:
    """Available items matching the diet, in menu order."""
    return [m for m in sorted(dhaba.menu_items, key=lambda m: m.id) if m.is_available and item_matches_diet(m, diet)]


def shown_for_diet(dhaba: Dhaba, diet: Diet) -> bool:
    """veg hides dhabas with no veg items; nonveg hides those with none (so pure-veg dhabas disappear)."""
    return diet == "all" or bool(visible_items(dhaba, diet))


def face_item(dhaba: Dhaba, diet: Diet) -> MenuItem | None:
    """The dish on the dhaba's card: its signature if that fits the diet, else the first item that does."""
    signature = next((m for m in dhaba.menu_items if m.is_signature), None)
    if signature is not None and signature.is_available and item_matches_diet(signature, diet):
        return signature
    items = visible_items(dhaba, diet)
    return items[0] if items else signature


def is_live(dhaba: Dhaba) -> bool:
    return dhaba.status == DhabaStatus.ACTIVE


def sponsored_first(dhabas: list[Dhaba]) -> list[Dhaba]:
    """Sponsored listings pinned first, then by rating (highest first)."""
    return sorted(dhabas, key=lambda d: (d.sponsored_offer is None, -(d.rating or 0), d.name))


def stop_cutoff(expected_arrival: datetime, stop: Stop) -> datetime | None:
    """Latest time an order can be placed for this stop: min(arrival - prep - buffer) over its live dhabas.

    None when the stop has no live dhabas.
    """
    preps = [d.avg_prep_time_minutes for d in stop.dhabas if is_live(d)]
    if not preps:
        return None
    return expected_arrival - timedelta(minutes=max(preps) + settings.order_cutoff_buffer_minutes)
