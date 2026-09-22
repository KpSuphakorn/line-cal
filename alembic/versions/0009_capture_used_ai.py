"""Record whether a food capture actually spent an AI request

Revision ID: 0009_capture_used_ai
Revises: 0008_food_estimate_cache
"""
import sqlalchemy as sa
from alembic import op

revision = "0009_capture_used_ai"
down_revision = "0008_food_estimate_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing captures all predate the cache, so every one of them did call
    # the model — the server default is correct for the backfill too.
    op.add_column(
        "food_captures",
        sa.Column("used_ai", sa.Boolean(), server_default=sa.true(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("food_captures", "used_ai")
