import pytest

from app.models.order import Order, OrderStatus
from app.services.order_service import advance_status, cancel_order
from app.utils.errors import BadRequestError, ConflictError


@pytest.mark.parametrize(
    "current,next_status",
    [
        (OrderStatus.PLACED, OrderStatus.ACCEPTED),
        (OrderStatus.ACCEPTED, OrderStatus.PREPARING),
        (OrderStatus.PREPARING, OrderStatus.READY),
        (OrderStatus.READY, OrderStatus.PICKED_UP),
    ],
)
def test_valid_forward_transitions(current, next_status):
    order = Order(status=current)
    advance_status(order, next_status)
    assert order.status == next_status


def test_cannot_skip_statuses():
    order = Order(status=OrderStatus.PLACED)
    with pytest.raises(BadRequestError):
        advance_status(order, OrderStatus.PREPARING)


def test_cannot_move_backwards():
    order = Order(status=OrderStatus.READY)
    with pytest.raises(BadRequestError):
        advance_status(order, OrderStatus.ACCEPTED)


def test_cannot_advance_from_terminal_status():
    order = Order(status=OrderStatus.PICKED_UP)
    with pytest.raises(BadRequestError):
        advance_status(order, OrderStatus.PICKED_UP)


def test_cannot_transition_directly_to_cancelled_via_advance():
    order = Order(status=OrderStatus.PLACED)
    with pytest.raises(BadRequestError):
        advance_status(order, OrderStatus.CANCELLED)


@pytest.mark.parametrize("status", [OrderStatus.PLACED, OrderStatus.ACCEPTED])
def test_cancel_allowed_from_early_statuses(status):
    order = Order(status=status)
    cancel_order(order)
    assert order.status == OrderStatus.CANCELLED


@pytest.mark.parametrize("status", [OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.PICKED_UP])
def test_cancel_rejected_once_preparing_or_later(status):
    order = Order(status=status)
    with pytest.raises(ConflictError):
        cancel_order(order)
