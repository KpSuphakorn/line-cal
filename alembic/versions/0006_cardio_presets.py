"""Add reusable, user-owned cardio presets."""
from alembic import op
import sqlalchemy as sa


revision = "0006_cardio_presets"
down_revision = "0005_remove_legacy_paths"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cardio_presets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("activity", sa.String(length=80), nullable=False),
        sa.Column("custom_name", sa.String(length=80), nullable=True),
        sa.Column("duration_min", sa.Float(), nullable=False),
        sa.Column("incline_pct", sa.Float(), nullable=True),
        sa.Column("speed_kmh", sa.Float(), nullable=True),
        sa.Column("distance_km", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("duration_min > 0", name="ck_cardio_preset_duration"),
        sa.CheckConstraint("incline_pct IS NULL OR incline_pct >= 0", name="ck_cardio_preset_incline"),
        sa.CheckConstraint("speed_kmh IS NULL OR speed_kmh >= 0", name="ck_cardio_preset_speed"),
        sa.CheckConstraint("distance_km IS NULL OR distance_km >= 0", name="ck_cardio_preset_distance"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("user_id", "name", name="uq_cardio_preset_user_name"),
    )
    op.create_index("ix_cardio_presets_user_id", "cardio_presets", ["user_id"])


def downgrade():
    op.drop_index("ix_cardio_presets_user_id", table_name="cardio_presets")
    op.drop_table("cardio_presets")
