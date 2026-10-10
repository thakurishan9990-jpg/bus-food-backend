from app.models.dhaba import Dhaba, MenuItem
from app.models.route import Route
from app.models.stop import Stop
from app.models.trip import Trip
from app.models.user import User
from scripts.seed import seed

TABLES = [Route, Stop, Dhaba, MenuItem, User, Trip]


def _counts(db_session) -> dict:
    return {model.__name__: db_session.query(model).count() for model in TABLES}


def test_seed_is_idempotent(db_session):
    seed(db_session)
    first_counts = _counts(db_session)

    assert first_counts["Route"] == 1
    assert first_counts["Stop"] == 5
    assert first_counts["User"] == 3
    assert first_counts["Trip"] == 28  # 7 days x 4 departures/day

    seed(db_session)
    second_counts = _counts(db_session)

    assert second_counts == first_counts


def test_seed_twice_does_not_duplicate_natural_keys(db_session):
    seed(db_session)
    seed(db_session)

    assert db_session.query(Route).filter(Route.name.like("%Delhi%")).count() == 1
    assert db_session.query(User).filter(User.phone == "9876543210").count() == 1
    assert db_session.query(Dhaba).filter(Dhaba.name == "Sharma Dhaba").count() == 1
    assert db_session.query(Trip).filter(Trip.bus_number == "UP15-AB-1234").count() == 1
