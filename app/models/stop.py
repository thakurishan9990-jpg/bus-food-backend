from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Stop(Base):
    __tablename__ = "stops"
    __table_args__ = (UniqueConstraint("route_id", "sequence_order", name="uq_stop_route_sequence"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    sequence_order: Mapped[int] = mapped_column(Integer)
    minutes_from_origin: Mapped[int] = mapped_column(Integer)
    halt_duration_minutes: Mapped[int] = mapped_column(Integer)

    route: Mapped["Route"] = relationship(back_populates="stops")
    dhabas: Mapped[list["Dhaba"]] = relationship(back_populates="stop", cascade="all, delete-orphan")
