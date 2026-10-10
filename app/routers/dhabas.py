from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.dhaba import Dhaba
from app.models.order import Order
from app.models.user import User, UserRole
from app.schemas.order import OrderRead, OrderStatusUpdate
from app.services import order_service
from app.utils.errors import ForbiddenError, NotFoundError
from app.utils.security import get_current_user

router = APIRouter(tags=["dhabas"])


def _assert_owns_dhaba(current_user: User, dhaba_id: int) -> None:
    if current_user.role != UserRole.ADMIN and current_user.dhaba_id != dhaba_id:
        raise ForbiddenError("You may only manage orders for your own dhaba")


@router.get("/dhabas/{dhaba_id}/incoming-orders", response_model=list[OrderRead])
def incoming_orders(
    dhaba_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[Order]:
    """Orders placed at this dhaba. Dhaba staff may only view their own dhaba's orders."""
    if db.get(Dhaba, dhaba_id) is None:
        raise NotFoundError(f"Dhaba {dhaba_id} not found")
    _assert_owns_dhaba(current_user, dhaba_id)
    return db.query(Order).filter(Order.dhaba_id == dhaba_id).all()


@router.patch("/orders/{order_id}/status", response_model=OrderRead)
def update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Order:
    """Advance an order's status one step forward. Dhaba staff may only update their own orders."""
    order = db.get(Order, order_id)
    if order is None:
        raise NotFoundError(f"Order {order_id} not found")
    _assert_owns_dhaba(current_user, order.dhaba_id)

    order_service.advance_status(order, payload.status)
    db.commit()
    db.refresh(order)
    return order
