from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.bus import Bus, normalize_bus_number
from app.models.stop import Stop
from app.models.trip import Trip, TripStatus
from app.services.eta_service import as_aware_utc
from app.utils.errors import NotFoundError

BUS_NOT_FOUND = "No bus found with that number. Check the number on your ticket, for example UK07 PA 1187."

# Bus timetables (Bus.departs) are local wall-clock times.
IST = ZoneInfo("Asia/Kolkata")


def departure_on(bus: Bus, day: date) -> datetime:
    """The bus's departure on an IST calendar day, as an aware UTC datetime.

    Stored as UTC because SQLite drops tzinfo on round-trip and eta_service
    reads naive datetimes back as UTC.
    """
    return datetime.combine(day, bus.departs, tzinfo=IST).astimezone(timezone.utc)


def _ist_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=IST).astimezone(timezone.utc)
    return start, start + timedelta(days=1)


def get_todays_trip(db: Session, bus: Bus, now: datetime | None = None) -> Trip | None:
    """The Trip this bus runs on today's IST date, if one exists."""
    now = now or datetime.now(timezone.utc)
    start, end = _ist_day_bounds_utc(now.astimezone(IST).date())
    return (
        db.query(Trip)
        .filter(Trip.bus_id == bus.id, Trip.departure_time >= start, Trip.departure_time < end)
        .first()
    )


def get_or_create_todays_trip(
    db: Session, bus: Bus, now: datetime | None = None, delay_minutes: int = 0
) -> Trip:
    """Today's Trip for this bus, creating it from the timetable if needed.

    `delay_minutes` only applies to a newly created trip; an existing trip keeps
    whatever delay has been reported against it.
    """
    now = now or datetime.now(timezone.utc)
    trip = get_todays_trip(db, bus, now)
    if trip is None:
        departure_time = departure_on(bus, now.astimezone(IST).date())
        trip = Trip(
            route_id=bus.route_id,
            bus_id=bus.id,
            operator=bus.operator,
            bus_number=bus.bus_number,
            departure_time=departure_time,
            current_delay_minutes=delay_minutes,
            status=TripStatus.SCHEDULED if departure_time > now else TripStatus.IN_TRANSIT,
        )
        db.add(trip)
        db.flush()
    return trip


def find_bus(db: Session, bus_number: str) -> Bus:
    """Look up an active bus by number, ignoring case and spaces.

    An exact key match wins; otherwise a partial number ("PA 1187") is accepted
    when it identifies exactly one bus.
    """
    key = normalize_bus_number(bus_number)
    active = db.query(Bus).filter(Bus.is_active.is_(True))
    if key:
        bus = active.filter(Bus.bus_number_key == key).first()
        if bus is not None:
            return bus
        candidates = active.filter(Bus.bus_number_key.contains(key, autoescape=True)).limit(2).all()
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise NotFoundError(
                "More than one bus matches that number. Type the full number from your ticket, "
                "for example UK07 PA 1187."
            )
    raise NotFoundError(BUS_NOT_FOUND)


@dataclass
class BusRun:
    """A bus's run today: the persisted Trip when one exists, otherwise its timetable with no delay."""

    bus: Bus
    trip: Trip | None
    departure_time: datetime  # aware UTC

    @property
    def delay_minutes(self) -> int:
        return self.trip.current_delay_minutes if self.trip else 0

    def scheduled_at(self, stop: Stop) -> datetime:
        return self.departure_time + timedelta(minutes=stop.minutes_from_origin)

    def expected_at(self, stop: Stop) -> datetime:
        return self.scheduled_at(stop) + timedelta(minutes=self.delay_minutes)


def todays_run(db: Session, bus: Bus, now: datetime | None = None) -> BusRun:
    """Read-only view of today's run; never creates a Trip (see get_or_create_todays_trip)."""
    now = now or datetime.now(timezone.utc)
    trip = get_todays_trip(db, bus, now)
    if trip is not None:
        return BusRun(bus=bus, trip=trip, departure_time=as_aware_utc(trip.departure_time))
    return BusRun(bus=bus, trip=None, departure_time=departure_on(bus, now.astimezone(IST).date()))
