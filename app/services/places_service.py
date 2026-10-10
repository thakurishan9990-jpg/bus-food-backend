from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.dhaba import Dhaba
from app.models.review_cache import ReviewCache
from app.services.gemini_service import summarize_reviews

PLACES_BASE_URL = "https://maps.googleapis.com/maps/api/place"
REQUEST_TIMEOUT = 8.0
CACHE_TTL_HOURS = 24


def search_place_id(query: str) -> str | None:
    """Text-search Google Places for a dhaba name + location, return its place_id.

    Used by scripts/fetch_place_ids.py to look up real place IDs for seed data.
    Returns None on any failure (missing key, network error, no results).
    """
    if not settings.google_places_api_key:
        return None
    try:
        resp = httpx.get(
            f"{PLACES_BASE_URL}/textsearch/json",
            params={"query": query, "key": settings.google_places_api_key},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[0]["place_id"] if results else None
    except (httpx.HTTPError, KeyError, IndexError):
        return None


def fetch_place_details(place_id: str) -> dict | None:
    """Fetch rating, review count, and raw reviews for a place.

    Returns None on any API failure so callers can fall back to cache/static data.
    Shape: {"rating": float, "total_reviews": int, "raw_reviews": [...]}
    """
    if not settings.google_places_api_key:
        return None
    try:
        resp = httpx.get(
            f"{PLACES_BASE_URL}/details/json",
            params={
                "place_id": place_id,
                "fields": "rating,user_ratings_total,reviews",
                "key": settings.google_places_api_key,
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        result = resp.json().get("result")
        if not result:
            return None
        return {
            "rating": result.get("rating", 0.0),
            "total_reviews": result.get("user_ratings_total", 0),
            "raw_reviews": result.get("reviews", []),
        }
    except (httpx.HTTPError, KeyError):
        return None


def get_or_refresh_reviews(db: Session, dhaba: Dhaba) -> ReviewCache | None:
    """Serve a dhaba's review cache if fresh (<24h), else refresh via Places + Gemini.

    On any API failure, falls back to the existing (possibly stale) cache row,
    or None if there's never been one — callers should treat None as "no reviews yet"
    rather than an error.
    """
    cache = dhaba.review_cache
    now = datetime.now(timezone.utc)

    if cache is not None and (now - cache.fetched_at) < timedelta(hours=CACHE_TTL_HOURS):
        return cache

    if not dhaba.google_place_id:
        return cache

    details = fetch_place_details(dhaba.google_place_id)
    if details is None:
        return cache

    summary = summarize_reviews(dhaba.name, details["raw_reviews"])

    if cache is not None:
        cache.rating = details["rating"]
        cache.total_reviews = details["total_reviews"]
        cache.raw_reviews = details["raw_reviews"]
        cache.ai_summary = summary
        cache.fetched_at = now
    else:
        cache = ReviewCache(
            dhaba_id=dhaba.id,
            rating=details["rating"],
            total_reviews=details["total_reviews"],
            raw_reviews=details["raw_reviews"],
            ai_summary=summary,
            fetched_at=now,
        )
        db.add(cache)

    db.commit()
    db.refresh(cache)
    return cache
