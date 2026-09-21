"""API Integration tests."""
import io
from datetime import datetime, timedelta, timezone
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import init_db
from app.auth import AuthenticatedUser, get_current_user
from app.services.food_capture import create_capture

# Initialize tables for tests
init_db()

client = TestClient(app)


@pytest.fixture
def as_user():
    """Override only the verified LINE identity; never bypass ownership checks."""
    def _as_user(user_id: str):
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(subject=user_id)

    yield _as_user
    app.dependency_overrides.pop(get_current_user, None)


def complete_profile(as_user, user_id, **targets):
    """Set up a real user profile before tests mutate food or workout data."""
    as_user(user_id)
    payload = {
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
    payload.update(targets)
    response = client.put("/api/me/profile", json=payload)
    assert response.status_code == 200
    assert response.json()["profile"]["profile_completed"] is True
    return response.json()["profile"]


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["version"] == "2.0.0"
    assert "daily_target_kcal" not in data


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_summary_endpoint(as_user):
    user_id = "user_suphakorn_api"
    as_user(user_id)
    response = client.get("/api/me/today")
    assert response.status_code == 409
    complete_profile(as_user, user_id)
    response = client.get("/api/me/today")
    assert response.status_code == 200
    data = response.json()
    assert data["target_kcal"] == 2100.0
    assert data["remaining_kcal"] == 2100.0
    assert "food_logs" in data
    assert "workout_logs" in data


def test_simulate_analyze_food(as_user):
    user_id = "test_simulator"
    as_user(user_id)
    # Create a small dummy image in memory
    img = Image.new("RGB", (100, 100), color=(200, 50, 50))
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG")
    img_byte_arr.seek(0)

    blocked = client.post(
        "/api/simulate/analyze-food",
        files={"file": ("test_food.jpg", img_byte_arr, "image/jpeg")}
    )
    assert blocked.status_code == 409

    complete_profile(as_user, user_id)
    img_byte_arr.seek(0)
    response = client.post(
        "/api/simulate/analyze-food",
        files={"file": ("test_food.jpg", img_byte_arr, "image/jpeg")}
    )
    assert response.status_code == 200
    data = response.json()
    assert "analysis" in data
    assert data["analysis"]["items"][0]["calories"] > 0
    assert "flex_preview" in data


def test_webapp_dashboard_endpoint():
    response = client.get("/webapp")
    assert response.status_code == 200
    assert "<title>LINE Cal</title>" in response.text
    assert "bottom-nav" in response.text
    assert "100dvh" in response.text
    assert "modal-actions" in response.text
    assert "body.modal-open" in response.text
    assert "input.dataset.field=options.key" in response.text
    assert "exercise-details" in response.text
    assert "querySelector(`[data-field=\"${key}\"]`)" in response.text
    assert "node('div',message,'toast')" in response.text
    assert "calorie-ring" in response.text
    assert "progress-fill" in response.text
    assert "ออกกำลังกาย (ประมาณ)" in response.text
    assert "นั่งเป็นส่วนใหญ่" in response.text
    assert "รักษาน้ำหนัก / ปรับสัดส่วน" in response.text
    assert "iconPaths" in response.text
    assert "calendar-legend" in response.text
    assert "/api/me/history?period=" in response.text
    assert "/api/me/cardio-presets" in response.text
    assert "เลือกกิจกรรมวันนี้" in response.text
    assert "todayCardioPresetRow" not in response.text
    assert "body.append(pace)" in response.text
    assert "[activity,custom,duration,incline,speed,distance,pace].forEach" not in response.text
    assert "openCardio(" not in response.text
    assert "cardio=1" not in response.text
    assert "บันทึก Cardio" not in response.text
    assert "const CARDIO_CHOICES" in response.text
    assert "knownActivity?savedActivity:'อื่นๆ','select'" in response.text
    assert "button('บันทึกวันนี้',()=>logProgram" in response.text
    assert "history-controls" in response.text
    assert "program-footer" in response.text
    assert "node('fieldset'" in response.text
    assert "if(!presetResponse.ok)throw Error" in response.text
    assert "ลองอีกครั้ง" in response.text
    assert "LINE ยืนยันตัวตนไม่ผ่าน" in response.text
    assert "history-chart" in response.text
    assert "เลือกวันที่ต้องการดูรายละเอียด" in response.text
    assert "target-settings" in response.text
    assert "ปรับเป้าหมายเอง (ไม่จำเป็น)" in response.text
    assert "target-settings summary::after" in response.text
    assert "target-settings[open] summary::after" in response.text
    assert "min-height:44px" in response.text
    assert ".card>.button{margin-top:8px}" in response.text
    assert "'section-intro'),button('สร้างรายการคาร์ดิโอ'" in response.text
    assert "เพซประมาณ" in response.text
    assert "aria-pressed" in response.text
    assert "aria-current" in response.text
    assert "profile?.profile_completed" in response.text
    assert "const PROFILE_REQUIRED_MESSAGE='กรุณาตั้งค่าโปรไฟล์ให้ครบก่อนเริ่มใช้งาน'" in response.text
    assert "if(!profileRequired())return" in response.text
    assert "async function loadCapture(captureToken){if(!profileRequired())return;" in response.text
    assert "รายการอาหารนี้ยืนยันหรือยกเลิกไปแล้ว จึงแก้ไขไม่ได้" in response.text
    assert "const cancelResponse=await api" in response.text
    assert "if(!cancelResponse.ok){showToast(await apiError(cancelResponse));return}" in response.text
    assert "sessionResponse.status===409" in response.text
    assert "presetResponse.status===409" in response.text
    for emoji in ("📊", "📅", "🏋", "👤", "🍽", "🏃"):
        assert emoji not in response.text
    assert "class=\"tab-nav\"" not in response.text
    assert "reset_targets" in response.text
    assert "บันทึกเป้าหมาย" in response.text
    assert "/api/me/account" in response.text
    assert "ลบข้อมูลบัญชี" in response.text
    assert "โหมดคำนวณอัตโนมัติ" in response.text
    assert "โหมดกำหนดเอง" in response.text
    assert "กลับไปใช้ค่าคำนวณอัตโนมัติ" in response.text
    assert "/api/user/" not in response.text


def test_user_today_api(as_user):
    user_id = "test_user_webapp"
    complete_profile(as_user, user_id)
    # 1. Today summary
    res_today = client.get("/api/me/today")
    assert res_today.status_code == 200
    today_data = res_today.json()
    assert today_data["target_kcal"] == 2100.0


def test_food_capture_api_keeps_confirm_idempotent_and_cancel_statuses(as_user):
    from app.db.database import SessionLocal
    from app.db.models import FoodLog

    user_id = "capture-api-owner"
    complete_profile(as_user, user_id)
    db = SessionLocal()
    capture = create_capture(db, user_id, "text", [{"food_name": "ข้าว", "calories": 400}])
    token = capture.token
    db.close()

    first_confirm = client.post(f"/api/me/food-captures/{token}/confirm")
    second_confirm = client.post(f"/api/me/food-captures/{token}/confirm")
    assert first_confirm.status_code == second_confirm.status_code == 200
    assert first_confirm.json()["entry_ids"] == second_confirm.json()["entry_ids"]

    db = SessionLocal()
    assert db.query(FoodLog).filter_by(user_id=user_id, capture_id=capture.id).count() == 1
    db.close()

    cancel_confirmed = client.post(f"/api/me/food-captures/{token}/cancel")
    assert cancel_confirmed.status_code == 409
    assert "ยืนยันแล้ว" in cancel_confirmed.json()["detail"]

    db = SessionLocal()
    cancelled = create_capture(db, user_id, "text", [{"food_name": "ไข่", "calories": 100}])
    cancelled_token = cancelled.token
    db.close()
    assert client.post(f"/api/me/food-captures/{cancelled_token}/cancel").status_code == 200
    assert client.post(f"/api/me/food-captures/{cancelled_token}/cancel").status_code == 200
    assert client.get(f"/api/me/food-captures/{cancelled_token}").status_code == 409


def test_food_capture_api_rejects_expired_and_cross_user_editor_access(as_user):
    from app.db.database import SessionLocal

    owner = "capture-editor-owner"
    other = "capture-editor-other"
    complete_profile(as_user, owner)
    db = SessionLocal()
    expired = create_capture(db, owner, "text", [{"food_name": "ข้าว", "calories": 400}])
    expired.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    expired_token = expired.token
    cross_user = create_capture(db, owner, "text", [{"food_name": "แกง", "calories": 200}])
    cross_token = cross_user.token
    db.close()

    assert client.get(f"/api/me/food-captures/{expired_token}").status_code == 410

    complete_profile(as_user, other)
    other_get = client.get(f"/api/me/food-captures/{cross_token}")
    other_cancel = client.post(f"/api/me/food-captures/{cross_token}/cancel")
    assert other_get.status_code == other_cancel.status_code == 404

    db = SessionLocal()
    assert db.query(type(cross_user)).filter_by(token=cross_token).one().status == "draft"
    db.close()



def test_food_update_and_delete_api(as_user):
    from app.db.database import SessionLocal
    from app.db.models import FoodLog

    db = SessionLocal()
    user_id = "test_user_food_crud"
    complete_profile(as_user, user_id)
    new_food = FoodLog(
        user_id=user_id,
        food_name="ข้าวมันไก่",
        portion="1 จาน",
        calories=600.0,
        protein=25.0,
        carbs=70.0,
        fat=22.0
    )
    db.add(new_food)
    db.commit()
    db.refresh(new_food)
    food_id = new_food.id
    db.close()

    # 1. Update food log
    update_res = client.put(
        f"/api/me/food/{food_id}",
        json={"calories": 550.0, "protein": 28.0, "food_name": "ข้าวมันไก่ไม่เอาหนัง"}
    )
    assert update_res.status_code == 200
    assert update_res.json()["status"] == "success"

    # 2. Delete food log
    del_res = client.delete(f"/api/me/food/{food_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"


def test_workout_crud_api(as_user):
    user_id = "test_user_workout_api"
    complete_profile(as_user, user_id)
    programs = client.get("/api/me/workout-programs")
    assert programs.status_code == 200
    program_id = programs.json()["programs"][0]["id"]

    log_res = client.post("/api/me/workout-sessions", json={"program_id": program_id})
    assert log_res.status_code == 200
    data = log_res.json()
    assert data["type"] == "strength"
    assert data["program_id"] == program_id
    workout_id = data["id"]
    assert data["estimated_duration_min"] > 0
    assert data["estimated_calories"] > 0

    update_res = client.put(f"/api/me/workout-sessions/{workout_id}", json={
        "name": "Push (Updated)",
        "estimated_duration_min": 75,
        "estimated_calories": 380,
    })
    assert update_res.status_code == 200
    update_data = update_res.json()
    assert update_data["name"] == "Push (Updated)"
    assert update_data["estimated_duration_min"] == 75
    assert update_data["estimated_calories"] == 380

    del_res = client.delete(f"/api/me/workout-sessions/{workout_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"


def test_profile_custom_macros_api(as_user):
    user_id = "test_user_custom_macros"
    as_user(user_id)

    # 1. Update profile with custom target macros
    res = client.put(
        "/api/me/profile",
        json={
            "name": "Custom User",
            "gender": "female",
            "age": 24,
            "height_cm": 160,
            "weight_kg": 55,
            "goal": "cutting",
            "activity_multiplier": 1.45,
            "daily_target_kcal": 2100.0,
            "target_protein_g": 110.0,
            "target_carbs_g": 240.0,
            "target_fat_g": 60.0
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    profile = data["profile"]
    assert profile["profile_completed"] is True
    assert profile["daily_target_kcal"] == 2100.0
    assert profile["target_protein_g"] == 110.0
    assert profile["target_carbs_g"] == 240.0
    assert profile["target_fat_g"] == 60.0


def test_profile_target_override_contract(as_user):
    user_id = "test_target_override_contract"
    complete_profile(as_user, user_id)
    update = client.put("/api/me/profile", json={
        "daily_target_kcal": 1900,
        "target_protein_g": 120,
        "target_carbs_g": 200,
        "target_fat_g": 50,
    })
    assert update.status_code == 200
    assert update.json()["profile"]["daily_target_kcal"] == 1900

    negative = client.put("/api/me/profile", json={"target_protein_g": -1})
    assert negative.status_code == 422

    reset = client.put("/api/me/profile", json={"reset_targets": True})
    assert reset.status_code == 200
    assert reset.json()["profile"]["daily_target_kcal"] != 1900


def test_profile_partial_update_does_not_reset_activity_or_auto_targets(as_user):
    user_id = "partial-profile-update"
    as_user(user_id)
    response = client.put("/api/me/profile", json={
        "name": "Partial User",
        "gender": "male",
        "age": 30,
        "height_cm": 175,
        "weight_kg": 72,
        "goal": "recomposition",
        "activity_multiplier": 1.55,
    })
    assert response.status_code == 200
    initial = response.json()["profile"]
    changed = client.put("/api/me/profile", json={"weight_kg": 80})
    assert changed.status_code == 200
    updated = changed.json()["profile"]
    assert updated["activity_level"] == initial["activity_level"] == "1.55"
    assert updated["daily_target_kcal"] != initial["daily_target_kcal"]


def test_account_delete_is_owner_scoped_and_resets_identity(as_user):
    user_id = "account-delete-api"
    complete_profile(as_user, user_id)
    assert client.delete("/api/me/account").json() == {"status": "deleted"}
    profile = client.get("/api/me/profile")
    assert profile.status_code == 200
    assert profile.json()["profile_completed"] is False

    as_user("account-delete-other")
    assert client.delete("/api/me/account").status_code == 200


def test_protected_api_requires_authentication():
    response = client.get("/api/me/today")
    assert response.status_code == 401


def test_legacy_user_id_routes_are_removed(as_user):
    as_user("line-owner-a")
    for path in (
        "/api/summary/line-owner-a",
        "/api/user/line-owner-a/today",
        "/api/user/line-owner-a/monthly",
        "/api/user/line-owner-a/profile",
        "/api/preview/dashboard/line-owner-a",
    ):
        assert client.get(path).status_code == 404


def test_food_crud_is_tenant_scoped_and_partial_updates_preserve_macros(as_user):
    from app.db.database import SessionLocal
    from app.db.models import FoodLog

    db = SessionLocal()
    complete_profile(as_user, "food-owner-b")
    food = FoodLog(
        user_id="food-owner-b",
        food_name="ข้าวผัด",
        portion="1 จาน",
        calories=500.0,
        protein=20.0,
        carbs=65.0,
        fat=18.0,
    )
    db.add(food)
    db.commit()
    db.refresh(food)
    food_id = food.id
    db.close()

    complete_profile(as_user, "food-owner-a")
    update_other = client.put(f"/api/me/food/{food_id}", json={"calories": 1})
    delete_other = client.delete(f"/api/me/food/{food_id}")
    assert update_other.status_code == 404
    assert delete_other.status_code == 404

    # The owner can update one field without zeroing omitted macro values.
    as_user("food-owner-b")
    partial = client.put(f"/api/me/food/{food_id}", json={"calories": 450})
    assert partial.status_code == 200
    db = SessionLocal()
    saved = db.query(FoodLog).filter(FoodLog.id == food_id).one()
    assert saved.calories == 450.0
    assert saved.protein == 20.0
    assert saved.carbs == 65.0
    assert saved.fat == 18.0
    db.close()


@pytest.mark.parametrize("payload", [{"calories": -1}, {"calories": "NaN"}])
def test_food_payload_rejects_negative_and_non_finite_values(as_user, payload):
    as_user("validation-owner")
    response = client.put("/api/me/food/999999", json=payload)
    assert response.status_code == 422


def test_monthly_api_rejects_invalid_month(as_user):
    as_user("monthly-validation-owner")
    response = client.get("/api/me/monthly?year=2026&month=13")
    assert response.status_code == 404


def test_cardio_presets_are_owned_and_snapshot_sessions(as_user):
    user_id = "cardio-preset-owner"
    complete_profile(as_user, user_id)
    created = client.post("/api/me/cardio-presets", json={
        "name": "เดินชันหลังเลิกงาน",
        "activity": "เดินชัน",
        "duration_min": 30,
        "incline_pct": 8,
    })
    assert created.status_code == 200
    preset = created.json()
    assert preset["duration_min"] == 30
    assert client.post("/api/me/cardio-presets", json={
        "name": "กิจกรรมมั่ว",
        "activity": "ลอยตัว",
        "duration_min": 20,
    }).status_code == 422

    logged = client.post("/api/me/workout-sessions/cardio", json={"preset_id": preset["id"]})
    assert logged.status_code == 200
    assert logged.json()["cardio"]["duration_min"] == 30

    changed = client.put(f"/api/me/cardio-presets/{preset['id']}", json={
        "name": "เดินชันหลังเลิกงาน",
        "activity": "เดินชัน",
        "duration_min": 45,
        "incline_pct": 10,
    })
    assert changed.status_code == 200
    assert changed.json()["duration_min"] == 45
    assert client.get(f"/api/me/workout-sessions/{logged.json()['id']}").json()["cardio"]["duration_min"] == 30

    complete_profile(as_user, "cardio-preset-other")
    assert client.put(f"/api/me/cardio-presets/{preset['id']}", json={
        "name": "ขโมย",
        "activity": "วิ่ง",
        "duration_min": 10,
    }).status_code == 404


def test_cardio_session_create_requires_preset(as_user):
    user_id = "cardio-create-requires-preset"
    complete_profile(as_user, user_id)
    response = client.post("/api/me/workout-sessions/cardio", json={
        "activity": "เดิน",
        "duration_min": 20,
    })
    assert response.status_code == 422


def test_cardio_preset_name_defaults_to_activity(as_user):
    user_id = "cardio-preset-derived-name"
    complete_profile(as_user, user_id)
    response = client.post("/api/me/cardio-presets", json={
        "activity": "เดิน",
        "duration_min": 20,
    })
    assert response.status_code == 200
    assert response.json()["name"] == "เดิน"


def test_cardio_session_update_preserves_other_activity_name(as_user):
    user_id = "cardio-session-other-update"
    complete_profile(as_user, user_id)
    preset = client.post("/api/me/cardio-presets", json={
        "activity": "อื่นๆ",
        "custom_name": "กระโดดเชือก",
        "duration_min": 20,
    }).json()
    session = client.post("/api/me/workout-sessions/cardio", json={"preset_id": preset["id"]}).json()

    updated = client.put(f"/api/me/workout-sessions/{session['id']}", json={
        "cardio": {"activity": "อื่นๆ", "custom_name": "เต้น", "duration_min": 25},
    })
    assert updated.status_code == 200
    assert updated.json()["cardio"]["activity"] == "เต้น"

    retained = client.put(f"/api/me/workout-sessions/{session['id']}", json={
        "cardio": {"duration_min": 30},
    })
    assert retained.status_code == 200
    assert retained.json()["cardio"]["activity"] == "เต้น"


def test_cardio_session_update_clears_fields_invalid_for_new_activity(as_user):
    user_id = "cardio-session-clears-stale-fields"
    complete_profile(as_user, user_id)
    preset = client.post("/api/me/cardio-presets", json={
        "activity": "เดินชัน",
        "duration_min": 30,
        "incline_pct": 8,
        "speed_kmh": 5,
    }).json()
    session = client.post("/api/me/workout-sessions/cardio", json={"preset_id": preset["id"]}).json()
    assert session["cardio"]["incline_pct"] == 8
    assert session["cardio"]["speed_kmh"] == 5

    updated = client.put(f"/api/me/workout-sessions/{session['id']}", json={
        "cardio": {"activity": "เดิน", "duration_min": 25},
    })
    assert updated.status_code == 200
    assert updated.json()["cardio"] == {
        "activity": "เดิน",
        "duration_min": 25,
        "incline_pct": None,
        "speed_kmh": None,
        "distance_km": None,
        "met": 3.5,
    }

    listed = client.get("/api/me/workout-sessions").json()["sessions"]
    saved = next(item for item in listed if item["id"] == session["id"])
    assert saved["cardio"]["incline_pct"] is None
    assert saved["cardio"]["speed_kmh"] is None
    assert saved["cardio"]["distance_km"] is None


def test_history_periods_are_bounded_and_directly_selectable(as_user):
    user_id = "history-period-owner"
    complete_profile(as_user, user_id)
    week = client.get("/api/me/history?period=week&anchor=2026-09-20")
    assert week.status_code == 200
    assert week.json()["start_date"] == "2026-09-14"
    assert len(week.json()["daily_breakdown"]) == 7
    month = client.get("/api/me/history?period=month&anchor=2026-09-20")
    assert month.status_code == 200
    assert month.json()["start_date"] == "2026-09-01"
    assert month.json()["end_date"] == "2026-09-30"
    assert len(month.json()["daily_breakdown"]) == 30


def test_history_workout_details_use_today_session_display_fields_and_dynamic_years(as_user):
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    from app.db.database import SessionLocal
    from app.db.models import FoodLog

    user_id = "history-workout-details"
    current_year = datetime.now(ZoneInfo("Asia/Bangkok")).year
    complete_profile(as_user, user_id)
    program_id = client.get("/api/me/workout-programs").json()["programs"][0]["id"]
    strength = client.post(
        "/api/me/workout-sessions",
        json={"program_id": program_id, "occurred_at": f"{current_year}-06-10T10:00:00Z"},
    ).json()
    preset = client.post("/api/me/cardio-presets", json={
        "activity": "เดิน",
        "duration_min": 25,
    }).json()
    cardio = client.post(
        "/api/me/workout-sessions/cardio",
        json={"preset_id": preset["id"], "occurred_at": f"{current_year}-06-11T10:00:00Z"},
    ).json()

    db = SessionLocal()
    db.add(FoodLog(
        user_id=user_id,
        food_name="ข้อมูลปีเก่า",
        calories=100,
        logged_at=datetime(2023, 6, 10, 10, tzinfo=timezone.utc),
    ))
    db.add(FoodLog(
        user_id=user_id,
        food_name="ข้อมูลปีคั่นกลาง",
        calories=100,
        logged_at=datetime(2025, 6, 10, 10, tzinfo=timezone.utc),
    ))
    db.commit()
    db.close()

    history = client.get(f"/api/me/history?period=month&anchor={current_year}-06-01")
    assert history.status_code == 200
    data = history.json()
    assert data["available_years"] == list(range(2023, current_year + 1))
    sessions = {
        item["id"]: item
        for day in data["daily_breakdown"]
        for item in day["workout_logs"]
    }
    for session in (strength, cardio):
        assert sessions[session["id"]]["estimated_duration_min"] == session["estimated_duration_min"]
        assert sessions[session["id"]]["estimated_calories"] == session["estimated_calories"]


def test_webhook_acknowledges_before_running_slow_handlers(monkeypatch):
    """LINE must get its 200 without waiting on the AI analysis behind it."""
    import asyncio
    import base64
    import hashlib
    import hmac
    from fastapi import BackgroundTasks

    from app.config import settings
    import app.main as main_module

    calls = []
    monkeypatch.setattr(main_module, "handle_line_events", lambda events, db: calls.append(events))

    body = '{"events":[],"destination":"x"}'
    signature = base64.b64encode(
        hmac.new(settings.LINE_CHANNEL_SECRET.encode(), body.encode(), hashlib.sha256).digest()
    ).decode()

    class _Request:
        async def body(self):
            return body.encode()

    background_tasks = BackgroundTasks()
    response = asyncio.run(
        main_module.line_webhook(_Request(), background_tasks, x_line_signature=signature)
    )

    assert response.status_code == 200
    # The response is ready while the work is still only queued.
    assert calls == []
    assert len(background_tasks.tasks) == 1

    asyncio.run(background_tasks())
    assert calls == [[]]
