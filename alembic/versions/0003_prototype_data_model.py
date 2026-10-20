"""prototype data model: buses, ad campaigns, integer-rupee money, dhaba status

Revision ID: 0003_prototype_data_model
Revises: 0002_menu_item_is_available
Create Date: 2026-10-19

Adds what the prototype needs on top of the existing schema:
  - routes: code, slug, highway, operator, duration
  - stops: lat/lng become nullable (the seed has no coordinates)
  - buses (new), trips.bus_id -> buses
  - dhabas: slug, cuisine, rating, review_count, avg_bill_inr, review_summary,
    status (replaces is_active), commission_pct, sponsored_offer
  - menu_items: dish_id, description, image_url, is_signature; price -> price_inr (int)
  - ad_campaigns (new)
  - orders: total_amount -> subtotal_inr / convenience_fee_inr / commission_inr / total_inr (int)
  - order_items: unit_price -> unit_price_inr (int); menu_item_id nullable; addon_campaign_id

Existing rows are converted, not dropped: is_active=false -> status 'blocked', and
decimal money is rounded to whole rupees. Legacy orders keep subtotal = total,
with no fee or commission, since none was charged when they were placed.

batch_alter_table is used wherever SQLite (local dev / tests) can't ALTER in place;
on Postgres it emits plain ALTER TABLE statements.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_prototype_data_model"
down_revision: Union[str, None] = "0002_menu_item_is_available"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DHABA_STATUS = sa.Enum("active", "pending", "blocked", name="dhaba_status")
AD_PLACEMENT = sa.Enum("trip_banner", "sponsored_dhaba", "menu_addon", "order_wait", name="ad_placement")
AD_STATUS = sa.Enum("live", "paused", name="ad_status")
AD_ART = sa.Enum("bottle", "shield", "packet", name="ad_art")


def _round_to_int(column: str) -> str:
    return f"CAST(ROUND({column}) AS INTEGER)"


def upgrade() -> None:
    bind = op.get_bind()

    # ---- routes ----
    with op.batch_alter_table("routes") as batch_op:
        batch_op.add_column(sa.Column("code", sa.String(20), nullable=True))
        batch_op.add_column(sa.Column("slug", sa.String(50), nullable=True))
        batch_op.add_column(sa.Column("highway", sa.String(50), nullable=True))
        batch_op.add_column(sa.Column("operator", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("duration", sa.String(20), nullable=True))
        batch_op.create_unique_constraint("uq_routes_code", ["code"])
        batch_op.create_unique_constraint("uq_routes_slug", ["slug"])

    # ---- stops ----
    with op.batch_alter_table("stops") as batch_op:
        batch_op.alter_column("lat", existing_type=sa.Float(), nullable=True)
        batch_op.alter_column("lng", existing_type=sa.Float(), nullable=True)

    # ---- buses ----
    op.create_table(
        "buses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("route_id", sa.Integer(), sa.ForeignKey("routes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bus_number", sa.String(20), nullable=False),
        sa.Column("bus_number_key", sa.String(20), nullable=False),
        sa.Column("departs", sa.Time(), nullable=False),
        sa.Column("bus_type", sa.String(50), nullable=True),
        sa.Column("operator", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_buses_bus_number_key", "buses", ["bus_number_key"], unique=True)

    with op.batch_alter_table("trips") as batch_op:
        batch_op.add_column(sa.Column("bus_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_trips_bus_id_buses", "buses", ["bus_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_trips_bus_id", "trips", ["bus_id"])

    # ---- dhabas ----
    DHABA_STATUS.create(bind, checkfirst=True)
    with op.batch_alter_table("dhabas") as batch_op:
        batch_op.add_column(sa.Column("slug", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("cuisine", sa.String(30), nullable=True))
        batch_op.add_column(sa.Column("rating", sa.Numeric(2, 1), nullable=True))
        batch_op.add_column(sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("avg_bill_inr", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("review_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("status", DHABA_STATUS, nullable=False, server_default="active"))
        batch_op.add_column(sa.Column("commission_pct", sa.Integer(), nullable=False, server_default="12"))
        batch_op.add_column(sa.Column("sponsored_offer", sa.Text(), nullable=True))
        batch_op.create_unique_constraint("uq_dhabas_slug", ["slug"])

    dhabas = sa.table("dhabas", sa.column("is_active", sa.Boolean()), sa.column("status", DHABA_STATUS))
    op.execute(dhabas.update().where(dhabas.c.is_active == sa.false()).values(status="blocked"))
    with op.batch_alter_table("dhabas") as batch_op:
        batch_op.drop_column("is_active")

    # ---- menu_items ----
    op.add_column("menu_items", sa.Column("price_inr", sa.Integer(), nullable=True))
    op.execute(f"UPDATE menu_items SET price_inr = {_round_to_int('price')}")
    with op.batch_alter_table("menu_items") as batch_op:
        batch_op.add_column(sa.Column("dish_id", sa.String(60), nullable=True))
        batch_op.add_column(sa.Column("description", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("image_url", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("is_signature", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.alter_column("price_inr", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("price")
    op.create_index("ix_menu_items_dish_id", "menu_items", ["dish_id"])

    # ---- ad_campaigns ----
    op.create_table(
        "ad_campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("advertiser", sa.String(255), nullable=False),
        sa.Column("headline", sa.String(255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("cta", sa.String(60), nullable=True),
        sa.Column("art", AD_ART, nullable=True),
        sa.Column("color_from", sa.String(9), nullable=True),
        sa.Column("color_to", sa.String(9), nullable=True),
        sa.Column("placement", AD_PLACEMENT, nullable=False),
        sa.Column("route_id", sa.Integer(), sa.ForeignKey("routes.id", ondelete="CASCADE"), nullable=True),
        sa.Column("dhaba_id", sa.Integer(), sa.ForeignKey("dhabas.id", ondelete="CASCADE"), nullable=True),
        sa.Column("addon_price_inr", sa.Integer(), nullable=True),
        sa.Column("addon_item_name", sa.String(255), nullable=True),
        sa.Column("daily_budget_inr", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("taps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("spend_inr", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", AD_STATUS, nullable=False, server_default="live"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ---- orders ----
    for column in ("subtotal_inr", "total_inr"):
        op.add_column("orders", sa.Column(column, sa.Integer(), nullable=True))
    op.execute(
        f"UPDATE orders SET subtotal_inr = {_round_to_int('total_amount')}, "
        f"total_inr = {_round_to_int('total_amount')}"
    )
    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(sa.Column("convenience_fee_inr", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("commission_inr", sa.Integer(), nullable=False, server_default="0"))
        batch_op.alter_column("subtotal_inr", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("total_inr", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("total_amount")

    # ---- order_items ----
    op.add_column("order_items", sa.Column("unit_price_inr", sa.Integer(), nullable=True))
    op.execute(f"UPDATE order_items SET unit_price_inr = {_round_to_int('unit_price')}")
    with op.batch_alter_table("order_items") as batch_op:
        batch_op.add_column(sa.Column("addon_campaign_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_order_items_addon_campaign_id_ad_campaigns", "ad_campaigns",
            ["addon_campaign_id"], ["id"], ondelete="SET NULL",
        )
        batch_op.alter_column("menu_item_id", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("unit_price_inr", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("unit_price")
        batch_op.create_check_constraint(
            "ck_order_item_menu_item_xor_addon",
            "(menu_item_id IS NULL) <> (addon_campaign_id IS NULL)",
        )


def downgrade() -> None:
    bind = op.get_bind()

    # ---- order_items ----
    # Add-on lines have no menu item and can't exist in the old schema.
    op.execute("DELETE FROM order_items WHERE menu_item_id IS NULL")
    op.add_column("order_items", sa.Column("unit_price", sa.Numeric(8, 2), nullable=True))
    op.execute("UPDATE order_items SET unit_price = unit_price_inr")
    with op.batch_alter_table("order_items") as batch_op:
        batch_op.drop_constraint("ck_order_item_menu_item_xor_addon", type_="check")
        batch_op.drop_constraint("fk_order_items_addon_campaign_id_ad_campaigns", type_="foreignkey")
        batch_op.drop_column("addon_campaign_id")
        batch_op.drop_column("unit_price_inr")
        batch_op.alter_column("unit_price", existing_type=sa.Numeric(8, 2), nullable=False)
        batch_op.alter_column("menu_item_id", existing_type=sa.Integer(), nullable=False)

    # ---- orders ----
    op.add_column("orders", sa.Column("total_amount", sa.Numeric(8, 2), nullable=True))
    op.execute("UPDATE orders SET total_amount = total_inr")
    with op.batch_alter_table("orders") as batch_op:
        batch_op.alter_column("total_amount", existing_type=sa.Numeric(8, 2), nullable=False)
        for column in ("subtotal_inr", "convenience_fee_inr", "commission_inr", "total_inr"):
            batch_op.drop_column(column)

    # ---- ad_campaigns ----
    op.drop_table("ad_campaigns")
    for enum_type in (AD_ART, AD_STATUS, AD_PLACEMENT):
        enum_type.drop(bind, checkfirst=True)

    # ---- menu_items ----
    op.drop_index("ix_menu_items_dish_id", table_name="menu_items")
    op.add_column("menu_items", sa.Column("price", sa.Numeric(8, 2), nullable=True))
    op.execute("UPDATE menu_items SET price = price_inr")
    with op.batch_alter_table("menu_items") as batch_op:
        batch_op.alter_column("price", existing_type=sa.Numeric(8, 2), nullable=False)
        for column in ("price_inr", "dish_id", "description", "image_url", "is_signature"):
            batch_op.drop_column(column)

    # ---- dhabas ----
    op.add_column("dhabas", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    dhabas = sa.table("dhabas", sa.column("is_active", sa.Boolean()), sa.column("status", DHABA_STATUS))
    op.execute(dhabas.update().where(dhabas.c.status != "active").values(is_active=sa.false()))
    with op.batch_alter_table("dhabas") as batch_op:
        batch_op.drop_constraint("uq_dhabas_slug", type_="unique")
        for column in (
            "slug", "cuisine", "rating", "review_count", "avg_bill_inr",
            "review_summary", "status", "commission_pct", "sponsored_offer",
        ):
            batch_op.drop_column(column)
    DHABA_STATUS.drop(bind, checkfirst=True)

    # ---- trips / buses ----
    op.drop_index("ix_trips_bus_id", table_name="trips")
    with op.batch_alter_table("trips") as batch_op:
        batch_op.drop_constraint("fk_trips_bus_id_buses", type_="foreignkey")
        batch_op.drop_column("bus_id")
    op.drop_index("ix_buses_bus_number_key", table_name="buses")
    op.drop_table("buses")

    # ---- stops ----
    # Stops created without coordinates get 0,0 rather than blocking the downgrade.
    op.execute("UPDATE stops SET lat = 0 WHERE lat IS NULL")
    op.execute("UPDATE stops SET lng = 0 WHERE lng IS NULL")
    with op.batch_alter_table("stops") as batch_op:
        batch_op.alter_column("lat", existing_type=sa.Float(), nullable=False)
        batch_op.alter_column("lng", existing_type=sa.Float(), nullable=False)

    # ---- routes ----
    with op.batch_alter_table("routes") as batch_op:
        batch_op.drop_constraint("uq_routes_slug", type_="unique")
        batch_op.drop_constraint("uq_routes_code", type_="unique")
        for column in ("code", "slug", "highway", "operator", "duration"):
            batch_op.drop_column(column)
