"""Record calorie lookups so they count against the daily AI allowance

Revision ID: 0010_food_lookups
Revises: 0009_capture_used_ai
"""
import sqlalchemy as sa
from alembic import op

revision = "0010_food_lookups"
down_revision = "0009_capture_used_ai"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "food_lookups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("used_ai", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_food_lookups_user_created", "food_lookups", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_food_lookups_user_created", table_name="food_lookups")
    op.drop_table("food_lookups")
