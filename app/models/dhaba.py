from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Dhaba(Base):
    __tablename__ = "dhabas"

    id: Mapped[int] = mapped_column(primary_key=True)
    stop_id: Mapped[int] = mapped_column(ForeignKey("stops.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    google_place_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avg_prep_time_minutes: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    stop: Mapped["Stop"] = relationship(back_populates="dhabas")
    menu_items: Mapped[list["MenuItem"]] = relationship(back_populates="dhaba", cascade="all, delete-orphan")
    review_cache: Mapped["ReviewCache | None"] = relationship(
        back_populates="dhaba", cascade="all, delete-orphan", uselist=False
    )


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    dhaba_id: Mapped[int] = mapped_column(ForeignKey("dhabas.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    price: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    is_veg: Mapped[bool] = mapped_column(Boolean)

    dhaba: Mapped["Dhaba"] = relationship(back_populates="menu_items")
