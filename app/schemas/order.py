from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.order import OrderStatus


class OrderItemCreate(BaseModel):
    menu_item_id: int
    quantity: int = Field(gt=0)


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    menu_item_id: int
    quantity: int
    unit_price: Decimal


class OrderCreate(BaseModel):
    trip_id: int
    stop_id: int
    dhaba_id: int
    seat_number: str | None = None
    items: list[OrderItemCreate] = Field(min_length=1)


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    passenger_id: int
    trip_id: int
    stop_id: int
    stop_name: str
    dhaba_id: int
    dhaba_name: str
    seat_number: str | None
    status: OrderStatus
    total_amount: Decimal
    expected_arrival_time: datetime
    created_at: datetime
    items: list[OrderItemRead]


class OrderStatusUpdate(BaseModel):
    status: OrderStatus
