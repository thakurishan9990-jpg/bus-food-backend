"""Seed the database with the NH-334 (Delhi -> Dehradun) demo route.

Usage:
    python -m scripts.seed
"""
from datetime import datetime, timezone

from app.config import settings
from app.database import SessionLocal
from app.models.dhaba import Dhaba, MenuItem
from app.models.route import Route
from app.models.stop import Stop
from app.models.trip import Trip, TripStatus
from app.models.user import User, UserRole
from app.utils.auth import hash_password

STOPS = [
    # name, lat, lng, sequence_order, minutes_from_origin, halt_duration_minutes
    ("Meerut", 28.9845, 77.7064, 1, 30, 20),
    ("Khatauli", 29.2795, 77.7275, 2, 50, 10),
    ("Muzaffarnagar", 29.4727, 77.7085, 3, 70, 10),
    ("Roorkee", 29.8543, 77.8880, 4, 110, 10),
    ("Chhutmalpur", 29.9365, 77.8958, 5, 130, 5),
]

DHABAS_BY_STOP = {
    "Meerut": [
        ("Sharma Dhaba", 15, [
            ("Dal Makhani", 180, True), ("Paneer Butter Masala", 220, True),
            ("Tandoori Roti", 20, True), ("Lassi", 60, True),
        ]),
        ("Highway Express", 10, [
            ("Rajma Chawal", 150, True), ("Butter Chicken", 260, False),
            ("Egg Curry", 150, False), ("Aloo Paratha", 70, True), ("Chai", 20, True),
        ]),
    ],
    "Khatauli": [
        ("Khatauli Sweets & Dhaba", 12, [
            ("Chole Bhature", 120, True), ("Veg Thali", 160, True), ("Jalebi", 50, True),
        ]),
        ("Truckers Point", 15, [
            ("Chicken Curry", 240, False), ("Dal Fry", 120, True),
            ("Tandoori Roti", 20, True), ("Lassi", 60, True),
        ]),
    ],
    "Muzaffarnagar": [
        ("Muzaffarnagar Junction Dhaba", 10, [
            ("Veg Thali", 150, True), ("Paneer Tikka", 200, True), ("Butter Naan", 40, True),
        ]),
        ("New Highway Dhaba", 12, [
            ("Mutton Curry", 300, False), ("Rajma Chawal", 150, True), ("Chai", 20, True),
        ]),
        ("Jat Dhaba", 15, [
            ("Dal Makhani", 180, True), ("Chicken Biryani", 220, False),
            ("Raita", 40, True), ("Tandoori Roti", 20, True), ("Lassi", 60, True),
        ]),
    ],
    "Roorkee": [
        ("Roorkee Highway Dhaba", 10, [
            ("Aloo Paratha", 70, True), ("Egg Curry", 150, False), ("Chai", 20, True),
        ]),
        ("Ganga Dhaba", 12, [
            ("Veg Thali", 160, True), ("Butter Chicken", 260, False),
            ("Dal Fry", 120, True), ("Tandoori Roti", 20, True),
        ]),
    ],
    "Chhutmalpur": [
        ("Chhutmalpur Food Point", 10, [
            ("Rajma Chawal", 150, True), ("Chicken Curry", 240, False), ("Chai", 20, True),
        ]),
        ("Border Dhaba", 8, [
            ("Paneer Butter Masala", 220, True), ("Veg Thali", 150, True),
            ("Lassi", 60, True), ("Butter Naan", 40, True),
        ]),
    ],
}

SEED_USERS = [
    # phone, name, role, dhaba_name_for_lookup (None unless role=dhaba)
    ("9876543210", "Amit", UserRole.PASSENGER, None),
    ("9876543211", "Rajesh", UserRole.DHABA, "Sharma Dhaba"),
    ("9876543212", "Admin", UserRole.ADMIN, None),
]


def seed() -> None:
    db = SessionLocal()
    try:
        existing = db.query(Route).filter(Route.name == "Delhi ISBT Kashmere Gate -> Dehradun ISBT").first()
        if existing is not None:
            print("Already seeded (route exists). Skipping.")
            return

        route = Route(
            name="Delhi ISBT Kashmere Gate -> Dehradun ISBT",
            origin="Delhi ISBT Kashmere Gate",
            destination="Dehradun ISBT",
        )
        db.add(route)
        db.flush()

        stops_by_name: dict[str, Stop] = {}
        for name, lat, lng, sequence_order, minutes_from_origin, halt_duration_minutes in STOPS:
            stop = Stop(
                route_id=route.id,
                name=name,
                lat=lat,
                lng=lng,
                sequence_order=sequence_order,
                minutes_from_origin=minutes_from_origin,
                halt_duration_minutes=halt_duration_minutes,
            )
            db.add(stop)
            db.flush()
            stops_by_name[name] = stop

        dhaba_by_name: dict[str, Dhaba] = {}
        for stop_name, dhabas in DHABAS_BY_STOP.items():
            stop = stops_by_name[stop_name]
            for dhaba_name, prep_time, menu_items in dhabas:
                dhaba = Dhaba(
                    stop_id=stop.id,
                    name=dhaba_name,
                    avg_prep_time_minutes=prep_time,
                    is_active=True,
                )
                db.add(dhaba)
                db.flush()
                dhaba_by_name[dhaba_name] = dhaba
                for item_name, price, is_veg in menu_items:
                    db.add(MenuItem(dhaba_id=dhaba.id, name=item_name, price=price, is_veg=is_veg))

        trip = Trip(
            route_id=route.id,
            operator="UPSRTC",
            bus_number="UP15-AB-1234",
            departure_time=datetime.now(timezone.utc),
            current_delay_minutes=0,
            status=TripStatus.IN_TRANSIT,
        )
        db.add(trip)

        for phone, name, role, dhaba_name in SEED_USERS:
            db.add(
                User(
                    phone=phone,
                    name=name,
                    hashed_password=hash_password(settings.seed_user_password),
                    role=role,
                    dhaba_id=dhaba_by_name[dhaba_name].id if dhaba_name else None,
                )
            )

        db.commit()
        print("Seed complete:")
        print(f"  Route: {route.name} (id={route.id})")
        print(f"  Trip: {trip.bus_number} (id={trip.id})")
        print(f"  Demo users (password='{settings.seed_user_password}'):")
        for phone, name, role, _ in SEED_USERS:
            print(f"    {role.value}: phone={phone} name={name}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
