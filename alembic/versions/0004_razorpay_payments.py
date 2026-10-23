"""add payment columns and the awaiting_payment order status

Revision ID: 0004_razorpay_payments
Revises: 0003_prototype_data_model
Create Date: 2026-10-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004_razorpay_payments"
down_revision: Union[str, None] = "0003_prototype_data_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PAYMENT_STATUS = sa.Enum(
    "not_required", "awaiting", "paid", "refunded", name="payment_status"
)


def upgrade() -> None:
    bind = op.get_bind()

    # Postgres enums are closed types, so the new order status has to be added
    # to the existing type before any row can hold it. SQLite has no enum type
    # and needs neither step.
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'awaiting_payment'")

    PAYMENT_STATUS.create(bind, checkfirst=True)

    op.add_column(
        "orders",
        sa.Column(
            "payment_status",
            PAYMENT_STATUS,
            nullable=False,
            server_default="not_required",
        ),
    )
    op.add_column("orders", sa.Column("razorpay_order_id", sa.String(64), nullable=True))
    op.add_column("orders", sa.Column("razorpay_payment_id", sa.String(64), nullable=True))
    op.create_index("ix_orders_razorpay_order_id", "orders", ["razorpay_order_id"])


def downgrade() -> None:
    op.drop_index("ix_orders_razorpay_order_id", table_name="orders")
    op.drop_column("orders", "razorpay_payment_id")
    op.drop_column("orders", "razorpay_order_id")
    op.drop_column("orders", "payment_status")
    PAYMENT_STATUS.drop(op.get_bind(), checkfirst=True)
    # The 'awaiting_payment' value is left in the order_status enum: Postgres
    # cannot remove a value from a type without rewriting it.
