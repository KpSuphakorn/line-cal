"""Unit tests for AI vision food analyzer."""
import io
import sys

import pytest
from PIL import Image

from app.config import settings
from app.services.ai_errors import FOOD_MODELS, FoodAnalysisError
from app.services.ai_vision import analyze_food_image


def _tiny_png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


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
    genai = flaky_genai_factory(FOOD_MODELS[0], [{"food_name": "ไข่เจียว", "calories": 200}])
    monkeypatch.setitem(sys.modules, "google.generativeai", genai)

    res = analyze_food_image(_tiny_png_bytes())
    assert res["items"][0]["food_name"] == "ไข่เจียว"
