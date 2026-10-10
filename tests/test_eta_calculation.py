from datetime import datetime, timedelta, timezone

from app.models.stop import Stop
from app.models.trip import Trip
from app.services.eta_service import compute_eta, minutes_until


def test_compute_eta_adds_minutes_from_origin_and_delay():
    departure = datetime(2026, 1, 1, 6, 0, tzinfo=timezone.utc)
    trip = Trip(departure_time=departure, current_delay_minutes=15)
    stop = Stop(minutes_from_origin=30)

    assert compute_eta(trip, stop) == departure + timedelta(minutes=45)


def test_compute_eta_with_zero_delay():
    departure = datetime(2026, 1, 1, 6, 0, tzinfo=timezone.utc)
    trip = Trip(departure_time=departure, current_delay_minutes=0)
    stop = Stop(minutes_from_origin=50)

    assert compute_eta(trip, stop) == departure + timedelta(minutes=50)


def test_compute_eta_for_further_stop_includes_full_delay():
    departure = datetime(2026, 1, 1, 6, 0, tzinfo=timezone.utc)
    trip = Trip(departure_time=departure, current_delay_minutes=20)
    stop = Stop(minutes_from_origin=130)

    assert compute_eta(trip, stop) == departure + timedelta(minutes=150)


def test_minutes_until_future_is_positive():
    now = datetime(2026, 1, 1, 6, 0, tzinfo=timezone.utc)
    future = now + timedelta(minutes=20)

    assert minutes_until(future, now) == 20


def test_minutes_until_past_is_negative():
    now = datetime(2026, 1, 1, 6, 0, tzinfo=timezone.utc)
    past = now - timedelta(minutes=5)

    assert minutes_until(past, now) == -5
