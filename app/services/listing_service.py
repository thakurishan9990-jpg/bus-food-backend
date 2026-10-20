"""Builds the passenger-facing response models from ORM rows."""
from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from app.models.ad_campaign import AdCampaign, AdPlacement, AdStatus
from app.models.dhaba import Dhaba
from app.models.review_cache import ReviewCache
from app.models.route import Route
from app.schemas.catalog import AdItem, BusSummary, DhabaListing, RouteSummary
from app.services.bus_service import BusRun
from app.services.catalog_service import Diet, cuisine_label, face_item, is_live, visible_items


def route_summary(route: Route) -> RouteSummary:
    return RouteSummary(
        id=route.id, code=route.code, slug=route.slug, name=route.name,
        origin=route.origin, destination=route.destination,
        highway=route.highway, operator=route.operator, duration=route.duration,
        bus_count=sum(1 for b in route.buses if b.is_active),
        stop_count=len(route.stops),
        dhaba_count=sum(1 for s in route.stops for d in s.dhabas if is_live(d)),
    )


def bus_summary(run: BusRun) -> BusSummary:
    bus = run.bus
    return BusSummary(
        id=bus.id, bus_number=bus.bus_number, bus_number_key=bus.bus_number_key,
        route_code=bus.route.code, departs=bus.departs, departure_time=run.departure_time,
        delay_minutes=run.delay_minutes, bus_type=bus.bus_type, operator=bus.operator,
        trip_id=run.trip.id if run.trip else None,
    )


def dhaba_listing(dhaba: Dhaba, diet: Diet, reviews: ReviewCache | None = None) -> DhabaListing:
    """A dhaba card. `reviews` (Google rating + AI summary) wins over the seeded values when present."""
    items = visible_items(dhaba, diet)
    face = face_item(dhaba, diet)
    previews = [m.image_url for m in items if m is not face and m.image_url][:2]
    return DhabaListing(
        id=dhaba.id, slug=dhaba.slug, name=dhaba.name,
        stop_id=dhaba.stop_id, stop_name=dhaba.stop.name, route_code=dhaba.stop.route.code,
        cuisine=dhaba.cuisine, cuisine_label=cuisine_label(dhaba),
        rating=float(reviews.rating) if reviews else (float(dhaba.rating) if dhaba.rating is not None else None),
        review_count=reviews.total_reviews if reviews else dhaba.review_count,
        review_summary=reviews.ai_summary if reviews else dhaba.review_summary,
        avg_bill_inr=dhaba.avg_bill_inr, prep_minutes=dhaba.avg_prep_time_minutes,
        is_sponsored=dhaba.sponsored_offer is not None, sponsored_offer=dhaba.sponsored_offer,
        is_pure_veg=dhaba.is_pure_veg,
        face_image=face.image_url if face else None,
        preview_images=previews,
        matching_item_count=len(items),
    )


def live_campaigns(db: Session, placement: AdPlacement, route_id: int | None) -> Query:
    """Live campaigns for a placement on a route, including those that run on every route."""
    route_filter = AdCampaign.route_id.is_(None)
    if route_id is not None:
        route_filter = or_(route_filter, AdCampaign.route_id == route_id)
    return (
        db.query(AdCampaign)
        .filter(AdCampaign.placement == placement, AdCampaign.status == AdStatus.LIVE, route_filter)
        .order_by(AdCampaign.id)
    )


def addon_for(db: Session, dhaba: Dhaba) -> AdCampaign | None:
    """One menu add-on for this dhaba's route, picked deterministically by dhaba id."""
    addons = live_campaigns(db, AdPlacement.MENU_ADDON, dhaba.stop.route_id).all()
    return addons[dhaba.id % len(addons)] if addons else None


def ad_item(campaign: AdCampaign) -> AdItem:
    item = AdItem(
        id=campaign.id, placement=campaign.placement, advertiser=campaign.advertiser,
        headline=campaign.headline, detail=campaign.detail, cta=campaign.cta, art=campaign.art,
        color_from=campaign.color_from, color_to=campaign.color_to,
        addon_item_name=campaign.addon_item_name, addon_price_inr=campaign.addon_price_inr,
    )
    if campaign.dhaba is not None:
        dhaba = campaign.dhaba
        item.dhaba_slug, item.dhaba_name = dhaba.slug, dhaba.name
        item.stop_id, item.stop_name = dhaba.stop_id, dhaba.stop.name
        item.rating = float(dhaba.rating) if dhaba.rating is not None else None
        face = face_item(dhaba, "all")
        item.image_url = face.image_url if face else None
    return item
