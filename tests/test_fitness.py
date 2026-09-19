"""Unit tests for Fitness & Nutrition calculation engine."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.database import Base
from app.db.models import User, FoodLog, WorkoutLog
from app.services.fitness import (
    calculate_bmr,
    calculate_tdee,
    calculate_incline_walk_burn,
    get_or_create_user,
    get_daily_summary
)
from app.config import settings


@pytest.fixture
def db_session():
    """In-memory SQLite database session fixture."""
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    yield session
    session.close()


def test_bmr_calculation():
    """Test Mifflin-St Jeor BMR formula for Suphakorn (Male, 72kg, 174cm, 22y)."""
    bmr = calculate_bmr("male", 72.0, 174.0, 22)
    # Expected: (10 * 72) + (6.25 * 174) - (5 * 22) + 5 = 720 + 1087.5 - 110 + 5 = 1702.5
    assert bmr == 1702.5


def test_tdee_calculation():
    """Test TDEE with moderate activity factor (1.45)."""
    tdee = calculate_tdee(1702.5, 1.45)
    assert tdee == 2468.6


def test_incline_walk_burn():
    """Test calorie burn for 40 minutes incline treadmill walking at 72kg."""
    burn_40 = calculate_incline_walk_burn(72.0, 40, incline_pct=10.0)
    # MET ~7.5 -> 7.5 * 3.5 * 72 / 200 * 40 = 378
    assert burn_40 > 250.0
    assert burn_40 < 450.0


def test_daily_summary_workflow(db_session):
    """Test creating user, logging meals, logging workouts, and computing balance."""
    user_id = "test_user_suphakorn"
    user = get_or_create_user(db_session, user_id, settings)
    assert user.id == user_id
    assert user.daily_target_kcal == 1950.0

    # 1. Log Pre-workout Banana
    db_session.add(FoodLog(
        user_id=user_id,
        food_name="กล้วยหอม 1 ลูก",
        calories=105.0,
        protein=1.3,
        carbs=27.0,
        fat=0.3
    ))

    # 2. Log Lunch
    db_session.add(FoodLog(
        user_id=user_id,
        food_name="ข้าวกะเพราอกไก่",
        calories=520.0,
        protein=34.0,
        carbs=58.0,
        fat=14.0
    ))

    # 3. Log Day 1 Workout (Push)
    db_session.add(WorkoutLog(
        user_id=user_id,
        workout_type="weights",
        routine_name="Day 1: Push",
        duration_min=60,
        calories_burned=300.0
    ))

    # 4. Log Incline Walk
    db_session.add(WorkoutLog(
        user_id=user_id,
        workout_type="cardio",
        routine_name="เดินชัน 40 นาที",
        duration_min=40,
        calories_burned=280.0
    ))

    db_session.commit()

    # Calculate summary
    summary = get_daily_summary(db_session, user_id)

    assert summary["target_kcal"] == 1950.0
    assert summary["calories_in"] == 625.0 # 105 + 520
    assert summary["calories_burned"] == 580.0 # 300 + 280
    assert summary["remaining_kcal"] == 1905.0
    assert summary["protein"] == 35.3
    assert len(summary["food_logs"]) == 2
    assert len(summary["workout_logs"]) == 2

    # Test Weekly Stats
    from app.services.fitness import get_weekly_stats, get_past_food_history
    weekly = get_weekly_stats(db_session, user_id, days=7)
    assert weekly["total_calories_in"] == 625.0
    assert weekly["total_calories_burned"] == 580.0
    assert weekly["split_done"]["day_1"] is True
    assert weekly["split_done"]["day_2"] is False
    assert weekly["cardio_count"] == 1

    # Test Past Food History
    history = get_past_food_history(db_session, user_id, limit=5)
    assert len(history) == 2
    assert history[0]["name"] in ["กล้วยหอม 1 ลูก", "ข้าวกะเพราอกไก่"]
