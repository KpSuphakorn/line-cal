"""Add the food estimate cache

Revision ID: 0008_food_estimate_cache
Revises: 0007_profile_targets_customized
"""
import sqlalchemy as sa
from alembic import op

revision = "0008_food_estimate_cache"
down_revision = "0007_profile_targets_customized"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "food_estimate_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cache_key", sa.String(length=300), nullable=False),
        sa.Column("items_json", sa.Text(), nullable=False),
        sa.Column("hit_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cache_key"),
    )
    op.create_index("ix_food_estimate_cache_cache_key", "food_estimate_cache", ["cache_key"])


def downgrade() -> None:
    op.drop_index("ix_food_estimate_cache_cache_key", table_name="food_estimate_cache")
    op.drop_table("food_estimate_cache")
