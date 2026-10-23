from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.dhaba import Dhaba, MenuItem
from app.models.order import Order, OrderStatus
from app.models.user import User, UserRole
from app.schemas.dhaba import MenuItemCreate, MenuItemRead, MenuItemUpdate
from app.schemas.order import OrderRead, OrderStatusUpdate
from app.services import order_service
from app.utils.errors import ForbiddenError, NotFoundError
from app.utils.security import get_current_user

router = APIRouter(tags=["kitchen"])


def _assert_owns_dhaba(current_user: User, dhaba_id: int) -> None:
    if current_user.role != UserRole.ADMIN and current_user.dhaba_id != dhaba_id:
        raise ForbiddenError("You may only manage your own dhaba")


@router.get("/dhabas/{dhaba_id}/incoming-orders", response_model=list[OrderRead])
def incoming_orders(
    dhaba_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[Order]:
    """Orders placed at this dhaba. Dhaba staff may only view their own dhaba's orders."""
    if db.get(Dhaba, dhaba_id) is None:
        raise NotFoundError(f"Dhaba {dhaba_id} not found")
    _assert_owns_dhaba(current_user, dhaba_id)
    # Orders still awaiting payment are not the kitchen's problem — it should
    # never start cooking food nobody has paid for.
    return (
        db.query(Order)
        .filter(Order.dhaba_id == dhaba_id, Order.status != OrderStatus.AWAITING_PAYMENT)
        .all()
    )


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


@router.post("/dhabas/{dhaba_id}/menu-items", response_model=MenuItemRead, status_code=201)
def create_dhaba_menu_item(
    dhaba_id: int,
    payload: MenuItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MenuItem:
    """Add a menu item to a dhaba. Dhaba staff may only add to their own dhaba."""
    if db.get(Dhaba, dhaba_id) is None:
        raise NotFoundError(f"Dhaba {dhaba_id} not found")
    _assert_owns_dhaba(current_user, dhaba_id)

    data = payload.model_dump()
    data["dhaba_id"] = dhaba_id  # the path owns this, never the body
    menu_item = MenuItem(**data)
    db.add(menu_item)
    db.commit()
    db.refresh(menu_item)
    return menu_item


@router.patch("/dhabas/{dhaba_id}/menu-items/{item_id}", response_model=MenuItemRead)
def update_dhaba_menu_item(
    dhaba_id: int,
    item_id: int,
    payload: MenuItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MenuItem:
    """Update a menu item. Dhaba staff may only update their own dhaba's items."""
    menu_item = db.get(MenuItem, item_id)
    if menu_item is None or menu_item.dhaba_id != dhaba_id:
        raise NotFoundError(f"Menu item {item_id} not found at dhaba {dhaba_id}")
    _assert_owns_dhaba(current_user, dhaba_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(menu_item, field, value)
    db.commit()
    db.refresh(menu_item)
    return menu_item


@router.delete("/dhabas/{dhaba_id}/menu-items/{item_id}", status_code=204)
def delete_dhaba_menu_item(
    dhaba_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a menu item. Dhaba staff may only delete from their own dhaba."""
    menu_item = db.get(MenuItem, item_id)
    if menu_item is None or menu_item.dhaba_id != dhaba_id:
        raise NotFoundError(f"Menu item {item_id} not found at dhaba {dhaba_id}")
    _assert_owns_dhaba(current_user, dhaba_id)

    db.delete(menu_item)
    db.commit()
