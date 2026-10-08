"""Allow cardio sessions with optional time and walking steps."""
import sqlalchemy as sa
from alembic import op


revision = "0011_optional_cardio_metrics"
down_revision = "0010_food_lookups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("cardio_presets", "cardio_details"):
        with op.batch_alter_table(table) as batch:
            batch.alter_column("duration_min", existing_type=sa.Float(), nullable=True)
            batch.add_column(sa.Column("steps", sa.Integer(), nullable=True))
            batch.add_column(sa.Column("variant", sa.String(40), nullable=True))
            if table == "cardio_details":
                batch.add_column(sa.Column("activity_type", sa.String(80), nullable=True))
            batch.drop_constraint(
                "ck_cardio_preset_duration" if table == "cardio_presets" else "ck_cardio_duration",
                type_="check",
            )
            batch.create_check_constraint(
                "ck_cardio_preset_duration" if table == "cardio_presets" else "ck_cardio_duration",
                "duration_min IS NULL OR duration_min > 0",
            )
            batch.create_check_constraint(
                "ck_cardio_preset_steps" if table == "cardio_presets" else "ck_cardio_steps",
                "steps IS NULL OR steps > 0",
            )
    op.execute(
        "UPDATE cardio_details SET activity_type = CASE "
        "WHEN activity IN ('เดิน', 'เดินชัน', 'วิ่ง', 'จักรยาน', 'ว่ายน้ำ', 'อื่นๆ') "
        "THEN activity ELSE 'อื่นๆ' END WHERE activity_type IS NULL"
    )


def downgrade() -> None:
    for table in ("cardio_presets", "cardio_details"):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(
                "ck_cardio_preset_steps" if table == "cardio_presets" else "ck_cardio_steps",
                type_="check",
            )
            batch.drop_column("steps")
            batch.drop_column("variant")
            if table == "cardio_details":
                batch.drop_column("activity_type")
            batch.drop_constraint(
                "ck_cardio_preset_duration" if table == "cardio_presets" else "ck_cardio_duration",
                type_="check",
            )
            batch.create_check_constraint(
                "ck_cardio_preset_duration" if table == "cardio_presets" else "ck_cardio_duration",
                "duration_min > 0",
            )
            batch.alter_column("duration_min", existing_type=sa.Float(), nullable=False)
