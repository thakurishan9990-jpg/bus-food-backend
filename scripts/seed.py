"""Seed the database with the NH-334 (Delhi -> Dehradun) demo route.

Idempotent: re-running updates existing rows (matched by a natural key) instead
of duplicating them, so this is safe to run repeatedly (e.g. on every deploy).

Usage:
    python -m scripts.seed
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.dhaba import Dhaba, MenuItem
from app.models.route import Route
from app.models.stop import Stop
from app.models.trip import Trip, TripStatus
from app.models.user import User, UserRole
from app.utils.auth import hash_password

IST = ZoneInfo("Asia/Kolkata")

ROUTE_NAME = "Delhi ISBT Kashmere Gate -> Dehradun ISBT"

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

DEPARTURE_HOURS = [6, 10, 14, 18]
DAYS_AHEAD = 7
BUS_NUMBER_START = 1234
OPERATOR = "UPSRTC"


def _get_or_create_route(db, name: str, origin: str, destination: str) -> Route:
    route = db.query(Route).filter(Route.name == name).first()
    if route is None:
        route = Route(name=name, origin=origin, destination=destination)
        db.add(route)
        db.flush()
    else:
        route.origin = origin
        route.destination = destination
    return route


def _get_or_create_stop(
    db, route: Route, name: str, lat: float, lng: float,
    sequence_order: int, minutes_from_origin: int, halt_duration_minutes: int,
) -> Stop:
    stop = db.query(Stop).filter(Stop.route_id == route.id, Stop.name == name).first()
    if stop is None:
        stop = Stop(
            route_id=route.id, name=name, lat=lat, lng=lng,
            sequence_order=sequence_order, minutes_from_origin=minutes_from_origin,
            halt_duration_minutes=halt_duration_minutes,
        )
        db.add(stop)
        db.flush()
    else:
        stop.lat = lat
        stop.lng = lng
        stop.sequence_order = sequence_order
        stop.minutes_from_origin = minutes_from_origin
        stop.halt_duration_minutes = halt_duration_minutes
    return stop


def _get_or_create_dhaba(db, stop: Stop, name: str, avg_prep_time_minutes: int) -> Dhaba:
    dhaba = db.query(Dhaba).filter(Dhaba.stop_id == stop.id, Dhaba.name == name).first()
    if dhaba is None:
        dhaba = Dhaba(stop_id=stop.id, name=name, avg_prep_time_minutes=avg_prep_time_minutes, is_active=True)
        db.add(dhaba)
        db.flush()
    else:
        dhaba.avg_prep_time_minutes = avg_prep_time_minutes
        dhaba.is_active = True
    return dhaba


def _get_or_create_menu_item(db, dhaba: Dhaba, name: str, price: int, is_veg: bool) -> MenuItem:
    item = db.query(MenuItem).filter(MenuItem.dhaba_id == dhaba.id, MenuItem.name == name).first()
    if item is None:
        item = MenuItem(dhaba_id=dhaba.id, name=name, price=price, is_veg=is_veg)
        db.add(item)
        db.flush()
    else:
        item.price = price
        item.is_veg = is_veg
    return item


def _get_or_create_user(
    db, phone: str, name: str, role: UserRole, dhaba_id: int | None, password: str
) -> User:
    user = db.query(User).filter(User.phone == phone).first()
    if user is None:
        user = User(
            phone=phone, name=name, hashed_password=hash_password(password),
            role=role, dhaba_id=dhaba_id,
        )
        db.add(user)
        db.flush()
    else:
        user.name = name
        user.role = role
        user.dhaba_id = dhaba_id
        user.hashed_password = hash_password(password)
    return user


def _trip_status_for(departure_time: datetime, now: datetime) -> TripStatus:
    if departure_time > now:
        return TripStatus.SCHEDULED
    if now - departure_time <= timedelta(hours=3):
        return TripStatus.IN_TRANSIT
    return TripStatus.COMPLETED


def _get_or_create_trip(
    db, route: Route, bus_number: str, departure_time: datetime, status: TripStatus
) -> Trip:
    trip = db.query(Trip).filter(Trip.bus_number == bus_number).first()
    if trip is None:
        trip = Trip(
            route_id=route.id, operator=OPERATOR, bus_number=bus_number,
            departure_time=departure_time, current_delay_minutes=0, status=status,
        )
        db.add(trip)
        db.flush()
    else:
        trip.route_id = route.id
        trip.departure_time = departure_time
        trip.status = status
    return trip


def seed(db: Session | None = None) -> None:
    """Seed (or, on re-run, update) the demo route/stops/dhabas/menu/users/trips.

    Pass an existing `db` (e.g. a test session) to seed into it directly; the
    caller then owns its lifecycle. With no argument, opens and closes its own
    SessionLocal, for CLI use.
    """
    owns_session = db is None
    if db is None:
        db = SessionLocal()
    try:
        route = _get_or_create_route(
            db, ROUTE_NAME, "Delhi ISBT Kashmere Gate", "Dehradun ISBT"
        )

        stops_by_name: dict[str, Stop] = {}
        for name, lat, lng, sequence_order, minutes_from_origin, halt_duration_minutes in STOPS:
            stops_by_name[name] = _get_or_create_stop(
                db, route, name, lat, lng, sequence_order, minutes_from_origin, halt_duration_minutes
            )

        dhaba_by_name: dict[str, Dhaba] = {}
        for stop_name, dhabas in DHABAS_BY_STOP.items():
            stop = stops_by_name[stop_name]
            for dhaba_name, prep_time, menu_items in dhabas:
                dhaba = _get_or_create_dhaba(db, stop, dhaba_name, prep_time)
                dhaba_by_name[dhaba_name] = dhaba
                for item_name, price, is_veg in menu_items:
                    _get_or_create_menu_item(db, dhaba, item_name, price, is_veg)

        for phone, name, role, dhaba_name in SEED_USERS:
            _get_or_create_user(
                db, phone, name, role,
                dhaba_by_name[dhaba_name].id if dhaba_name else None,
                settings.seed_user_password,
            )

        now_ist = datetime.now(IST)
        now_utc = datetime.now(timezone.utc)
        today = now_ist.date()

        trips_created = []
        bus_index = 0
        for day_offset in range(DAYS_AHEAD):
            day = today + timedelta(days=day_offset)
            for hour in DEPARTURE_HOURS:
                departure_time = datetime(day.year, day.month, day.day, hour, 0, tzinfo=IST)
                bus_number = f"UP15-AB-{BUS_NUMBER_START + bus_index}"
                status = _trip_status_for(departure_time, now_utc)
                trip = _get_or_create_trip(db, route, bus_number, departure_time, status)
                trips_created.append(trip)
                bus_index += 1

        db.commit()

        print("Seed complete:")
        print(f"  Route: {route.name} (id={route.id})")
        print(f"  Trips: {len(trips_created)} departures across {DAYS_AHEAD} days")
        print(f"  Demo users (password='{settings.seed_user_password}'):")
        for phone, name, role, _ in SEED_USERS:
            print(f"    {role.value}: phone={phone} name={name}")
    finally:
        if owns_session:
            db.close()


if __name__ == "__main__":
    seed()
