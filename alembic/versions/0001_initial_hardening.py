"""Create the complete application schema and hardening tables.

This is the first migration, so it must be able to build an empty database from
scratch.  The previous version only created the two hardening tables and relied
on ``Base.metadata.create_all`` having run first, which made ``alembic upgrade
head`` fail on a fresh production database.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_hardening"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("gender", sa.String(length=10), nullable=True),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("height_cm", sa.Float(), nullable=True),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("goal", sa.String(length=50), nullable=True),
        sa.Column("daily_target_kcal", sa.Float(), nullable=True),
        sa.Column("target_protein_g", sa.Float(), nullable=True),
        sa.Column("target_carbs_g", sa.Float(), nullable=True),
        sa.Column("target_fat_g", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_id", "users", ["id"])

    op.create_table(
        "food_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("meal_type", sa.String(length=20), nullable=True),
        sa.Column("food_name", sa.String(length=200), nullable=False),
        sa.Column("portion", sa.String(length=150), nullable=True),
        sa.Column("calories", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("protein", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("carbs", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("fat", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("logged_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("calories >= 0", name="ck_food_log_calories"),
        sa.CheckConstraint("protein >= 0", name="ck_food_log_protein"),
        sa.CheckConstraint("carbs >= 0", name="ck_food_log_carbs"),
        sa.CheckConstraint("fat >= 0", name="ck_food_log_fat"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_food_logs_user_id", "food_logs", ["user_id"])
    op.create_index("ix_food_logs_logged_at", "food_logs", ["logged_at"])
    op.create_index("ix_food_logs_user_logged_at", "food_logs", ["user_id", "logged_at"])

    op.create_table(
        "workout_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("workout_type", sa.String(length=30), nullable=True),
        sa.Column("routine_name", sa.String(length=150), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=True),
        sa.Column("calories_burned", sa.Float(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("logged_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_workout_logs_user_id", "workout_logs", ["user_id"])
    op.create_index("ix_workout_logs_logged_at", "workout_logs", ["logged_at"])

    op.create_table(
        "user_exercises",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("split_id", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("weight", sa.String(length=50), nullable=True),
        sa.Column("target", sa.String(length=100), nullable=True),
        sa.Column("order_num", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_user_exercises_user_id", "user_exercises", ["user_id"])

    op.create_table(
        "pending_food_analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("food_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("token"),
    )
    op.create_index("ix_pending_food_analyses_token", "pending_food_analyses", ["token"])
    op.create_index("ix_pending_food_analyses_user_id", "pending_food_analyses", ["user_id"])
    op.create_table(
        "processed_webhooks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_processed_webhooks_event_id", "processed_webhooks", ["event_id"])
    op.create_index("ix_processed_webhooks_user_id", "processed_webhooks", ["user_id"])

def downgrade():
    op.drop_table("processed_webhooks")
    op.drop_table("pending_food_analyses")
    op.drop_table("user_exercises")
    op.drop_table("workout_logs")
    op.drop_index("ix_food_logs_user_logged_at", table_name="food_logs")
    op.drop_table("food_logs")
    op.drop_table("users")
