from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.order import OrderStatus, PaymentStatus
from app.schemas.catalog import IstTimesModel


class OrderItemCreate(BaseModel):
    """One line: a menu item, or a paid add-on from a menu_addon campaign. Prices are never taken from here."""

    menu_item_id: int | None = None
    addon_campaign_id: int | None = None
    quantity: int = Field(gt=0, le=50)

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "OrderItemCreate":
        if (self.menu_item_id is None) == (self.addon_campaign_id is None):
            raise ValueError("Each item needs exactly one of menu_item_id or addon_campaign_id")
        return self


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    menu_item_id: int | None
    addon_campaign_id: int | None
    name: str
    image_url: str | None
    quantity: int
    unit_price_inr: int


class OrderCreate(BaseModel):
    # The bus as printed on the ticket (e.g. "UK07 PA 1187"), or an existing trip.
    bus_number: str | None = None
    trip_id: int | None = None
    stop_id: int
    # Optional: the dhaba is taken from the menu items, and must match if given.
    dhaba_id: int | None = None
    seat_number: str = Field(min_length=1, max_length=10)
    items: list[OrderItemCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def _exactly_one_bus_reference(self) -> "OrderCreate":
        self.seat_number = self.seat_number.strip()
        if not self.seat_number:
            raise ValueError("seat_number is required")
        if (self.bus_number is None) == (self.trip_id is None):
            raise ValueError("Give exactly one of bus_number or trip_id")
        return self


class OrderRead(IstTimesModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    passenger_id: int
    trip_id: int
    bus_number: str
    stop_id: int
    stop_name: str
    dhaba_id: int
    dhaba_name: str
    seat_number: str | None
    status: OrderStatus
    payment_status: PaymentStatus
    subtotal_inr: int
    convenience_fee_inr: int
    commission_inr: int
    total_inr: int
    expected_arrival_time: datetime
    ready_by: datetime
    created_at: datetime
    items: list[OrderItemRead]


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class PaymentCheckout(BaseModel):
    """Everything the browser needs to open Razorpay Checkout. The key id is
    public; the secret stays on the server."""

    key_id: str
    razorpay_order_id: str
    amount_paise: int
    currency: str = "INR"


class OrderPlaced(OrderRead):
    """An order plus, when payments are on, the checkout handle for it."""

    payment: PaymentCheckout | None = None


class PaymentVerify(BaseModel):
    """The two values Razorpay Checkout hands back on success that the server
    needs; the Razorpay order id is already stored on our order."""

    razorpay_payment_id: str
    razorpay_signature: str


class KitchenOrderRead(OrderRead):
    passenger_name: str


class KitchenStatusUpdate(BaseModel):
    """Next status along placed -> accepted -> preparing -> ready -> picked_up, or cancelled."""

    status: OrderStatus
