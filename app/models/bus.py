from datetime import time

from sqlalchemy import Boolean, ForeignKey, String, Time, true
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.database import Base


def normalize_bus_number(bus_number: str) -> str:
    """Lookup key for a bus number: uppercase with all whitespace removed ('uk07 pa 1187' -> 'UK07PA1187')."""
    return "".join(bus_number.split()).upper()


class Bus(Base):
    """One physical bus running on a route. Its delay lives on today's Trip (Trip.bus_id)."""

    __tablename__ = "buses"

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id", ondelete="CASCADE"))
    bus_number: Mapped[str] = mapped_column(String(20))
    bus_number_key: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    departs: Mapped[time] = mapped_column(Time)
    bus_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    operator: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())

    route: Mapped["Route"] = relationship(back_populates="buses")
    trips: Mapped[list["Trip"]] = relationship(back_populates="bus")

    @validates("bus_number")
    def _sync_bus_number_key(self, _key: str, value: str) -> str:
        # Keep the lookup key in step with the number as entered, so no caller can forget it.
        self.bus_number_key = normalize_bus_number(value)
        return value
