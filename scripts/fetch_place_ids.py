"""Look up real Google Place IDs for every seeded dhaba, by name + stop location.

Requires GOOGLE_PLACES_API_KEY to be set in .env. Run after scripts/seed.py.

Usage:
    python -m scripts.fetch_place_ids
"""
from app.database import SessionLocal
from app.models.dhaba import Dhaba
from app.services.places_service import search_place_id


def fetch_place_ids() -> None:
    db = SessionLocal()
    try:
        dhabas = db.query(Dhaba).all()
        if not dhabas:
            print("No dhabas found. Run `python -m scripts.seed` first.")
            return

        for dhaba in dhabas:
            stop = dhaba.stop
            query = f"{dhaba.name}, {stop.name}, Uttar Pradesh, India"
            place_id = search_place_id(query)
            if place_id:
                dhaba.google_place_id = place_id
                print(f"  {dhaba.name} ({stop.name}): {place_id}")
            else:
                print(f"  {dhaba.name} ({stop.name}): NOT FOUND (left unset)")

        db.commit()
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    fetch_place_ids()
