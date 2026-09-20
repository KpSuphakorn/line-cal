"""Add reusable, user-owned cardio presets.

Some pilot databases created this exact table through ORM metadata before
Alembic was enabled.  Existing tables are adopted only after their schema is
validated in full.  Downgrade is intentionally disabled so an adopted table
can never be mistaken for an Alembic-owned table and dropped with user data.
"""
import re

from alembic import op
import sqlalchemy as sa


revision = "0006_cardio_presets"
down_revision = "0005_remove_legacy_paths"
branch_labels = None
depends_on = None


EXPECTED_COLUMNS = {
    "id": (sa.Integer, False),
    "user_id": (sa.String, False),
    "name": (sa.String, False),
    "activity": (sa.String, False),
    "custom_name": (sa.String, True),
    "duration_min": (sa.Float, False),
    "incline_pct": (sa.Float, True),
    "speed_kmh": (sa.Float, True),
    "distance_km": (sa.Float, True),
    "created_at": (sa.DateTime, False),
    "updated_at": (sa.DateTime, False),
}
EXPECTED_STRING_LENGTHS = {
    "user_id": 64,
    "name": 100,
    "activity": 80,
    "custom_name": 80,
}
EXPECTED_CHECKS = {
    "ck_cardio_preset_duration": "duration_min>0",
    "ck_cardio_preset_incline": "incline_pctisnullorincline_pct>=0",
    "ck_cardio_preset_speed": "speed_kmhisnullorspeed_kmh>=0",
    "ck_cardio_preset_distance": "distance_kmisnullordistance_km>=0",
}


def _normalized_sql(value: str | None) -> str:
    value = re.sub(
        r"::\s*(?:double\s+precision|doubleprecision|numeric|integer|bigint|real|smallint|float8|float4)\b",
        "",
        str(value or ""),
        flags=re.IGNORECASE,
    )
    return "".join(value.lower().split()).replace("(", "").replace(")", "")


def _column_type_matches(name: str, actual_type: sa.types.TypeEngine, expected_type: type) -> bool:
    if not isinstance(actual_type, expected_type):
        return False
    expected_length = EXPECTED_STRING_LENGTHS.get(name)
    return expected_length is None or getattr(actual_type, "length", None) == expected_length


def _validate_existing_table(bind) -> None:
    inspector = sa.inspect(bind)
    columns = inspector.get_columns("cardio_presets")
    actual_names = {column["name"] for column in columns}
    expected_names = set(EXPECTED_COLUMNS)
    if actual_names != expected_names:
        raise RuntimeError(
            "Cannot adopt existing cardio_presets table: columns must be exactly "
            + ", ".join(sorted(expected_names))
        )
    for column in columns:
        expected_type, expected_nullable = EXPECTED_COLUMNS[column["name"]]
        if not _column_type_matches(column["name"], column["type"], expected_type):
            raise RuntimeError(
                f"Cannot adopt existing cardio_presets table: invalid type for {column['name']}"
            )
        if bool(column["nullable"]) != expected_nullable:
            raise RuntimeError(
                f"Cannot adopt existing cardio_presets table: invalid nullability for {column['name']}"
            )
        if (
            bind.dialect.name != "sqlite"
            and column["name"] in {"created_at", "updated_at"}
            and not getattr(column["type"], "timezone", False)
        ):
            raise RuntimeError(
                f"Cannot adopt existing cardio_presets table: {column['name']} must use timezone-aware datetime"
            )

    primary_key = inspector.get_pk_constraint("cardio_presets").get("constrained_columns") or []
    if primary_key != ["id"]:
        raise RuntimeError("Cannot adopt existing cardio_presets table: primary key must be id")

    foreign_keys = inspector.get_foreign_keys("cardio_presets")
    if not any(
        fk.get("constrained_columns") == ["user_id"]
        and fk.get("referred_table") == "users"
        and fk.get("referred_columns") == ["id"]
        for fk in foreign_keys
    ):
        raise RuntimeError("Cannot adopt existing cardio_presets table: user_id must reference users.id")

    unique_constraints = inspector.get_unique_constraints("cardio_presets")
    if not any(
        constraint.get("name") == "uq_cardio_preset_user_name"
        and constraint.get("column_names") == ["user_id", "name"]
        for constraint in unique_constraints
    ):
        raise RuntimeError(
            "Cannot adopt existing cardio_presets table: missing unique constraint "
            "uq_cardio_preset_user_name(user_id, name)"
        )

    checks = {
        check.get("name"): _normalized_sql(check.get("sqltext"))
        for check in inspector.get_check_constraints("cardio_presets")
    }
    for name, expression in EXPECTED_CHECKS.items():
        if checks.get(name) != expression:
            raise RuntimeError(f"Cannot adopt existing cardio_presets table: invalid check {name}")

    indexes = {
        index.get("name"): index
        for index in inspector.get_indexes("cardio_presets")
    }
    user_index = indexes.get("ix_cardio_presets_user_id")
    if not user_index or user_index.get("column_names") != ["user_id"] or user_index.get("unique"):
        raise RuntimeError(
            "Cannot adopt existing cardio_presets table: index ix_cardio_presets_user_id "
            "must be non-unique on user_id"
        )


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    created = False
    if "cardio_presets" not in inspector.get_table_names():
        op.create_table(
            "cardio_presets",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("activity", sa.String(length=80), nullable=False),
            sa.Column("custom_name", sa.String(length=80), nullable=True),
            sa.Column("duration_min", sa.Float(), nullable=False),
            sa.Column("incline_pct", sa.Float(), nullable=True),
            sa.Column("speed_kmh", sa.Float(), nullable=True),
            sa.Column("distance_km", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("duration_min > 0", name="ck_cardio_preset_duration"),
            sa.CheckConstraint("incline_pct IS NULL OR incline_pct >= 0", name="ck_cardio_preset_incline"),
            sa.CheckConstraint("speed_kmh IS NULL OR speed_kmh >= 0", name="ck_cardio_preset_speed"),
            sa.CheckConstraint("distance_km IS NULL OR distance_km >= 0", name="ck_cardio_preset_distance"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.UniqueConstraint("user_id", "name", name="uq_cardio_preset_user_name"),
        )
        created = True
    else:
        _validate_existing_table(bind)
    if created:
        op.create_index("ix_cardio_presets_user_id", "cardio_presets", ["user_id"])


def downgrade():
    raise RuntimeError(
        "Downgrade of 0006_cardio_presets is disabled to protect adopted cardio_presets data; "
        "perform a reviewed manual rollback if required."
    )
