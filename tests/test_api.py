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
