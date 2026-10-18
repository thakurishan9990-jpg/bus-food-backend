from app.config import settings
from app.models.dhaba import Dhaba, MenuItem
from app.models.route import Route
from app.models.stop import Stop
from app.models.trip import Trip
from app.models.user import User, UserRole
from app.utils.auth import verify_password
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


def _admin(db_session) -> User:
    return db_session.query(User).filter(User.role == UserRole.ADMIN).one()


def test_admin_password_comes_from_env_and_demo_users_keep_shared_password(db_session, monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "s3cret-admin")
    seed(db_session)

    assert verify_password("s3cret-admin", _admin(db_session).hashed_password)
    assert not verify_password(settings.seed_user_password, _admin(db_session).hashed_password)
    for phone in ("9876543210", "9876543211"):
        user = db_session.query(User).filter(User.phone == phone).one()
        assert verify_password(settings.seed_user_password, user.hashed_password)


def test_admin_password_is_random_and_printed_when_unset(db_session, monkeypatch, capsys):
    monkeypatch.setattr(settings, "admin_password", "")
    seed(db_session)

    hashed = _admin(db_session).hashed_password
    assert not verify_password(settings.seed_user_password, hashed)
    admin_line = next(line for line in capsys.readouterr().out.splitlines() if "admin:" in line)
    generated = admin_line.split("password='")[1].split("'")[0]
    assert verify_password(generated, hashed)


def test_reseed_updates_existing_admin_password(db_session, monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "first-password")
    seed(db_session)
    monkeypatch.setattr(settings, "admin_password", "second-password")
    seed(db_session)

    assert db_session.query(User).filter(User.role == UserRole.ADMIN).count() == 1
    assert verify_password("second-password", _admin(db_session).hashed_password)
