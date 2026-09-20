"""Unit tests for the current nutrition and workout-program calculations."""

from datetime import datetime, date, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.database import Base
from app.db.models import FoodLog, User
from app.services.fitness import (
    calculate_bmr,
    calculate_incline_walk_burn,
    calculate_tdee,
    get_daily_summary,
    get_history_summary,
    get_monthly_summary,
    get_or_create_user,
    get_past_food_history,
    get_user_programs,
    get_weekly_stats,
    update_food_log,
    update_exercise_weight,
    update_user_profile,
)
from app.services.workouts import create_cardio_session, create_strength_session
from app.services.workouts import delete_program


@pytest.fixture
def db_session():
    """Use a disposable SQLite schema for every test."""
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=test_engine)
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = testing_session()
    yield session
    session.close()


def complete_profile(db, user_id: str, **target_overrides) -> User:
    values = {
        "name": "Test User",
        "gender": "male",
        "age": 30,
        "height_cm": 175.0,
        "weight_kg": 72.0,
        "goal": "recomposition",
        "activity_multiplier": 1.45,
        "daily_target_kcal": 2100.0,
        "target_protein_g": 140.0,
        "target_carbs_g": 240.0,
        "target_fat_g": 60.0,
    }
    values.update(target_overrides)
    update_user_profile(db, user_id, values)
    return db.query(User).filter(User.id == user_id).one()


def test_bmr_calculation():
    assert calculate_bmr("male", 72.0, 174.0, 22) == 1702.5


def test_tdee_calculation():
    assert calculate_tdee(1702.5, 1.45) == 2468.6


def test_incline_walk_burn():
    burn_40 = calculate_incline_walk_burn(72.0, 40, incline_pct=10.0)
    assert 250.0 < burn_40 < 450.0


def test_daily_summary_workflow_after_profile_setup(db_session):
    user_id = "test_user_daily"
    user = complete_profile(db_session, user_id)
    assert user.profile_completed is True
    assert user.daily_target_kcal == 2100.0

    db_session.add_all([
        FoodLog(user_id=user_id, food_name="กล้วยหอม 1 ลูก", calories=105.0, protein=1.3, carbs=27.0, fat=0.3),
        FoodLog(user_id=user_id, food_name="ข้าวกะเพราอกไก่", calories=520.0, protein=34.0, carbs=58.0, fat=14.0),
    ])
    db_session.commit()
    programs = get_user_programs(db_session, user_id)
    push_id = next(program["id"] for program in programs.values() if program["name"] == "Push")
    create_strength_session(db_session, user_id, push_id)
    create_cardio_session(db_session, user_id, "เดินชัน", 40)

    summary = get_daily_summary(db_session, user_id)
    assert summary["target_kcal"] == 2100.0
    assert summary["calories_in"] == 625.0
    assert summary["calories_burned"] > 0
    assert summary["remaining_kcal"] == 1475.0
    assert summary["protein"] == 35.3
    assert len(summary["food_logs"]) == 2
    assert len(summary["workout_logs"]) == 2

    weekly = get_weekly_stats(db_session, user_id, days=7)
    assert weekly["total_calories_in"] == 625.0
    assert weekly["total_calories_burned"] == summary["calories_burned"]
    assert weekly["weights_completed"] == 1
    assert weekly["cardio_count"] == 1

    history = get_past_food_history(db_session, user_id, limit=5)
    assert len(history) == 2
    assert history[0]["name"] in ["กล้วยหอม 1 ลูก", "ข้าวกะเพราอกไก่"]


def test_user_programs_are_independent_and_editable(db_session):
    user_id = "test_user_programs"
    complete_profile(db_session, user_id)

    programs = get_user_programs(db_session, user_id)
    assert len(programs) == 3
    assert {program["name"] for program in programs.values()} == {"Push", "Pull", "Legs"}

    push = next(program for program in programs.values() if program["name"] == "Push")
    pec_dec = next(exercise for exercise in push["exercises"] if "pec dec" in exercise["name"].lower())
    assert pec_dec["weight"] == 40.0

    updated = update_exercise_weight(db_session, user_id, "pec dec fly", "45 kg")
    assert updated is not None
    assert updated.weight == 45.0

    refreshed = get_user_programs(db_session, user_id)
    refreshed_push = next(program for program in refreshed.values() if program["name"] == "Push")
    refreshed_pec_dec = next(exercise for exercise in refreshed_push["exercises"] if "pec dec" in exercise["name"].lower())
    assert refreshed_pec_dec["weight"] == 45.0


def test_monthly_summary_handles_incomplete_profile_and_food_crud(db_session):
    user_id = "test_user_monthly"
    get_or_create_user(db_session, user_id, settings)

    monthly_before = get_monthly_summary(db_session, user_id, datetime.now().year, datetime.now().month)
    assert monthly_before["target_kcal"] == 0.0
    assert monthly_before["target_protein"] == 0.0
    assert all(not day["protein_goal_met"] for day in monthly_before["daily_breakdown"])

    food = FoodLog(
        user_id=user_id,
        food_name="ข้าวไข่เจียว",
        portion="1 จาน",
        calories=450.0,
        protein=12.0,
        carbs=50.0,
        fat=22.0,
    )
    db_session.add(food)
    db_session.commit()
    db_session.refresh(food)

    monthly = get_monthly_summary(db_session, user_id, datetime.now().year, datetime.now().month)
    assert monthly["days_logged"] >= 1
    assert len(monthly["daily_breakdown"]) == monthly["total_days"]

    updated = update_food_log(db_session, food.id, {"calories": 400.0, "food_name": "ข้าวไข่เจียวไร้น้ำมัน"})
    assert updated is not None
    assert updated.calories == 400.0
    assert updated.food_name == "ข้าวไข่เจียวไร้น้ำมัน"


def test_bangkok_day_groups_utc_midnight_crossing_entries(db_session):
    user_id = "bangkok-midnight"
    get_or_create_user(db_session, user_id, settings)
    db_session.add_all([
        FoodLog(
            user_id=user_id,
            food_name="หลังเที่ยงคืนกรุงเทพ",
            calories=100,
            logged_at=datetime(2026, 9, 19, 17, 30, tzinfo=timezone.utc),
        ),
        FoodLog(
            user_id=user_id,
            food_name="ก่อนเที่ยงคืนกรุงเทพ",
            calories=200,
            logged_at=datetime(2026, 9, 19, 16, 59, tzinfo=timezone.utc),
        ),
    ])
    db_session.commit()

    summary = get_daily_summary(db_session, user_id, date(2026, 9, 20))
    assert summary["calories_in"] == 100
    assert summary["food_logs"][0]["time"] == "00:30"

    monthly = get_monthly_summary(db_session, user_id, 2026, 9)
    days = {item["date"]: item["calories_in"] for item in monthly["daily_breakdown"]}
    assert days["2026-09-20"] == 100
    assert days["2026-09-19"] == 200


def test_deleting_program_detaches_historical_session(db_session):
    user_id = "program-history"
    complete_profile(db_session, user_id)
    programs = get_user_programs(db_session, user_id)
    program_id = next(item["id"] for item in programs.values() if item["name"] == "Push")
    session = create_strength_session(db_session, user_id, program_id)

    assert delete_program(db_session, user_id, program_id) is True
    saved = db_session.query(type(session)).filter_by(id=session.id).one()
    assert saved.program_id is None
    assert saved.estimated_calories > 0


def test_profile_update_preserves_manual_targets_without_reset(db_session):
    user_id = "manual-targets"
    complete_profile(
        db_session,
        user_id,
        daily_target_kcal=2000,
        target_protein_g=150,
        target_carbs_g=180,
        target_fat_g=70,
    )
    update_user_profile(db_session, user_id, {"name": "Renamed User"})
    saved = db_session.query(User).filter_by(id=user_id).one()
    assert (saved.daily_target_kcal, saved.target_protein_g, saved.target_carbs_g, saved.target_fat_g) == (2000, 150, 180, 70)

    update_user_profile(db_session, user_id, {"weight_kg": 80, "reset_targets": True})
    reset = db_session.query(User).filter_by(id=user_id).one()
    assert reset.daily_target_kcal != 2000


def test_history_summary_uses_bangkok_week_bounds(db_session):
    user_id = "history-summary"
    get_or_create_user(db_session, user_id, settings)
    db_session.add(FoodLog(
        user_id=user_id,
        food_name="มื้อทดสอบ",
        calories=500,
        protein=30,
        carbs=50,
        fat=10,
        logged_at=datetime(2026, 9, 19, 17, 0, tzinfo=timezone.utc),
    ))
    db_session.commit()
    result = get_history_summary(db_session, user_id, "week", date(2026, 9, 20))
    assert result["start_date"] == "2026-09-14"
    assert result["summary"]["total_food_entries"] == 1
    assert result["summary"]["food_logged_days"] == 1
    assert result["summary"]["average_daily_calories"] == 500
    assert result["summary"]["peak_day"]["calories_in"] == 500
    assert result["daily_breakdown"][-1]["calories_in"] == 500
