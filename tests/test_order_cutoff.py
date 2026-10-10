from datetime import datetime, timedelta, timezone

import pytest

from app.models.dhaba import Dhaba
from app.models.stop import Stop
from app.models.trip import Trip
from app.services.order_service import validate_cutoff
from app.utils.errors import ConflictError


def _trip_stop_dhaba(minutes_from_origin: int, delay: int, prep_time: int):
    trip = Trip(departure_time=datetime(2026, 1, 1, 6, 0, tzinfo=timezone.utc), current_delay_minutes=delay)
    stop = Stop(minutes_from_origin=minutes_from_origin)
    dhaba = Dhaba(avg_prep_time_minutes=prep_time)
    return trip, stop, dhaba


def test_order_allowed_with_enough_buffer():
    # ETA is 60 min out; needs prep(15) + buffer(10) = 25 min. Plenty of room.
    trip, stop, dhaba = _trip_stop_dhaba(minutes_from_origin=60, delay=0, prep_time=15)
    eta = validate_cutoff(trip, stop, dhaba, now=trip.departure_time)
    assert eta == trip.departure_time + timedelta(minutes=60)


def test_order_rejected_when_too_close_to_arrival():
    # ETA is 20 min out; needs prep(15) + buffer(10) = 25 min. Not enough time.
    trip, stop, dhaba = _trip_stop_dhaba(minutes_from_origin=20, delay=0, prep_time=15)
    with pytest.raises(ConflictError):
        validate_cutoff(trip, stop, dhaba, now=trip.departure_time)


def test_rejection_message_mentions_minutes_needed_and_available():
    trip, stop, dhaba = _trip_stop_dhaba(minutes_from_origin=5, delay=0, prep_time=10)
    with pytest.raises(ConflictError) as exc_info:
        validate_cutoff(trip, stop, dhaba, now=trip.departure_time)
    assert "Too late to order" in exc_info.value.detail
    assert "5 min" in exc_info.value.detail
    assert "20 min" in exc_info.value.detail  # prep(10) + buffer(10)


def test_exact_boundary_is_allowed():
    # minutes_to_arrival == required_minutes exactly -> allowed, since rule is >=
    trip, stop, dhaba = _trip_stop_dhaba(minutes_from_origin=25, delay=0, prep_time=15)
    eta = validate_cutoff(trip, stop, dhaba, now=trip.departure_time)
    assert eta is not None


def test_delay_increases_available_lead_time():
    # Without delay: ETA is 20 min out, needs 25 -> rejected.
    trip, stop, dhaba = _trip_stop_dhaba(minutes_from_origin=20, delay=0, prep_time=15)
    with pytest.raises(ConflictError):
        validate_cutoff(trip, stop, dhaba, now=trip.departure_time)

    # Same stop and "now", but the bus is running 10 min late -> ETA pushed back,
    # so there's now *more* lead time to order (delay helps, it never hurts).
    trip2, stop2, dhaba2 = _trip_stop_dhaba(minutes_from_origin=20, delay=10, prep_time=15)
    eta = validate_cutoff(trip2, stop2, dhaba2, now=trip2.departure_time)
    assert eta is not None
