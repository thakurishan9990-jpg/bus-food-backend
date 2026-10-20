import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.bus import Bus, normalize_bus_number
from app.models.dhaba import Dhaba, DhabaStatus
from app.models.route import Route
from app.models.stop import Stop
from app.models.user import User, UserRole
from app.services.bus_service import get_todays_trip
from app.utils.auth import hash_password
from scripts.seed import load_seed_file, seed

SEED_DATA = load_seed_file()
TEST_ADMIN_PASSWORD = "test-admin-password"


@pytest.fixture()
def db_session():
    """A fresh SQLite in-memory DB per test, with all tables created."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    """FastAPI TestClient wired to the in-memory db_session via dependency override."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def seeded_route_and_dhaba(db_session):
    """One route -> one stop -> one dhaba, for tests that just need valid IDs."""
    route = Route(name="Test Route", origin="A", destination="B")
    db_session.add(route)
    db_session.flush()

    stop = Stop(
        route_id=route.id, name="Stop1", lat=0, lng=0, sequence_order=1,
        minutes_from_origin=30, halt_duration_minutes=10,
    )
    db_session.add(stop)
    db_session.flush()

    dhaba = Dhaba(stop_id=stop.id, name="Test Dhaba", avg_prep_time_minutes=10)
    db_session.add(dhaba)
    db_session.commit()
    return route, stop, dhaba


def make_user(db_session, phone: str, role: UserRole, dhaba_id: int | None = None, password: str = "password123") -> User:
    user = User(phone=phone, name="Test", hashed_password=hash_password(password), role=role, dhaba_id=dhaba_id)
    db_session.add(user)
    db_session.commit()
    return user


def auth_header(client, phone: str, password: str = "password123") -> dict:
    resp = client.post("/auth/login", data={"username": phone, "password": password})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---- the full seed-file dataset ----

@pytest.fixture(scope="session")
def _seeded_template():
    """The seed file loaded once per test run, into an in-memory SQLite DB that tests copy."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    saved, settings.admin_password = settings.admin_password, TEST_ADMIN_PASSWORD
    try:
        with Session(engine) as session:
            seed(session)
    finally:
        settings.admin_password = saved
    raw = engine.raw_connection()
    yield raw.driver_connection
    raw.close()
    engine.dispose()


@pytest.fixture()
def seeded_session(_seeded_template):
    """A private copy of the seeded DB for one test (8 routes, 284 dhabas, 2245 menu items, ...)."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    _seeded_template.backup(conn)
    engine = create_engine("sqlite://", creator=lambda: conn, poolclass=StaticPool)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        conn.close()


@pytest.fixture()
def seeded_client(seeded_session):
    def override_get_db():
        yield seeded_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def demo_headers(client, role: str) -> dict:
    """Bearer headers for a seeded demo user: the seed file's passenger or dhaba, or the settings admin."""
    if role == "admin":
        return auth_header(client, settings.admin_phone, TEST_ADMIN_PASSWORD)
    user = next(u for u in SEED_DATA["demo_users"] if u["role"] == role)
    return auth_header(client, user["phone"], user["password"])


def open_ordering(db, bus_number: str, stop_sequence: int = 1, minutes_left: int = 30):
    """Move today's trip for a bus so `stop_sequence`'s order cut-off is `minutes_left` from now.

    Returns (trip, stop). The bus's reported delay is kept.
    """
    bus = db.query(Bus).filter(Bus.bus_number_key == normalize_bus_number(bus_number)).one()
    trip = get_todays_trip(db, bus)
    stop = db.query(Stop).filter(Stop.route_id == bus.route_id, Stop.sequence_order == stop_sequence).one()
    slowest_prep = max(d.avg_prep_time_minutes for d in stop.dhabas if d.status == DhabaStatus.ACTIVE)
    trip.departure_time = datetime.now(timezone.utc) + timedelta(
        minutes=minutes_left - stop.minutes_from_origin - trip.current_delay_minutes
        + slowest_prep + settings.order_cutoff_buffer_minutes
    )
    db.commit()
    return trip, stop
