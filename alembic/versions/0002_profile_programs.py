"""Add onboarding fields and user-owned workout programs."""
from alembic import op
import sqlalchemy as sa


revision = "0002_profile_programs"
down_revision = "0001_initial_hardening"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("birth_date", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("activity_level", sa.String(length=30), nullable=True))
    op.add_column(
        "users",
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Asia/Bangkok"),
    )
    op.add_column(
        "users",
        sa.Column("profile_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "program_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_program_templates_key", "program_templates", ["key"])
    op.create_table(
        "template_exercises",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("sets", sa.Integer(), nullable=False),
        sa.Column("repetitions", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("order_num", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["template_id"], ["program_templates.id"]),
    )
    op.create_index("ix_template_exercises_template_id", "template_exercises", ["template_id"])
    op.create_table(
        "workout_programs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("source_key", sa.String(length=40), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["template_id"], ["program_templates.id"]),
        sa.UniqueConstraint("user_id", "source_key", name="uq_workout_program_user_source"),
    )
    op.create_index("ix_workout_programs_user_id", "workout_programs", ["user_id"])
    op.create_index("ix_workout_programs_template_id", "workout_programs", ["template_id"])
    op.create_table(
        "program_exercises",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("program_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("sets", sa.Integer(), nullable=False),
        sa.Column("repetitions", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("order_num", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["program_id"], ["workout_programs.id"]),
    )
    op.create_index("ix_program_exercises_program_id", "program_exercises", ["program_id"])


def downgrade():
    op.drop_table("program_exercises")
    op.drop_index("ix_workout_programs_template_id", table_name="workout_programs")
    op.drop_index("ix_workout_programs_user_id", table_name="workout_programs")
    op.drop_table("workout_programs")
    op.drop_index("ix_template_exercises_template_id", table_name="template_exercises")
    op.drop_table("template_exercises")
    op.drop_index("ix_program_templates_key", table_name="program_templates")
    op.drop_table("program_templates")
    op.drop_column("users", "profile_completed")
    op.drop_column("users", "timezone")
    op.drop_column("users", "activity_level")
    op.drop_column("users", "birth_date")
