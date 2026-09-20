import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from app.db.models import FoodAnalysisDraft, FoodLog, User

ROOT = Path(__file__).resolve().parents[1]


def test_orm_matches_ownership_and_food_nutrition_contract():
    assert FoodLog.__table__.c.user_id.nullable is False
    assert "meal_type" not in FoodLog.__table__.c

    assert User.__table__.c.timezone.nullable is False
    assert User.__table__.c.profile_completed.nullable is False
    for model in (FoodLog, FoodAnalysisDraft):
        assert {constraint.name for constraint in model.__table__.constraints} >= {
            f"ck_{'food_log' if model is FoodLog else 'food_draft'}_calories",
            f"ck_{'food_log' if model is FoodLog else 'food_draft'}_protein",
            f"ck_{'food_log' if model is FoodLog else 'food_draft'}_carbs",
            f"ck_{'food_log' if model is FoodLog else 'food_draft'}_fat",
        }


def test_fresh_sqlite_migrations_reach_head(tmp_path):
    database_path = tmp_path / "migration-test.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path}"
    env.pop("MIGRATION_DATABASE_URL", None)

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    with sqlite3.connect(database_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert revision == "0005_remove_legacy_paths"

        food_columns = {
            row[1]: row[3]
            for row in connection.execute("PRAGMA table_info(food_logs)")
        }
        assert food_columns["user_id"] == 1
        assert food_columns["calories"] == 1

        indexes = {
            row[1]
            for row in connection.execute("PRAGMA index_list(food_logs)")
        }
        assert "ix_food_logs_user_logged_at" in indexes

        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert not {"workout_logs", "user_exercises", "pending_food_analyses"} & tables


def test_migration_url_overrides_runtime_url(tmp_path):
    runtime_path = tmp_path / "runtime.db"
    migration_path = tmp_path / "migration.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{runtime_path}"
    env["MIGRATION_DATABASE_URL"] = f"sqlite:///{migration_path}"

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert migration_path.exists()
    assert not runtime_path.exists()
