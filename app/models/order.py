import enum
from datetime import datetime, timedelta

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.database import Base


class OrderStatus(str, enum.Enum):
    AWAITING_PAYMENT = "awaiting_payment"
    PLACED = "placed"
    ACCEPTED = "accepted"
    PREPARING = "preparing"
    READY = "ready"
    PICKED_UP = "picked_up"
    CANCELLED = "cancelled"


class PaymentStatus(str, enum.Enum):
    NOT_REQUIRED = "not_required"
    AWAITING = "awaiting"
    PAID = "paid"
    REFUNDED = "refunded"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    passenger_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"))
    stop_id: Mapped[int] = mapped_column(ForeignKey("stops.id", ondelete="CASCADE"))
    dhaba_id: Mapped[int] = mapped_column(ForeignKey("dhabas.id", ondelete="CASCADE"))
    seat_number: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status", values_callable=lambda x: [e.value for e in x]),
        default=OrderStatus.PLACED,
    )
    # All money is integer rupees, computed server-side at order time.
    subtotal_inr: Mapped[int] = mapped_column(Integer)
    convenience_fee_inr: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    commission_inr: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    total_inr: Mapped[int] = mapped_column(Integer)
    expected_arrival_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payment_status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", values_callable=lambda x: [e.value for e in x]),
        default=PaymentStatus.NOT_REQUIRED,
        server_default=PaymentStatus.NOT_REQUIRED.value,
    )
    razorpay_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    passenger: Mapped["User"] = relationship(back_populates="orders")
    trip: Mapped["Trip"] = relationship(back_populates="orders")
    stop: Mapped["Stop"] = relationship()
    dhaba: Mapped["Dhaba"] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")

    @property
    def dhaba_name(self) -> str:
        return self.dhaba.name

    @property
    def stop_name(self) -> str:
        return self.stop.name

    @property
    def bus_number(self) -> str:
        return self.trip.bus_number

    @property
    def passenger_name(self) -> str:
        return self.passenger.name

    @property
    def ready_by(self) -> datetime:
        """When the kitchen should have the food ready, a few minutes before the bus pulls in."""
        return self.expected_arrival_time - timedelta(minutes=settings.ready_before_arrival_minutes)


class OrderItem(Base):
    """One order line: either a dhaba menu item or a paid add-on from a menu_addon AdCampaign."""

    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint(
            "(menu_item_id IS NULL) <> (addon_campaign_id IS NULL)",
            name="ck_order_item_menu_item_xor_addon",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    menu_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=True
    )
    addon_campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("ad_campaigns.id", ondelete="SET NULL"), nullable=True
    )
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_inr: Mapped[int] = mapped_column(Integer)

    order: Mapped["Order"] = relationship(back_populates="items")
    menu_item: Mapped["MenuItem | None"] = relationship()
    addon_campaign: Mapped["AdCampaign | None"] = relationship()

    @property
    def name(self) -> str:
        if self.menu_item is not None:
            return self.menu_item.name
        if self.addon_campaign is not None:
            return self.addon_campaign.addon_item_name or self.addon_campaign.headline
        return "Removed item"

    @property
    def image_url(self) -> str | None:
        return self.menu_item.image_url if self.menu_item is not None else None
