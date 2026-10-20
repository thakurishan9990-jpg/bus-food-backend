import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AdPlacement(str, enum.Enum):
    TRIP_BANNER = "trip_banner"
    SPONSORED_DHABA = "sponsored_dhaba"
    MENU_ADDON = "menu_addon"
    ORDER_WAIT = "order_wait"


class AdStatus(str, enum.Enum):
    LIVE = "live"
    PAUSED = "paused"


class AdArt(str, enum.Enum):
    BOTTLE = "bottle"
    SHIELD = "shield"
    PACKET = "packet"


def _enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    return Enum(enum_cls, name=name, values_callable=lambda x: [e.value for e in x])


class AdCampaign(Base):
    __tablename__ = "ad_campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    advertiser: Mapped[str] = mapped_column(String(255))
    headline: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    cta: Mapped[str | None] = mapped_column(String(60), nullable=True)
    art: Mapped[AdArt | None] = mapped_column(_enum(AdArt, "ad_art"), nullable=True)
    color_from: Mapped[str | None] = mapped_column(String(9), nullable=True)
    color_to: Mapped[str | None] = mapped_column(String(9), nullable=True)
    placement: Mapped[AdPlacement] = mapped_column(_enum(AdPlacement, "ad_placement"))
    # NULL route_id = runs on every route.
    route_id: Mapped[int | None] = mapped_column(ForeignKey("routes.id", ondelete="CASCADE"), nullable=True)
    dhaba_id: Mapped[int | None] = mapped_column(ForeignKey("dhabas.id", ondelete="CASCADE"), nullable=True)
    # Only for placement=menu_addon: the item the passenger can add to their order.
    addon_price_inr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    addon_item_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    daily_budget_inr: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    views: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    taps: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    spend_inr: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[AdStatus] = mapped_column(
        _enum(AdStatus, "ad_status"), default=AdStatus.LIVE, server_default=AdStatus.LIVE.value
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    route: Mapped["Route | None"] = relationship()
    dhaba: Mapped["Dhaba | None"] = relationship()
