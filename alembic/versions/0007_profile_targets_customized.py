"""Track whether nutrition targets were manually customized."""
from alembic import op
import sqlalchemy as sa


revision = "0007_profile_targets_customized"
down_revision = "0006_cardio_presets"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("targets_customized", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Preserve legacy values. Existing target fields came from an earlier
    # manual-target flow, so they must not be silently replaced on next edit.
    op.execute(
        sa.text(
            "UPDATE users SET targets_customized = TRUE "
            "WHERE daily_target_kcal IS NOT NULL "
            "OR target_protein_g IS NOT NULL "
            "OR target_carbs_g IS NOT NULL "
            "OR target_fat_g IS NOT NULL"
        )
    )


def downgrade():
    op.drop_column("users", "targets_customized")
