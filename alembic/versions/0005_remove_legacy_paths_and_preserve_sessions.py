"""Remove retired write paths and keep workout history when programs change.

The pilot database may already be at 0004, so this migration is deliberately
forward-only.  The old tables were never part of the current food-capture or
workout-session flow and can be dropped.  Workout sessions keep their history
when a user deletes a reusable program by setting ``program_id`` to NULL.
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_remove_legacy_paths"
down_revision = "0004_workout_sessions"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Existing pilot databases are empty in these legacy tables.  Use IF
    # EXISTS so this remains safe for databases created from a reduced schema.
    for table in ("pending_food_analyses", "user_exercises", "workout_logs"):
        if table in inspector.get_table_names():
            op.drop_table(table)

    if "food_logs" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("food_logs")}
        if "meal_type" in columns:
            with op.batch_alter_table("food_logs", recreate="always") as batch_op:
                batch_op.drop_column("meal_type")

    # PostgreSQL can alter the existing unnamed/default FK in place.  SQLite
    # keeps the 0004 FK for migration compatibility; fresh ORM schemas use the
    # correct ON DELETE SET NULL constraint, and SQLite does not enforce FKs
    # unless explicitly enabled by the caller.
    if bind.dialect.name != "sqlite" and "workout_sessions" in inspector.get_table_names():
        for fk in inspector.get_foreign_keys("workout_sessions"):
            if fk.get("constrained_columns") == ["program_id"]:
                name = fk.get("name")
                if name:
                    op.drop_constraint(name, "workout_sessions", type_="foreignkey")
                break
        op.create_foreign_key(
            "fk_workout_sessions_program_id",
            "workout_sessions",
            "workout_programs",
            ["program_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade():
    # Retired tables are intentionally not recreated; restoring them would
    # reintroduce public legacy write paths.
    pass
