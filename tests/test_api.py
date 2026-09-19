"""API Integration tests."""
import io
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import init_db

# Initialize tables for tests
init_db()

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["daily_target_kcal"] == 1950.0


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_summary_endpoint():
    response = client.get("/api/summary/user_suphakorn_api")
    assert response.status_code == 200
    data = response.json()
    assert data["target_kcal"] == 1950.0
    assert data["remaining_kcal"] == 1950.0
    assert "food_logs" in data
    assert "workout_logs" in data


def test_preview_dashboard_endpoint():
    response = client.get("/api/preview/dashboard/user_suphakorn_api")
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "bubble"
    assert "DAILY CALORIE BALANCE" in str(data)


def test_simulate_analyze_food():
    # Create a small dummy image in memory
    img = Image.new("RGB", (100, 100), color=(200, 50, 50))
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG")
    img_byte_arr.seek(0)

    response = client.post(
        "/api/simulate/analyze-food",
        files={"file": ("test_food.jpg", img_byte_arr, "image/jpeg")}
    )
    assert response.status_code == 200
    data = response.json()
    assert "analysis" in data
    assert "calories" in data["analysis"]
    assert "flex_preview" in data


def test_workout_editor_web_endpoint():
    response = client.get("/workout-editor")
    assert response.status_code == 200
    assert "Workout Routine" in response.text
    assert "saveAllRoutines" in response.text


def test_user_exercises_api():
    # 1. Get exercises
    user_id = "test_user_web_api"
    response = client.get(f"/api/user/{user_id}/exercises")
    assert response.status_code == 200
    data = response.json()
    assert "day_1" in data
    assert len(data["day_1"]["exercises"]) > 0

    # 2. Save modified exercises
    payload = {
        "day_1": [
            {"name": "Pec dec fly (custom)", "weight": "45 kg", "target": "อกรวม"},
            {"name": "Bench press (custom)", "weight": "25 kg", "target": "อกกลาง"}
        ]
    }
    save_res = client.post(f"/api/user/{user_id}/exercises/save", json=payload)
    assert save_res.status_code == 200
    assert save_res.json()["status"] == "success"

    # 3. Verify changes persisted
    verify_res = client.get(f"/api/user/{user_id}/exercises")
    new_data = verify_res.json()
    assert len(new_data["day_1"]["exercises"]) == 2
    assert new_data["day_1"]["exercises"][0]["name"] == "Pec dec fly (custom)"
    assert new_data["day_1"]["exercises"][0]["weight"] == "45 kg"

