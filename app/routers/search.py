from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models.dhaba import Dhaba, MenuItem
from app.models.route import Route
from app.models.stop import Stop
from app.schemas.catalog import MenuItemListing, SearchResponse, SearchResult
from app.services.catalog_service import (
    Diet, cuisine_label, dhabas_with_menus, is_live, listed_routes, shown_for_diet, sponsored_first, visible_items,
)
from app.services.listing_service import dhaba_listing
from app.utils.errors import BadRequestError, NotFoundError

router = APIRouter(tags=["passenger"])

MAX_RESULTS = 60


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query("", description="Dhaba, cuisine, stop, city, or dish"),
    scope: Literal["route", "all"] = "route",
    route: str | None = Query(None, description="Route code; required when scope=route"),
    diet: Diet = "all",
    min_rating: float | None = Query(None, ge=0, le=5),
    pure_veg: bool = False,
    max_avg_bill: int | None = Query(None, ge=0),
    max_prep: int | None = Query(None, ge=0),
    cuisine: list[str] = Query([], description="Cuisine keys; repeat the parameter or comma-separate"),
    db: Session = Depends(get_db),
) -> SearchResponse:
    """Search live dhabas, sponsored first, then by rating; at most 60 results. Public.

    Matches dhaba name, cuisine, stop name and route origin/destination; failing
    that, a dish name or description within the diet, returned as `matched_item`.
    """
    query = (
        dhabas_with_menus(db)
        .join(Dhaba.stop)
        .join(Stop.route)
        .filter(Route.id.in_(listed_routes(db).with_entities(Route.id)))
        .options(selectinload(Dhaba.stop).selectinload(Stop.route))
    )
    if scope == "route":
        if not route:
            raise BadRequestError("Pass route=<code> to search one route, or scope=all")
        if listed_routes(db).filter(Route.code == route).first() is None:
            raise NotFoundError(f"Route {route} not found")
        query = query.filter(Route.code == route)

    cuisines = {c.strip() for value in cuisine for c in value.split(",") if c.strip()}
    needle = q.strip().lower()
    results: list[tuple[Dhaba, MenuItem | None]] = []
    for dhaba in query.all():
        if not is_live(dhaba) or not shown_for_diet(dhaba, diet):
            continue
        if min_rating is not None and float(dhaba.rating or 0) < min_rating:
            continue
        if pure_veg and not dhaba.is_pure_veg:
            continue
        if max_avg_bill is not None and (dhaba.avg_bill_inr is None or dhaba.avg_bill_inr > max_avg_bill):
            continue
        if max_prep is not None and dhaba.avg_prep_time_minutes > max_prep:
            continue
        if cuisines and dhaba.cuisine not in cuisines:
            continue

        matched_item = None
        if needle:
            route_row = dhaba.stop.route
            text = " ".join(
                [dhaba.name, cuisine_label(dhaba) or "", dhaba.stop.name, route_row.origin, route_row.destination]
            ).lower()
            if needle not in text:
                matched_item = next(
                    (m for m in visible_items(dhaba, diet)
                     if needle in f"{m.name} {m.description or ''}".lower()),
                    None,
                )
                if matched_item is None:
                    continue
        results.append((dhaba, matched_item))

    by_dhaba = dict(results)
    ranked = sponsored_first(list(by_dhaba))
    return SearchResponse(
        total=len(ranked),
        results=[
            SearchResult(
                dhaba=dhaba_listing(d, diet),
                matched_item=MenuItemListing.model_validate(by_dhaba[d]) if by_dhaba[d] else None,
            )
            for d in ranked[:MAX_RESULTS]
        ],
    )
