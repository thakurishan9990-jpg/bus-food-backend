"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "routes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("origin", sa.String(255), nullable=False),
        sa.Column("destination", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "stops",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("route_id", sa.Integer(), sa.ForeignKey("routes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("sequence_order", sa.Integer(), nullable=False),
        sa.Column("minutes_from_origin", sa.Integer(), nullable=False),
        sa.Column("halt_duration_minutes", sa.Integer(), nullable=False),
        sa.UniqueConstraint("route_id", "sequence_order", name="uq_stop_route_sequence"),
    )

    op.create_table(
        "dhabas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stop_id", sa.Integer(), sa.ForeignKey("stops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("google_place_id", sa.String(255), nullable=True),
        sa.Column("avg_prep_time_minutes", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "menu_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dhaba_id", sa.Integer(), sa.ForeignKey("dhabas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("price", sa.Numeric(8, 2), nullable=False),
        sa.Column("is_veg", sa.Boolean(), nullable=False),
    )

    op.create_table(
        "trips",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("route_id", sa.Integer(), sa.ForeignKey("routes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operator", sa.String(255), nullable=False),
        sa.Column("bus_number", sa.String(50), nullable=False),
        sa.Column("departure_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_delay_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_passed_stop_id", sa.Integer(), sa.ForeignKey("stops.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "status",
            sa.Enum("scheduled", "in_transit", "completed", "cancelled", name="trip_status"),
            nullable=False,
            server_default="scheduled",
        ),
    )

    op.create_table(
        "review_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dhaba_id", sa.Integer(), sa.ForeignKey("dhabas.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.Column("total_reviews", sa.Integer(), nullable=False),
        sa.Column("raw_reviews", sa.JSON(), nullable=False),
        sa.Column("ai_summary", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("phone", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("passenger", "dhaba", "admin", name="user_role"),
            nullable=False,
            server_default="passenger",
        ),
        sa.Column("dhaba_id", sa.Integer(), sa.ForeignKey("dhabas.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_phone", "users", ["phone"])

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("passenger_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trip_id", sa.Integer(), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stop_id", sa.Integer(), sa.ForeignKey("stops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dhaba_id", sa.Integer(), sa.ForeignKey("dhabas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seat_number", sa.String(10), nullable=True),
        sa.Column(
            "status",
            sa.Enum("placed", "accepted", "preparing", "ready", "picked_up", "cancelled", name="order_status"),
            nullable=False,
            server_default="placed",
        ),
        sa.Column("total_amount", sa.Numeric(8, 2), nullable=False),
        sa.Column("expected_arrival_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("menu_item_id", sa.Integer(), sa.ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(8, 2), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_table("users")
    op.drop_table("review_cache")
    op.drop_table("trips")
    op.drop_table("menu_items")
    op.drop_table("dhabas")
    op.drop_table("stops")
    op.drop_table("routes")

    sa.Enum(name="order_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="trip_status").drop(op.get_bind(), checkfirst=True)
