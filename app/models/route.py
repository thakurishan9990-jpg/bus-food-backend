from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    # code/slug are the seed's natural keys (e.g. "DL-234" / "ddn"); NULL only on pre-seed legacy rows.
    code: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    slug: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    origin: Mapped[str] = mapped_column(String(255))
    destination: Mapped[str] = mapped_column(String(255))
    highway: Mapped[str | None] = mapped_column(String(50), nullable=True)
    operator: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stops: Mapped[list["Stop"]] = relationship(back_populates="route", cascade="all, delete-orphan")
    trips: Mapped[list["Trip"]] = relationship(back_populates="route", cascade="all, delete-orphan")
    buses: Mapped[list["Bus"]] = relationship(back_populates="route", cascade="all, delete-orphan")
