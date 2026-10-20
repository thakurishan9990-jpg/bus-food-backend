import enum
from decimal import Decimal

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, Numeric, String, Text, false, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.database import Base


class DhabaStatus(str, enum.Enum):
    ACTIVE = "active"
    PENDING = "pending"
    BLOCKED = "blocked"


class Dhaba(Base):
    __tablename__ = "dhabas"

    id: Mapped[int] = mapped_column(primary_key=True)
    stop_id: Mapped[int] = mapped_column(ForeignKey("stops.id", ondelete="CASCADE"))
    # Seed natural key (e.g. "ddn-punjabi-rasoi"); NULL only on pre-seed legacy rows.
    slug: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    cuisine: Mapped[str | None] = mapped_column(String(30), nullable=True)
    google_place_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avg_prep_time_minutes: Mapped[int] = mapped_column(Integer)
    rating: Mapped[Decimal | None] = mapped_column(Numeric(2, 1), nullable=True)
    review_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    avg_bill_inr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[DhabaStatus] = mapped_column(
        Enum(DhabaStatus, name="dhaba_status", values_callable=lambda x: [e.value for e in x]),
        default=DhabaStatus.ACTIVE,
        server_default=DhabaStatus.ACTIVE.value,
    )
    commission_pct: Mapped[int] = mapped_column(
        Integer, default=lambda: settings.default_commission_pct, server_default="12"
    )
    # Non-null means this dhaba is a paid sponsored listing.
    sponsored_offer: Mapped[str | None] = mapped_column(Text, nullable=True)

    stop: Mapped["Stop"] = relationship(back_populates="dhabas")
    menu_items: Mapped[list["MenuItem"]] = relationship(back_populates="dhaba", cascade="all, delete-orphan")
    review_cache: Mapped["ReviewCache | None"] = relationship(
        back_populates="dhaba", cascade="all, delete-orphan", uselist=False
    )

    @property
    def is_pure_veg(self) -> bool:
        """Derived from the menu rather than stored, so it can never drift: no non-veg items at all."""
        return bool(self.menu_items) and all(item.is_veg for item in self.menu_items)


def _default_image_url(context) -> str | None:
    dish_id = context.get_current_parameters().get("dish_id")
    return f"/static/dishes/{dish_id}.jpg" if dish_id else None


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    dhaba_id: Mapped[int] = mapped_column(ForeignKey("dhabas.id", ondelete="CASCADE"))
    # Slug from the seed's dishes[] (e.g. "butter-chicken"); also names the dish image.
    dish_id: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_inr: Mapped[int] = mapped_column(Integer)
    is_veg: Mapped[bool] = mapped_column(Boolean)
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True, default=_default_image_url)
    is_signature: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())

    dhaba: Mapped["Dhaba"] = relationship(back_populates="menu_items")
