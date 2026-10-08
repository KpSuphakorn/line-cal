"""Unit tests for the current nutrition and workout-program calculations."""

from datetime import datetime, date, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.database import Base
from app.db.models import FoodAnalysisDraft, FoodLog, User
from app.services.fitness import (
    calculate_bmr,
    calculate_tdee,
    get_daily_summary,
    get_history_summary,
    get_or_create_user,
    update_food_log,
    update_user_profile,
    delete_user_account,
)
from app.services.workouts import (
    create_cardio_session,
    create_strength_session,
    list_programs,
    save_cardio_preset,
    save_program,
)
from app.services.workouts import delete_program
from app.services.workouts import update_session
from app.services.food_capture import (
    cancel_capture_result,
    confirm_capture,
    confirm_capture_result,
    create_capture,
    get_editable_capture,
    update_capture,
)
import app.services.food_capture as food_capture_service


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
    programs = list_programs(db_session, user_id)
    push_id = next(program["id"] for program in programs if program["name"] == "Push")
    create_strength_session(db_session, user_id, push_id)
    cardio_preset = save_cardio_preset(db_session, user_id, {
        "name": "เดินชัน",
        "activity": "เดินชัน",
        "duration_min": 40,
    })
    create_cardio_session(db_session, user_id, preset_id=cardio_preset["id"])

    summary = get_daily_summary(db_session, user_id)
    assert summary["target_kcal"] == 2100.0
    assert summary["calories_in"] == 625.0
    assert summary["calories_burned"] > 0
    assert summary["remaining_kcal"] == 1475.0
    assert summary["protein"] == 35.3
    assert len(summary["food_logs"]) == 2
    assert len(summary["workout_logs"]) == 2

def test_cardio_session_requires_preset(db_session):
    user_id = "test_user_cardio_requires_preset"
    complete_profile(db_session, user_id)
    with pytest.raises(ValueError, match="preset_id is required"):
        create_cardio_session(db_session, user_id, preset_id=None)


def test_cardio_time_only_keeps_baseline_met(db_session):
    user_id = "cardio-time-only"
    complete_profile(db_session, user_id)
    preset = save_cardio_preset(db_session, user_id, {"activity": "เดิน", "duration_min": 20})
    session = create_cardio_session(db_session, user_id, preset["id"])
    assert session.estimated_duration_min == 20
    assert session.cardio.met == 3.5
    assert session.estimated_calories == 88.2


def test_cardio_distance_and_duration_determine_walking_speed(db_session):
    user_id = "cardio-distance-time"
    complete_profile(db_session, user_id)
    preset = save_cardio_preset(db_session, user_id, {
        "activity": "เดิน", "duration_min": 20, "distance_km": 1.6, "speed_kmh": 3,
    })
    session = create_cardio_session(db_session, user_id, preset["id"])
    assert preset["speed_kmh"] == 3  # preserve the supplied value; distance and time drive the estimate
    assert session.cardio.met == 3.8
    assert session.cardio.distance_km == 1.6
    assert session.estimated_calories == 95.8


def test_cardio_incline_increases_walking_estimate(db_session):
    user_id = "cardio-incline-estimate"
    complete_profile(db_session, user_id)
    flat = save_cardio_preset(db_session, user_id, {"activity": "เดินชัน", "duration_min": 20, "speed_kmh": 4.8})
    incline = save_cardio_preset(db_session, user_id, {
        "name": "ชัน", "activity": "เดินชัน", "duration_min": 20, "speed_kmh": 4.8, "incline_pct": 8,
    })
    flat_session = create_cardio_session(db_session, user_id, flat["id"])
    incline_session = create_cardio_session(db_session, user_id, incline["id"])
    assert incline_session.cardio.met > flat_session.cardio.met
    assert incline_session.estimated_calories > flat_session.estimated_calories


def test_running_met_uses_published_speed_bands(db_session):
    user_id = "cardio-run-speed-bands"
    complete_profile(db_session, user_id)
    slow = save_cardio_preset(db_session, user_id, {
        "activity": "วิ่ง", "duration_min": 20, "speed_kmh": 5,
    })
    moderate = save_cardio_preset(db_session, user_id, {
        "name": "วิ่งเร็วขึ้น", "activity": "วิ่ง", "duration_min": 20, "speed_kmh": 8.1,
    })
    sprint = save_cardio_preset(db_session, user_id, {
        "name": "วิ่งเร็วมาก", "activity": "วิ่ง", "duration_min": 20, "speed_kmh": 23,
    })
    assert create_cardio_session(db_session, user_id, slow["id"]).cardio.met == 3.3
    assert create_cardio_session(db_session, user_id, moderate["id"]).cardio.met == 8.5
    assert create_cardio_session(db_session, user_id, sprint["id"]).cardio.met == 23


def test_cardio_steps_only_estimate_duration_and_km_take_priority(db_session):
    user_id = "cardio-walking-steps"
    complete_profile(db_session, user_id)
    steps_only = save_cardio_preset(db_session, user_id, {"activity": "เดิน", "steps": 10000})
    session = create_cardio_session(db_session, user_id, steps_only["id"])
    assert steps_only["duration_min"] is None
    assert steps_only["steps"] == 10000
    assert 80 < session.estimated_duration_min < 100
    assert session.cardio.steps == 10000

    both = save_cardio_preset(db_session, user_id, {
        "name": "ระยะทางนำ", "activity": "เดิน", "duration_min": 60, "distance_km": 5, "steps": 10000,
    })
    assert both["distance_km"] == 5
    assert both["steps"] == 10000
    assert both["speed_kmh"] is None  # inferred speed is used only for estimation, not stored as user input


def test_cardio_requires_a_meaningful_metric_and_bounds_derived_values(db_session):
    user_id = "cardio-validation"
    complete_profile(db_session, user_id)
    for data in (
        {"activity": "เดิน"},
        {"activity": "เดิน", "speed_kmh": 5},
        {"activity": "เดินชัน", "incline_pct": 8},
        {"activity": "วิ่ง", "distance_km": 1000, "duration_min": 1},
        {"activity": "เดิน", "duration_min": 20, "steps": 1.5},
    ):
        with pytest.raises(ValueError):
            save_cardio_preset(db_session, user_id, data)


def test_cardio_update_recalculates_auto_estimate_but_preserves_manual_zero(db_session):
    user_id = "cardio-calorie-edit"
    complete_profile(db_session, user_id)
    preset = save_cardio_preset(db_session, user_id, {"activity": "เดิน", "duration_min": 20})
    session = create_cardio_session(db_session, user_id, preset["id"])
    original = session.estimated_calories

    updated = update_session(db_session, user_id, session.id, {
        "cardio": {"duration_min": 20, "distance_km": 1.6},
    })
    assert updated.estimated_calories > original
    assert updated.calories_estimated is True

    updated = update_session(db_session, user_id, session.id, {"estimated_calories": 0})
    assert updated.estimated_calories == 0
    assert updated.calories_estimated is False
    updated = update_session(db_session, user_id, session.id, {"estimated_calories": None})
    assert updated.calories_estimated is True
    assert updated.estimated_calories > 0


def test_cycling_outdoor_uses_measured_speed_and_stationary_ignores_virtual_speed(db_session):
    user_id = "cardio-bike-variants"
    complete_profile(db_session, user_id)
    outdoor = save_cardio_preset(db_session, user_id, {
        "activity": "จักรยาน", "variant": "outdoor_general", "duration_min": 20, "distance_km": 6,
    })
    outdoor_session = create_cardio_session(db_session, user_id, outdoor["id"])
    assert outdoor_session.cardio.met == 6.8
    assert outdoor_session.cardio.activity_type == "จักรยาน"
    assert outdoor_session.cardio.variant == "outdoor_general"

    stationary = save_cardio_preset(db_session, user_id, {
        "name": "จักรยานอยู่กับที่", "activity": "จักรยาน", "variant": "stationary_light",
        "duration_min": 20, "distance_km": 40, "speed_kmh": 50,
    })
    stationary_session = create_cardio_session(db_session, user_id, stationary["id"])
    assert stationary_session.cardio.met == 4.0
    assert stationary_session.cardio.distance_km == 40
    assert stationary_session.cardio.speed_kmh == 50

    with pytest.raises(ValueError, match="เวลาออกกำลังกายจริง"):
        save_cardio_preset(db_session, user_id, {
            "name": "จักรยานไม่มีเวลา", "activity": "จักรยาน", "variant": "stationary_light", "distance_km": 5, "speed_kmh": 20,
        })


def test_swimming_variants_need_duration_and_other_display_name_never_changes_category(db_session):
    user_id = "cardio-swim-other"
    complete_profile(db_session, user_id)
    swim = save_cardio_preset(db_session, user_id, {
        "activity": "ว่ายน้ำ", "variant": "breaststroke_training", "duration_min": 30, "distance_km": 1,
    })
    swim_session = create_cardio_session(db_session, user_id, swim["id"])
    assert swim_session.cardio.met == 10.3
    with pytest.raises(ValueError, match="ระบุเวลา"):
        save_cardio_preset(db_session, user_id, {"name": "ว่ายน้ำไม่ระบุเวลา", "activity": "ว่ายน้ำ", "distance_km": 1})

    other = save_cardio_preset(db_session, user_id, {
        "activity": "อื่นๆ", "custom_name": "เดิน", "variant": "yoga", "duration_min": 30,
    })
    other_session = create_cardio_session(db_session, user_id, other["id"])
    assert other_session.cardio.activity == "เดิน"
    assert other_session.cardio.activity_type == "อื่นๆ"
    assert other_session.cardio.met == 2.3

    with pytest.raises(ValueError, match="ไม่ตรง"):
        save_cardio_preset(db_session, user_id, {"name": "swim invalid variant", "activity": "ว่ายน้ำ", "variant": "yoga", "duration_min": 20})


def test_strength_auto_recalculates_duration_and_manual_calories_are_preserved(db_session):
    user_id = "strength-preserves-manual"
    complete_profile(db_session, user_id)
    program = save_program(db_session, user_id, {"name": "Test", "exercises": [
        {"name": "Squat", "sets": 3, "repetitions": 10},
    ]})
    session = create_strength_session(db_session, user_id, program["id"])
    original_duration = session.estimated_duration_min
    update_session(db_session, user_id, session.id, {
        "exercises": [{"name": "Squat", "sets": 5, "repetitions": 12}],
    })
    assert session.estimated_duration_min > original_duration
    update_session(db_session, user_id, session.id, {"estimated_duration_min": 60})
    manual = update_session(db_session, user_id, session.id, {"estimated_calories": 321})
    edited = update_session(db_session, user_id, session.id, {
        "estimated_duration_min": 60,
        "exercises": [{"name": "Squat", "sets": 6, "repetitions": 12}],
    })
    assert edited.estimated_duration_min == 60
    assert edited.estimated_calories == 321
    assert edited.calories_estimated is False

    duration_program = save_program(db_session, user_id, {"name": "Duration", "exercises": [
        {"name": "Press", "sets": 3, "repetitions": 10},
    ]})
    duration_session = create_strength_session(db_session, user_id, duration_program["id"])
    before = duration_session.estimated_calories
    changed = update_session(db_session, user_id, duration_session.id, {"estimated_duration_min": 50})
    assert changed.estimated_duration_min == 50
    assert changed.estimated_calories != before


def test_user_programs_are_independent_and_editable(db_session):
    user_id = "test_user_programs"
    complete_profile(db_session, user_id)

    programs = list_programs(db_session, user_id)
    assert len(programs) == 3
    assert {program["name"] for program in programs} == {"Push", "Pull", "Legs"}

    push = next(program for program in programs if program["name"] == "Push")
    pec_dec = next(exercise for exercise in push["exercises"] if "pec dec" in exercise["name"].lower())
    assert pec_dec["weight"] == 40.0

    edited_exercises = [
        {**exercise, "weight": 45.0} if exercise["id"] == pec_dec["id"] else exercise
        for exercise in push["exercises"]
    ]
    save_program(db_session, user_id, {"exercises": edited_exercises}, program_id=push["id"])

    refreshed = list_programs(db_session, user_id)
    refreshed_push = next(program for program in refreshed if program["name"] == "Push")
    refreshed_pec_dec = next(exercise for exercise in refreshed_push["exercises"] if "pec dec" in exercise["name"].lower())
    assert refreshed_pec_dec["weight"] == 45.0


def test_food_crud_for_incomplete_profile(db_session):
    user_id = "test_user_food_crud"
    get_or_create_user(db_session, user_id, settings)

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

    updated = update_food_log(db_session, food.id, {"calories": 400.0, "food_name": "ข้าวไข่เจียวไร้น้ำมัน"})
    assert updated is not None
    assert updated.calories == 400.0
    assert updated.food_name == "ข้าวไข่เจียวไร้น้ำมัน"


def test_food_capture_action_results_are_stateful_and_owner_scoped(db_session):
    owner = "capture-service-owner"
    other = "capture-service-other"
    capture = create_capture(db_session, owner, "text", [{"food_name": "ข้าว", "calories": 400}])

    assert cancel_capture_result(db_session, other, capture.token).status == "missing"
    assert confirm_capture_result(db_session, owner, capture.token).status == "confirmed"
    assert confirm_capture_result(db_session, owner, capture.token).status == "already_confirmed"
    assert cancel_capture_result(db_session, owner, capture.token).status == "confirmed"

    cancelled = create_capture(db_session, owner, "text", [{"food_name": "ไข่", "calories": 100}])
    assert cancel_capture_result(db_session, owner, cancelled.token).status == "cancelled"
    assert cancel_capture_result(db_session, owner, cancelled.token).status == "already_cancelled"
    with pytest.raises(HTTPException, match="ยืนยันหรือยกเลิก") as error:
        get_editable_capture(db_session, owner, cancelled.token)
    assert error.value.status_code == 409


@pytest.mark.parametrize("terminal_action", ["confirm", "cancel"])
def test_stale_capture_update_cannot_mutate_after_terminal_action(db_session, terminal_action):
    """A second session's chat action wins over a stale LIFF update."""
    engine = db_session.get_bind()
    sessions = sessionmaker(bind=engine)
    liFF_db = sessions()
    chat_db = sessions()
    try:
        user_id = f"capture-race-{terminal_action}"
        capture = create_capture(liFF_db, user_id, "text", [{"food_name": "ข้าว", "calories": 400}])
        token = capture.token
        original_draft = liFF_db.query(FoodAnalysisDraft).filter_by(capture_id=capture.id).one()

        if terminal_action == "confirm":
            assert confirm_capture(chat_db, user_id, token)
        else:
            assert cancel_capture_result(chat_db, user_id, token).status == "cancelled"

        # The real LIFF request uses a fresh transaction; expire this session's
        # identity map so the update path must observe chat's terminal commit.
        liFF_db.expire_all()
        with pytest.raises(HTTPException, match="no longer editable"):
            update_capture(liFF_db, user_id, token, [{"food_name": "รายการเก่าที่แก้ค้าง", "calories": 1}])

        saved = chat_db.query(type(capture)).filter_by(token=token).one()
        drafts = chat_db.query(FoodAnalysisDraft).filter_by(capture_id=saved.id).all()
        assert saved.status in {"confirmed", "cancelled"}
        assert [draft.id for draft in drafts] == [original_draft.id]
        if terminal_action == "confirm":
            assert chat_db.query(FoodLog).filter_by(capture_id=saved.id, user_id=user_id).count() == 1
        else:
            assert chat_db.query(FoodLog).filter_by(capture_id=saved.id, user_id=user_id).count() == 0
    finally:
        liFF_db.close()
        chat_db.close()


def test_editor_get_uses_parent_lock_for_expiry_transition(db_session, monkeypatch):
    """The expiry mutation is guarded by the same lock as chat actions."""
    owner = "capture-editor-expiry-lock"
    capture = create_capture(db_session, owner, "text", [{"food_name": "ข้าว", "calories": 400}])
    capture.expires_at = datetime.now(timezone.utc)
    db_session.commit()
    calls = []
    original_get = food_capture_service._get_capture

    def tracked_get(db, user_id, token, lock=False):
        calls.append(lock)
        return original_get(db, user_id, token, lock=lock)

    monkeypatch.setattr(food_capture_service, "_get_capture", tracked_get)
    with pytest.raises(HTTPException) as error:
        get_editable_capture(db_session, owner, capture.token)

    assert error.value.status_code == 410
    assert calls == [True]
    saved = db_session.query(type(capture)).filter_by(token=capture.token).one()
    assert saved.status == "cancelled"
    assert saved.cancelled_at is not None


def test_stale_update_expiry_records_cancelled_at(db_session):
    owner = "capture-update-expiry"
    capture = create_capture(db_session, owner, "text", [{"food_name": "ข้าว", "calories": 400}])
    capture.expires_at = datetime.now(timezone.utc)
    db_session.commit()

    with pytest.raises(HTTPException) as error:
        update_capture(db_session, owner, capture.token, [{"food_name": "รายการเก่า", "calories": 1}])

    assert error.value.status_code == 410
    saved = db_session.query(type(capture)).filter_by(token=capture.token).one()
    assert saved.status == "cancelled"
    assert saved.cancelled_at is not None


def test_confirm_wins_before_editor_get_and_keeps_one_log(db_session):
    """Deterministic ordering check; SQLite does not provide true FOR UPDATE concurrency."""
    engine = db_session.get_bind()
    sessions = sessionmaker(bind=engine)
    editor_db = sessions()
    chat_db = sessions()
    try:
        owner = "capture-editor-after-confirm"
        capture = create_capture(editor_db, owner, "text", [{"food_name": "ข้าว", "calories": 400}])
        token = capture.token
        # Emulate the editor having read the draft before the chat action.
        editor_db.query(type(capture)).filter_by(token=token).one()
        assert len(confirm_capture(chat_db, owner, token)) == 1
        editor_db.expire_all()

        with pytest.raises(HTTPException) as error:
            get_editable_capture(editor_db, owner, token)
        assert error.value.status_code == 409
        assert chat_db.query(FoodLog).filter_by(capture_id=capture.id, user_id=owner).count() == 1
    finally:
        editor_db.close()
        chat_db.close()


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

    monthly = get_history_summary(db_session, user_id, "month", date(2026, 9, 20))
    days = {item["date"]: item["calories_in"] for item in monthly["daily_breakdown"]}
    assert days["2026-09-20"] == 100
    assert days["2026-09-19"] == 200


def test_deleting_program_detaches_historical_session(db_session):
    user_id = "program-history"
    complete_profile(db_session, user_id)
    programs = list_programs(db_session, user_id)
    program_id = next(item["id"] for item in programs if item["name"] == "Push")
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


def test_automatic_targets_follow_weight_until_manually_customized(db_session):
    user_id = "automatic-targets"
    update_user_profile(db_session, user_id, {
        "name": "Auto User",
        "gender": "male",
        "age": 30,
        "height_cm": 175,
        "weight_kg": 72,
        "goal": "recomposition",
        "activity_multiplier": 1.45,
    })
    saved = db_session.query(User).filter_by(id=user_id).one()
    initial_kcal = saved.daily_target_kcal
    assert saved.targets_customized is False

    update_user_profile(db_session, user_id, {"weight_kg": 80})
    saved = db_session.query(User).filter_by(id=user_id).one()
    assert saved.daily_target_kcal != initial_kcal
    assert saved.targets_customized is False

    update_user_profile(db_session, user_id, {"daily_target_kcal": 1900})
    saved = db_session.query(User).filter_by(id=user_id).one()
    assert saved.targets_customized is True
    update_user_profile(db_session, user_id, {"weight_kg": 90})
    saved = db_session.query(User).filter_by(id=user_id).one()
    assert saved.daily_target_kcal == 1900

    update_user_profile(db_session, user_id, {"reset_targets": True})
    saved = db_session.query(User).filter_by(id=user_id).one()
    assert saved.targets_customized is False
    assert saved.activity_level == "1.45"


def test_delete_user_account_removes_private_data_and_detaches_webhooks(db_session):
    from app.db.models import (
        CardioPreset,
        FoodAnalysisDraft,
        FoodCapture,
        FoodLog,
        ProcessedWebhook,
        ProgramTemplate,
        WorkoutProgram,
        WorkoutSession,
    )

    user_id = "delete-account-owner"
    complete_profile(db_session, user_id)
    program_id = list_programs(db_session, user_id)[0]["id"]
    create_strength_session(db_session, user_id, program_id)
    save_cardio_preset(db_session, user_id, {"name": "เดิน", "activity": "เดิน", "duration_min": 20})
    capture = FoodCapture(user_id=user_id, token="delete-capture", source="text", status="draft")
    db_session.add(capture)
    db_session.flush()
    db_session.add(FoodAnalysisDraft(capture_id=capture.id, order_num=1, food_name="ข้าว", portion="1 ที่"))
    db_session.add(FoodLog(user_id=user_id, food_name="ข้าว", calories=100))
    db_session.add(ProcessedWebhook(event_id="delete-event", user_id=user_id))
    db_session.commit()
    assert delete_user_account(db_session, user_id) is True

    assert db_session.query(User).filter_by(id=user_id).first() is None
    assert db_session.query(FoodLog).filter_by(user_id=user_id).count() == 0
    assert db_session.query(FoodCapture).filter_by(user_id=user_id).count() == 0
    assert db_session.query(FoodAnalysisDraft).count() == 0
    assert db_session.query(CardioPreset).filter_by(user_id=user_id).count() == 0
    assert db_session.query(WorkoutProgram).filter_by(user_id=user_id).count() == 0
    assert db_session.query(WorkoutSession).filter_by(user_id=user_id).count() == 0
    assert db_session.query(ProcessedWebhook).filter_by(event_id="delete-event").one().user_id is None
    assert db_session.query(ProgramTemplate).count() == 3


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


def test_create_strength_session_survives_concurrent_duplicate_source_event(db_session, monkeypatch):
    """A race that slips past the pre-check must resolve via the unique constraint, not a 500."""
    import app.services.workouts as workouts_module
    from app.db.models import WorkoutSession

    user_id = "strength-race-user"
    complete_profile(db_session, user_id)
    programs = list_programs(db_session, user_id)
    push_id = next(program["id"] for program in programs if program["name"] == "Push")

    winner = create_strength_session(db_session, user_id, push_id, source_event_id="evt-strength-race")

    real_lookup = workouts_module._existing_session_by_source_event
    calls = {"n": 0}

    def flaky_lookup(db, uid, source_event_id):
        calls["n"] += 1
        return None if calls["n"] == 1 else real_lookup(db, uid, source_event_id)

    monkeypatch.setattr(workouts_module, "_existing_session_by_source_event", flaky_lookup)

    loser = create_strength_session(db_session, user_id, push_id, source_event_id="evt-strength-race")

    assert loser.id == winner.id
    assert db_session.query(WorkoutSession).filter_by(
        user_id=user_id, source_event_id="evt-strength-race"
    ).count() == 1


def test_create_cardio_session_survives_concurrent_duplicate_source_event(db_session, monkeypatch):
    import app.services.workouts as workouts_module
    from app.db.models import WorkoutSession

    user_id = "cardio-race-user"
    complete_profile(db_session, user_id)
    preset = save_cardio_preset(db_session, user_id, {
        "name": "เดินชัน",
        "activity": "เดินชัน",
        "duration_min": 40,
    })

    winner = create_cardio_session(db_session, user_id, preset_id=preset["id"], source_event_id="evt-cardio-race")

    real_lookup = workouts_module._existing_session_by_source_event
    calls = {"n": 0}

    def flaky_lookup(db, uid, source_event_id):
        calls["n"] += 1
        return None if calls["n"] == 1 else real_lookup(db, uid, source_event_id)

    monkeypatch.setattr(workouts_module, "_existing_session_by_source_event", flaky_lookup)

    loser = create_cardio_session(db_session, user_id, preset_id=preset["id"], source_event_id="evt-cardio-race")

    assert loser.id == winner.id
    assert db_session.query(WorkoutSession).filter_by(
        user_id=user_id, source_event_id="evt-cardio-race"
    ).count() == 1


def test_seed_user_programs_survives_concurrent_duplicate_seeding(db_session, monkeypatch):
    """Two near-simultaneous first loads after onboarding must not 500 on the race."""
    import app.services.fitness as fitness_module
    from app.services.fitness import seed_user_programs_if_needed
    from app.db.models import WorkoutProgram

    user_id = "seed-race-user"
    complete_profile(db_session, user_id)

    winner = seed_user_programs_if_needed(db_session, user_id)
    assert len(winner) == 3

    # Undo the "programs already exist" fact for exactly one probe so the
    # function proceeds to seed again, colliding with the templates it just
    # created — the same shape as two concurrent first-ever requests.
    real_lookup = fitness_module._existing_user_programs
    calls = {"n": 0}

    def flaky_lookup(db, uid):
        calls["n"] += 1
        return [] if calls["n"] == 1 else real_lookup(db, uid)

    monkeypatch.setattr(fitness_module, "_existing_user_programs", flaky_lookup)

    loser = seed_user_programs_if_needed(db_session, user_id)

    assert {p.id for p in loser} == {p.id for p in winner}
    assert db_session.query(WorkoutProgram).filter_by(user_id=user_id).count() == 3
