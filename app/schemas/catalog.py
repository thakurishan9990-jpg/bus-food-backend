"""Response models for the passenger browsing endpoints (routes, buses, stops, dhabas, menus, search, ads).

Times are returned in IST (+05:30), since every timetable is local.
"""
from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_serializer

from app.models.ad_campaign import AdArt, AdPlacement
from app.services.bus_service import IST
from app.services.catalog_service import Diet
from app.services.eta_service import as_aware_utc


class IstTimesModel(BaseModel):
    """Serializes every datetime field in IST, with its offset.

    Naive values (SQLite drops tzinfo) are UTC, as everything the app writes is.
    """

    @field_serializer("*", when_used="json", check_fields=False)
    def _to_ist(self, value):
        return as_aware_utc(value).astimezone(IST) if isinstance(value, datetime) else value


class RouteSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    slug: str
    name: str
    origin: str
    destination: str
    highway: str | None
    operator: str | None
    duration: str | None
    bus_count: int
    stop_count: int
    dhaba_count: int


class BusSummary(IstTimesModel):
    id: int
    bus_number: str
    bus_number_key: str
    route_code: str
    departs: time
    departure_time: datetime
    delay_minutes: int
    bus_type: str | None
    operator: str
    # Today's Trip, if one exists yet (it's created when the first order is placed).
    trip_id: int | None


class BusLookup(BaseModel):
    bus: BusSummary
    route: RouteSummary


class StopTiming(IstTimesModel):
    stop_id: int
    sequence: int
    name: str
    minutes_from_departure: int
    halt_minutes: int
    scheduled: datetime
    expected_arrival: datetime
    # min(arrival - prep - buffer) over the stop's live dhabas; None if it has none.
    order_cutoff: datetime | None
    ordering_open: bool
    dhaba_count: int
    dhaba_count_for_diet: int
    has_offer: bool
    offer_dhaba_name: str | None
    # Card images and cuisine labels of the dhabas shown for the diet, sponsored first.
    face_images: list[str]
    cuisines: list[str]


class BusStops(BaseModel):
    bus: BusSummary
    diet: Diet
    stops: list[StopTiming]


class MenuItemListing(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dish_id: str | None
    name: str
    description: str | None
    price_inr: int
    is_veg: bool
    image_url: str | None
    is_signature: bool


class DhabaListing(BaseModel):
    id: int
    slug: str | None
    name: str
    stop_id: int
    stop_name: str
    route_code: str | None
    cuisine: str | None
    cuisine_label: str | None
    rating: float | None
    review_count: int
    review_summary: str | None
    avg_bill_inr: int | None
    prep_minutes: int
    is_sponsored: bool
    sponsored_offer: str | None
    is_pure_veg: bool
    face_image: str | None
    # Up to two more dish images for the card's thumbnails.
    preview_images: list[str]
    matching_item_count: int


class MenuCounts(BaseModel):
    all: int
    veg: int
    nonveg: int


class AdItem(BaseModel):
    """One ad slot. `id` is the campaign to report views and taps against."""

    id: int
    placement: AdPlacement
    advertiser: str
    headline: str
    detail: str | None
    cta: str | None
    art: AdArt | None
    color_from: str | None
    color_to: str | None
    addon_item_name: str | None
    addon_price_inr: int | None
    # Set for sponsored-dhaba items, so the card can open that dhaba.
    dhaba_slug: str | None = None
    dhaba_name: str | None = None
    stop_id: int | None = None
    stop_name: str | None = None
    rating: float | None = None
    image_url: str | None = None


class AppConfig(BaseModel):
    convenience_fee_inr: int
    order_cutoff_buffer_minutes: int
    ready_before_arrival_minutes: int
    cuisines: dict[str, str]


class DhabaMenu(BaseModel):
    dhaba: DhabaListing
    diet: Diet
    items: list[MenuItemListing]
    counts: MenuCounts
    empty_reason: Literal["pure_veg", "no_veg"] | None
    addon: AdItem | None


class SearchResult(BaseModel):
    dhaba: DhabaListing
    matched_item: MenuItemListing | None


class SearchResponse(BaseModel):
    total: int
    results: list[SearchResult]
