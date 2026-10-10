import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TripStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    IN_TRANSIT = "in_transit"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id", ondelete="CASCADE"))
    operator: Mapped[str] = mapped_column(String(255))
    bus_number: Mapped[str] = mapped_column(String(50))
    departure_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    current_delay_minutes: Mapped[int] = mapped_column(Integer, default=0)
    last_passed_stop_id: Mapped[int | None] = mapped_column(
        ForeignKey("stops.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[TripStatus] = mapped_column(
        Enum(TripStatus, name="trip_status"), default=TripStatus.SCHEDULED
    )

    route: Mapped["Route"] = relationship(back_populates="trips")
    last_passed_stop: Mapped["Stop | None"] = relationship(foreign_keys=[last_passed_stop_id])
    orders: Mapped[list["Order"]] = relationship(back_populates="trip", cascade="all, delete-orphan")
