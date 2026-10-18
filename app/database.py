import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings

# Vercel sets VERCEL=1 in every deployment environment.
ON_VERCEL = bool(os.environ.get("VERCEL"))


def _with_required_ssl(url: URL) -> URL:
    """Add sslmode=require to a Postgres URL that doesn't specify an sslmode."""
    if url.get_backend_name() == "postgresql" and "sslmode" not in url.query:
        return url.update_query_dict({"sslmode": "require"})
    return url


def _build_engine():
    # settings.database_url has already had postgres:// rewritten to postgresql://.
    url = make_url(settings.database_url)
    if ON_VERCEL:
        # A serverless invocation must not hold a pooled connection between
        # requests, and hosted Postgres reached from Vercel requires TLS.
        return create_engine(_with_required_ssl(url), poolclass=NullPool)
    return create_engine(url)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Declarative base shared by all SQLAlchemy models."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
