import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class OrderStatus(str, enum.Enum):
    PLACED = "placed"
    ACCEPTED = "accepted"
    PREPARING = "preparing"
    READY = "ready"
    PICKED_UP = "picked_up"
    CANCELLED = "cancelled"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    passenger_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"))
    stop_id: Mapped[int] = mapped_column(ForeignKey("stops.id", ondelete="CASCADE"))
    dhaba_id: Mapped[int] = mapped_column(ForeignKey("dhabas.id", ondelete="CASCADE"))
    seat_number: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, name="order_status"), default=OrderStatus.PLACED)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    expected_arrival_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    passenger: Mapped["User"] = relationship(back_populates="orders")
    trip: Mapped["Trip"] = relationship(back_populates="orders")
    stop: Mapped["Stop"] = relationship()
    dhaba: Mapped["Dhaba"] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id", ondelete="CASCADE"))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(8, 2))

    order: Mapped["Order"] = relationship(back_populates="items")
    menu_item: Mapped["MenuItem"] = relationship()
