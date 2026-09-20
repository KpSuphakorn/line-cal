"""Add normalized workout sessions, strength snapshots and cardio details."""
from alembic import op
import sqlalchemy as sa


revision = "0004_workout_sessions"
down_revision = "0003_food_captures"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workout_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("program_id", sa.Integer(), nullable=True),
        sa.Column("source_event_id", sa.String(length=128), nullable=True),
        sa.Column("session_type", sa.String(length=20), nullable=False, server_default="strength"),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("estimated_duration_min", sa.Float(), nullable=False, server_default="0"),
        sa.Column("estimated_calories", sa.Float(), nullable=False, server_default="0"),
        sa.Column("calories_estimated", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("session_type IN ('strength', 'cardio')", name="ck_workout_session_type"),
        sa.CheckConstraint("estimated_duration_min >= 0", name="ck_workout_session_duration"),
        sa.CheckConstraint("estimated_calories >= 0", name="ck_workout_session_calories"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["program_id"], ["workout_programs.id"]),
        sa.UniqueConstraint("user_id", "source_event_id", name="uq_workout_session_user_event"),
    )
    op.create_index("ix_workout_sessions_user_id", "workout_sessions", ["user_id"])
    op.create_index("ix_workout_sessions_program_id", "workout_sessions", ["program_id"])
    op.create_index("ix_workout_sessions_occurred_at", "workout_sessions", ["occurred_at"])
    op.create_index("ix_workout_sessions_user_occurred", "workout_sessions", ["user_id", "occurred_at"])

    op.create_table(
        "session_exercises",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("sets", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("repetitions", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("order_num", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("sets >= 0", name="ck_session_exercise_sets"),
        sa.CheckConstraint("repetitions >= 0", name="ck_session_exercise_repetitions"),
        sa.CheckConstraint("weight IS NULL OR weight >= 0", name="ck_session_exercise_weight"),
        sa.ForeignKeyConstraint(["session_id"], ["workout_sessions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_session_exercises_session_id", "session_exercises", ["session_id"])

    op.create_table(
        "cardio_details",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("activity", sa.String(length=80), nullable=False),
        sa.Column("duration_min", sa.Float(), nullable=False),
        sa.Column("incline_pct", sa.Float(), nullable=True),
        sa.Column("speed_kmh", sa.Float(), nullable=True),
        sa.Column("distance_km", sa.Float(), nullable=True),
        sa.Column("met", sa.Float(), nullable=False),
        sa.CheckConstraint("duration_min > 0", name="ck_cardio_duration"),
        sa.CheckConstraint("incline_pct IS NULL OR incline_pct >= 0", name="ck_cardio_incline"),
        sa.CheckConstraint("speed_kmh IS NULL OR speed_kmh >= 0", name="ck_cardio_speed"),
        sa.CheckConstraint("distance_km IS NULL OR distance_km >= 0", name="ck_cardio_distance"),
        sa.ForeignKeyConstraint(["session_id"], ["workout_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("session_id", name="uq_cardio_details_session"),
    )


def downgrade():
    op.drop_table("cardio_details")
    op.drop_index("ix_session_exercises_session_id", table_name="session_exercises")
    op.drop_table("session_exercises")
    op.drop_index("ix_workout_sessions_user_occurred", table_name="workout_sessions")
    op.drop_index("ix_workout_sessions_occurred_at", table_name="workout_sessions")
    op.drop_index("ix_workout_sessions_program_id", table_name="workout_sessions")
    op.drop_index("ix_workout_sessions_user_id", table_name="workout_sessions")
    op.drop_table("workout_sessions")
