from fastapi import APIRouter, Depends, Query
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.ad_campaign import AdCampaign, AdPlacement, AdStatus
from app.models.dhaba import Dhaba, DhabaStatus
from app.models.route import Route
from app.models.stop import Stop
from app.schemas.catalog import AdItem
from app.services.catalog_service import listed_routes
from app.services.listing_service import ad_item, live_campaigns
from app.utils.errors import NotFoundError

router = APIRouter(tags=["passenger"])


def _sponsored_dhaba_campaigns(db: Session, route_id: int) -> list[AdCampaign]:
    """Live sponsored-dhaba campaigns on a route whose dhaba is still live, in stop order."""
    return (
        live_campaigns(db, AdPlacement.SPONSORED_DHABA, route_id)
        .join(AdCampaign.dhaba)
        .join(Dhaba.stop)
        .filter(Dhaba.status == DhabaStatus.ACTIVE, Dhaba.sponsored_offer.isnot(None))
        .order_by(None)
        .order_by(Stop.sequence_order, Dhaba.rating.desc(), AdCampaign.id)
        .all()
    )


@router.get("/ads", response_model=list[AdItem])
def list_ads(
    placement: AdPlacement,
    route: str | None = Query(None, description="Route code; without it only all-route campaigns are returned"),
    db: Session = Depends(get_db),
) -> list[AdItem]:
    """Live campaigns for a placement, including ones that run on every route. Public.

    For trip_banner the route's sponsored dhabas are included as banner items too,
    with brand banners slotted between them as in the passenger app.
    """
    route_id = None
    if route is not None:
        route_row = listed_routes(db).filter(Route.code == route).first()
        if route_row is None:
            raise NotFoundError(f"Route {route} not found")
        route_id = route_row.id

    if placement == AdPlacement.SPONSORED_DHABA:
        campaigns = _sponsored_dhaba_campaigns(db, route_id) if route_id is not None else []
    else:
        campaigns = live_campaigns(db, placement, route_id).all()

    if placement == AdPlacement.TRIP_BANNER and route_id is not None:
        banner = _sponsored_dhaba_campaigns(db, route_id)
        for i, brand in enumerate(campaigns):
            banner.insert(min(len(banner), 1 + i * 2), brand)
        campaigns = banner
    return [ad_item(c) for c in campaigns]


def _bump(db: Session, campaign_id: int, column) -> None:
    # A single UPDATE, so concurrent views/taps can't overwrite each other's increments.
    result = db.execute(
        update(AdCampaign)
        .where(AdCampaign.id == campaign_id, AdCampaign.status == AdStatus.LIVE)
        .values({column: column + 1})
    )
    if result.rowcount == 0:
        raise NotFoundError(f"No live campaign {campaign_id}")
    db.commit()


@router.post("/ads/{campaign_id}/view", status_code=204)
def record_view(campaign_id: int, db: Session = Depends(get_db)) -> None:
    """Count one impression of a live campaign. Public; call once per ad shown."""
    _bump(db, campaign_id, AdCampaign.views)


@router.post("/ads/{campaign_id}/tap", status_code=204)
def record_tap(campaign_id: int, db: Session = Depends(get_db)) -> None:
    """Count one tap on a live campaign's call to action. Public."""
    _bump(db, campaign_id, AdCampaign.taps)
