import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
import sqlalchemy as sa
from sqlalchemy import create_engine
from app.db.models import FoodAnalysisDraft, FoodLog, User
from app.db.models import CardioDetails, CardioPreset

ROOT = Path(__file__).resolve().parents[1]


def create_legacy_cardio_presets(engine):
    """Build the exact pre-0011 schema used by the 0006 adoption fixture."""
    metadata = sa.MetaData()
    metadata.reflect(bind=engine, only=["users"])
    table = sa.Table(
        "cardio_presets", metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("activity", sa.String(80), nullable=False),
        sa.Column("custom_name", sa.String(80)),
        sa.Column("duration_min", sa.Float(), nullable=False),
        sa.Column("incline_pct", sa.Float()),
        sa.Column("speed_kmh", sa.Float()),
        sa.Column("distance_km", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("duration_min > 0", name="ck_cardio_preset_duration"),
        sa.CheckConstraint("incline_pct IS NULL OR incline_pct >= 0", name="ck_cardio_preset_incline"),
        sa.CheckConstraint("speed_kmh IS NULL OR speed_kmh >= 0", name="ck_cardio_preset_speed"),
        sa.CheckConstraint("distance_km IS NULL OR distance_km >= 0", name="ck_cardio_preset_distance"),
        sa.UniqueConstraint("user_id", "name", name="uq_cardio_preset_user_name"),
    )
    sa.Index("ix_cardio_presets_user_id", table.c.user_id)
    table.create(engine)
    return table


def alembic_head() -> str:
    """Ask Alembic for the head rather than pinning the number here.

    These assertions are about migrations reaching the end of the chain, not
    about which revision is last, so a hard-coded id only fails the suite every
    time a migration is added.
    """
    return ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_current_head()


def test_orm_matches_ownership_and_food_nutrition_contract():
    assert FoodLog.__table__.c.user_id.nullable is False
    assert "meal_type" not in FoodLog.__table__.c

    assert User.__table__.c.timezone.nullable is False
    assert User.__table__.c.profile_completed.nullable is False
    assert CardioPreset.__table__.c.duration_min.nullable is True
    assert CardioDetails.__table__.c.duration_min.nullable is True
    assert CardioPreset.__table__.c.steps.nullable is True
    assert CardioDetails.__table__.c.steps.nullable is True
    assert CardioPreset.__table__.c.variant.nullable is True
    assert CardioDetails.__table__.c.variant.nullable is True
    assert CardioDetails.__table__.c.activity_type.nullable is True
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
        assert revision == alembic_head()

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

        # The cache is looked up on every typed food message, so its key has to
        # be indexed and unique rather than scanned.
        cache_columns = {row[1] for row in connection.execute("PRAGMA table_info(food_estimate_cache)")}
        assert {"cache_key", "items_json", "hit_count"} <= cache_columns
        cache_indexes = {
            row[1]: row[2]
            for row in connection.execute("PRAGMA index_list(food_estimate_cache)")
        }
        assert any(unique for unique in cache_indexes.values()), "cache_key must be unique"

        # The daily allowance is counted from this column, so a capture served
        # from the cache can be excluded from it.
        capture_columns = {row[1]: row[3] for row in connection.execute("PRAGMA table_info(food_captures)")}
        assert capture_columns["used_ai"] == 1, "used_ai must be NOT NULL"

        # Lookups are counted per user per day, so that pair must be indexed.
        lookup_indexes = {row[1] for row in connection.execute("PRAGMA index_list(food_lookups)")}
        assert "ix_food_lookups_user_created" in lookup_indexes

        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert not {"workout_logs", "user_exercises", "pending_food_analyses"} & tables
        assert "cardio_presets" in tables
        assert {row[1] for row in connection.execute("PRAGMA table_info(cardio_presets)")} >= {"steps", "variant"}
        assert {row[1] for row in connection.execute("PRAGMA table_info(cardio_details)")} >= {"steps", "variant", "activity_type"}
        user_columns = {row[1]: row[3] for row in connection.execute("PRAGMA table_info(users)")}
        assert user_columns["targets_customized"] == 1


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


def test_optional_cardio_metrics_migration_preserves_existing_rows(tmp_path):
    database_path = tmp_path / "cardio-existing-rows.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path}"
    env.pop("MIGRATION_DATABASE_URL", None)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0010_food_lookups"],
        cwd=ROOT, env=env, check=True, capture_output=True, text=True,
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO cardio_presets (user_id, name, activity, duration_min, created_at, updated_at) "
            "VALUES ('legacy', 'เดิน', 'เดิน', 20, '2026-10-08', '2026-10-08')"
        )
        connection.execute(
            "INSERT INTO workout_sessions (id, user_id, session_type, name, estimated_duration_min, "
            "estimated_calories, calories_estimated, occurred_at, created_at, updated_at) "
            "VALUES (991, 'legacy', 'cardio', 'เดิน', 20, 88, 1, '2026-10-08', '2026-10-08', '2026-10-08')"
        )
        connection.execute(
            "INSERT INTO cardio_details (session_id, activity, duration_min, met) VALUES (991, 'เดิน', 20, 3.5)"
        )

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT, env=env, check=True, capture_output=True, text=True,
    )
    with sqlite3.connect(database_path) as connection:
        preset = connection.execute("SELECT duration_min, steps, variant FROM cardio_presets").fetchone()
        cardio = connection.execute("SELECT duration_min, steps, met, activity_type, variant FROM cardio_details").fetchone()
        session = connection.execute(
            "SELECT estimated_calories, calories_estimated FROM workout_sessions WHERE id = 991"
        ).fetchone()
    assert preset == (20, None, None)
    assert cardio == (20, None, 3.5, "เดิน", None)
    assert session == (88.0, 1)


def test_targets_customized_migration_preserves_legacy_targets(tmp_path):
    database_path = tmp_path / "legacy-targets.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path}"
    env.pop("MIGRATION_DATABASE_URL", None)

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0006_cardio_presets"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO users (id, daily_target_kcal, target_protein_g) VALUES (?, ?, ?)",
            ("legacy-manual", 2100, 140),
        )
        connection.execute("INSERT INTO users (id) VALUES (?)", ("legacy-empty",))

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    with sqlite3.connect(database_path) as connection:
        values = dict(connection.execute("SELECT id, targets_customized FROM users"))
    assert values == {"legacy-manual": 1, "legacy-empty": 0}


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
    create_legacy_cardio_presets(engine)
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
        assert revision == alembic_head()


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
    legacy_cardio_presets = create_legacy_cardio_presets(engine)
    recorded_at = datetime(2026, 9, 20, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            legacy_cardio_presets.insert().values(
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


def test_models_match_the_migrations(tmp_path):
    """Drift between models and migrations is how a deploy gets rejected at
    Railway's pre-deploy step, where it costs an outage instead of a red run."""
    database_path = tmp_path / "drift-check.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path}"
    env.pop("MIGRATION_DATABASE_URL", None)

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT, env=env, check=True, capture_output=True, text=True,
    )
    check = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )

    assert check.returncode == 0, f"models and migrations disagree:\n{check.stderr}"
