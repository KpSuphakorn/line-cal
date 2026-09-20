"""Add durable multi-item food captures and provenance."""
from alembic import op
import sqlalchemy as sa

revision = "0003_food_captures"
down_revision = "0002_profile_programs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "food_captures",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("source_message_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("ai_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("token"),
        sa.UniqueConstraint("user_id", "source_message_id", name="uq_food_capture_user_message"),
    )
    op.create_index("ix_food_captures_token", "food_captures", ["token"])
    op.create_index("ix_food_captures_user_id", "food_captures", ["user_id"])
    op.create_index("ix_food_captures_status", "food_captures", ["status"])

    op.create_table(
        "food_analysis_drafts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("capture_id", sa.Integer(), nullable=False),
        sa.Column("order_num", sa.Integer(), nullable=False),
        sa.Column("food_name", sa.String(length=200), nullable=False),
        sa.Column("portion", sa.String(length=150), nullable=False),
        sa.Column("calories", sa.Float(), nullable=False),
        sa.Column("protein", sa.Float(), nullable=False),
        sa.Column("carbs", sa.Float(), nullable=False),
        sa.Column("fat", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("calories >= 0", name="ck_food_draft_calories"),
        sa.CheckConstraint("protein >= 0", name="ck_food_draft_protein"),
        sa.CheckConstraint("carbs >= 0", name="ck_food_draft_carbs"),
        sa.CheckConstraint("fat >= 0", name="ck_food_draft_fat"),
        sa.ForeignKeyConstraint(["capture_id"], ["food_captures.id"]),
    )
    op.create_index("ix_food_analysis_drafts_capture_id", "food_analysis_drafts", ["capture_id"])
    # SQLite cannot ALTER TABLE to add a foreign key directly.  Alembic's
    # batch operation rebuilds that table on SQLite and emits normal ALTER
    # statements on PostgreSQL.
    with op.batch_alter_table("food_logs") as batch_op:
        batch_op.add_column(sa.Column("capture_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_food_logs_capture_id", ["capture_id"])
        batch_op.create_foreign_key(
            "fk_food_logs_capture_id", "food_captures", ["capture_id"], ["id"]
        )


def downgrade():
    with op.batch_alter_table("food_logs") as batch_op:
        batch_op.drop_constraint("fk_food_logs_capture_id", type_="foreignkey")
        batch_op.drop_index("ix_food_logs_capture_id")
        batch_op.drop_column("capture_id")
    op.drop_index("ix_food_analysis_drafts_capture_id", table_name="food_analysis_drafts")
    op.drop_table("food_analysis_drafts")
    op.drop_index("ix_food_captures_status", table_name="food_captures")
    op.drop_index("ix_food_captures_user_id", table_name="food_captures")
    op.drop_index("ix_food_captures_token", table_name="food_captures")
    op.drop_table("food_captures")
