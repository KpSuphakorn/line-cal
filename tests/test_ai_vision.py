"""Unit tests for AI vision food analyzer."""
import sys

import pytest

from app.config import settings
from app.services.ai_errors import FoodAnalysisError
from app.services.ai_vision import analyze_food_image


def test_analyze_food_image_mock_fallback():
    """Without a real API key, dev/test mock mode returns a labeled estimate."""
    res = analyze_food_image(b"not-a-real-image")
    assert isinstance(res["items"], list)
    assert len(res["items"]) >= 1
    item = res["items"][0]
    assert item["calories"] > 0


def test_analyze_food_image_raises_on_real_api_failure(monkeypatch):
    """A genuine Gemini Vision failure must surface as an error, never a fabricated answer."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "genuine-real-api-key")

    class _BoomModel:
        def generate_content(self, *args, **kwargs):
            raise RuntimeError("upstream unavailable")

    class _BoomGenAI:
        @staticmethod
        def configure(**kwargs):
            pass

        @staticmethod
        def GenerativeModel(*args, **kwargs):
            return _BoomModel()

    monkeypatch.setitem(sys.modules, "google.generativeai", _BoomGenAI())

    with pytest.raises(FoodAnalysisError):
        analyze_food_image(b"not-a-real-image")
