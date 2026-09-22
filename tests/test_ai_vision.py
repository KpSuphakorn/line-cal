"""Unit tests for AI vision food analyzer."""
import io
import json
import sys

import pytest
from PIL import Image

from app.config import settings
from app.services import ai_errors
from app.services.ai_errors import FoodAnalysisError
from app.services.ai_vision import analyze_food_image


def _tiny_png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


def _genai_returning(items):
    """A fake google.generativeai module whose model returns exactly `items`."""
    class _Response:
        text = json.dumps({"items": items})

    class _Model:
        def generate_content(self, *args, **kwargs):
            return _Response()

    class _FakeGenAI:
        @staticmethod
        def configure(**kwargs):
            pass

        @staticmethod
        def GenerativeModel(*args, **kwargs):
            return _Model()

    return _FakeGenAI()


def test_analyze_food_image_mock_fallback():
    """Without a real API key, dev/test mock mode returns a labeled estimate."""
    res = analyze_food_image(b"not-a-real-image")
    assert isinstance(res["items"], list)
    assert len(res["items"]) >= 1
    item = res["items"][0]
    assert item["calories"] > 0


def test_analyze_food_image_raises_on_real_api_failure(monkeypatch, boom_genai):
    """A genuine Gemini Vision failure must surface as an error, never a fabricated answer."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "genuine-real-api-key")
    monkeypatch.setitem(sys.modules, "google.generativeai", boom_genai)

    with pytest.raises(FoodAnalysisError):
        analyze_food_image(b"not-a-real-image")


def test_analyze_food_image_falls_back_to_next_pinned_model_on_quota_error(monkeypatch, flaky_genai_factory):
    """A 429/quota failure on the first pinned model must retry the next one, not give up."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "genuine-real-api-key")
    monkeypatch.setattr(ai_errors, "FOOD_MODELS", ("exhausted-model", "spare-model"))
    genai = flaky_genai_factory("exhausted-model", [{"food_name": "ไข่เจียว", "calories": 200}])
    monkeypatch.setitem(sys.modules, "google.generativeai", genai)

    res = analyze_food_image(_tiny_png_bytes())
    assert res["items"][0]["food_name"] == "ไข่เจียว"


def test_components_on_the_same_plate_become_one_item(monkeypatch):
    """Rice, chicken and a fried egg on one plate is one menu item, not three."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "genuine-real-api-key")
    genai = _genai_returning([
        {"plate": 1, "food_name": "ข้าวสวย", "calories": 240, "protein": 4, "carbs": 53, "fat": 0.4, "confidence": 0.8},
        {"plate": 1, "food_name": "ไก่ผัดกะเพรา", "calories": 380, "protein": 28, "carbs": 10, "fat": 24, "confidence": 0.6},
        {"plate": 1, "food_name": "ไข่ดาว", "calories": 120, "protein": 7, "carbs": 1, "fat": 10, "confidence": 0.7},
    ])
    monkeypatch.setitem(sys.modules, "google.generativeai", genai)

    res = analyze_food_image(_tiny_png_bytes())

    assert len(res["items"]) == 1
    item = res["items"][0]
    assert item["calories"] == 740.0
    assert item["protein"] == 39.0
    assert item["confidence"] == 0.6
    assert "ไข่ดาว" in item["food_name"]


def test_two_plates_in_one_photo_stay_two_items(monkeypatch):
    """A rice plate and a separate glass of juice are two menu items."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "genuine-real-api-key")
    genai = _genai_returning([
        {"plate": 1, "food_name": "ข้าวสวย", "calories": 240},
        {"plate": 1, "food_name": "ไก่ผัดกะเพรา", "calories": 380},
        {"plate": 2, "food_name": "น้ำส้มคั้น", "calories": 110},
    ])
    monkeypatch.setitem(sys.modules, "google.generativeai", genai)

    res = analyze_food_image(_tiny_png_bytes())

    assert len(res["items"]) == 2
    assert res["items"][0]["calories"] == 620.0
    assert res["items"][1]["food_name"] == "น้ำส้มคั้น"
    assert res["items"][1]["calories"] == 110


def test_missing_plate_numbers_do_not_get_merged_together(monkeypatch):
    """A defensive fallback: without a plate tag, items stay separate rather than
    silently combining into one row with the wrong totals."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "genuine-real-api-key")
    genai = _genai_returning([
        {"food_name": "ข้าวผัด", "calories": 400},
        {"food_name": "น้ำเปล่า", "calories": 0},
    ])
    monkeypatch.setitem(sys.modules, "google.generativeai", genai)

    res = analyze_food_image(_tiny_png_bytes())

    assert [item["food_name"] for item in res["items"]] == ["ข้าวผัด", "น้ำเปล่า"]
