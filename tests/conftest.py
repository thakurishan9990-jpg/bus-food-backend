import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.dhaba import Dhaba
from app.models.route import Route
from app.models.stop import Stop
from app.models.user import User, UserRole
from app.utils.auth import hash_password


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

    dhaba = Dhaba(stop_id=stop.id, name="Test Dhaba", avg_prep_time_minutes=10, is_active=True)
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
