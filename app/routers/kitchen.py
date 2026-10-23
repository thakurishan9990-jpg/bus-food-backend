from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.order import Order, OrderStatus
from app.models.user import User, UserRole
from app.schemas.order import KitchenOrderRead, KitchenStatusUpdate
from app.services import order_service
from app.services.eta_service import NOT_FOR_KITCHEN_STATUSES
from app.utils.errors import ForbiddenError, NotFoundError
from app.utils.security import require_role

router = APIRouter(prefix="/kitchen", tags=["kitchen"])


def _own_dhaba_id(current_user: User = Depends(require_role(UserRole.DHABA))) -> int:
    if current_user.dhaba_id is None:
        raise ForbiddenError("This dhaba account isn't linked to a dhaba")
    return current_user.dhaba_id


@router.get("/orders", response_model=list[KitchenOrderRead])
def kitchen_orders(dhaba_id: int = Depends(_own_dhaba_id), db: Session = Depends(get_db)) -> list[Order]:
    """Open orders for the caller's own dhaba, soonest bus arrival first. Dhaba role only."""
    return (
        db.query(Order)
        .filter(Order.dhaba_id == dhaba_id, Order.status.notin_(NOT_FOR_KITCHEN_STATUSES))
        .order_by(Order.expected_arrival_time, Order.id)
        .all()
    )


@router.patch("/orders/{order_id}", response_model=KitchenOrderRead)
def update_kitchen_order(
    order_id: int,
    payload: KitchenStatusUpdate,
    dhaba_id: int = Depends(_own_dhaba_id),
    db: Session = Depends(get_db),
) -> Order:
    """Move an order one step along placed -> accepted -> preparing -> ready -> picked_up.

    `cancelled` is allowed while the order is still placed or accepted. Dhaba role
    only, and only for the caller's own dhaba (403 otherwise).
    """
    order = db.get(Order, order_id)
    # An unpaid order is invisible to the kitchen, so it can't act on one either.
    if order is None or order.status == OrderStatus.AWAITING_PAYMENT:
        raise NotFoundError(f"Order {order_id} not found")
    if order.dhaba_id != dhaba_id:
        raise ForbiddenError("You may only manage your own dhaba's orders")

    if payload.status == OrderStatus.CANCELLED:
        order_service.cancel_order(order)
    else:
        order_service.advance_status(order, payload.status)
    db.commit()
    db.refresh(order)
    return order
