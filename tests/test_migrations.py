import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from app.db.models import FoodAnalysisDraft, FoodLog, User
from app.db.models import CardioPreset

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
        assert revision == "0006_cardio_presets"

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
        assert "cardio_presets" in tables


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


def test_existing_cardio_presets_table_is_adopted_by_0006(tmp_path):
    database_path = tmp_path / "pilot-migration-test.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path}"
    env.pop("MIGRATION_DATABASE_URL", None)

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0005_remove_legacy_paths"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    engine = create_engine(env["DATABASE_URL"])
    CardioPreset.__table__.create(engine)
    engine.dispose()

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
        assert revision == "0006_cardio_presets"


def test_malformed_existing_cardio_presets_table_fails_adoption(tmp_path):
    database_path = tmp_path / "malformed-cardio-presets.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path}"
    env.pop("MIGRATION_DATABASE_URL", None)

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0005_remove_legacy_paths"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    with sqlite3.connect(database_path) as connection:
        # Keep every expected column name so adoption must validate the actual
        # schema instead of merely checking whether the table exists.
        connection.execute(
            """
            CREATE TABLE cardio_presets (
                id INTEGER,
                user_id VARCHAR(64) NOT NULL,
                name INTEGER NOT NULL,
                activity VARCHAR(80) NOT NULL,
                custom_name VARCHAR(80),
                duration_min FLOAT NOT NULL,
                incline_pct FLOAT,
                speed_kmh FLOAT,
                distance_km FLOAT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0
    assert "Cannot adopt existing cardio_presets table" in output
    with sqlite3.connect(database_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert revision == "0005_remove_legacy_paths"
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cardio_presets'"
        ).fetchone()


def test_adopted_cardio_presets_downgrade_is_non_destructive(tmp_path):
    database_path = tmp_path / "adopted-cardio-presets.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path}"
    env.pop("MIGRATION_DATABASE_URL", None)

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0005_remove_legacy_paths"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    engine = create_engine(env["DATABASE_URL"])
    CardioPreset.__table__.create(engine)
    recorded_at = datetime(2026, 9, 20, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            CardioPreset.__table__.insert().values(
                user_id="downgrade-user",
                name="เดินชัน",
                activity="เดินชัน",
                duration_min=30,
                created_at=recorded_at,
                updated_at=recorded_at,
            )
        )
    engine.dispose()

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0005_remove_legacy_paths"],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0
    assert "Downgrade of 0006_cardio_presets is disabled" in output
    with sqlite3.connect(database_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert revision == "0006_cardio_presets"
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cardio_presets'"
        ).fetchone()
    assert connection.execute(
            "SELECT name FROM cardio_presets WHERE user_id='downgrade-user'"
        ).fetchone()[0] == "เดินชัน"
