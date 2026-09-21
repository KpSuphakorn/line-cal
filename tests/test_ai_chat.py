"""Unit tests for AI chat food parser."""
import sys

import pytest

from app.config import settings
from app.services.ai_chat import parse_food_text
from app.services.ai_errors import FOOD_MODELS, FoodAnalysisError


def test_parse_food_text_fallback():
    """Without a real API key, dev/test mock mode returns a labeled estimate."""
    res = parse_food_text("กิน ข้าวมันไก่ต้ม")
    assert isinstance(res["items"], list)
    assert len(res["items"]) == 1
    item = res["items"][0]
    assert item["food_name"] == "ข้าวมันไก่ต้ม"
    assert item["calories"] > 0
    assert item["protein"] >= 0
    assert item["carbs"] >= 0
    assert item["fat"] >= 0


def test_parse_food_text_raises_on_real_api_failure(monkeypatch, boom_genai):
    """A genuine Gemini failure must surface as an error, never a fabricated answer."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "genuine-real-api-key")
    monkeypatch.setitem(sys.modules, "google.generativeai", boom_genai)

    with pytest.raises(FoodAnalysisError):
        parse_food_text("กิน ข้าวมันไก่ต้ม")


def test_parse_food_text_never_uses_a_latest_alias():
    """A "-latest" alias can silently repoint to a low-quota preview model."""
    assert all("latest" not in name for name in FOOD_MODELS)
    assert len(FOOD_MODELS) >= 2


def test_parse_food_text_falls_back_to_next_pinned_model_on_quota_error(monkeypatch, flaky_genai_factory):
    """A 429/quota failure on the first pinned model must retry the next one, not give up."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "genuine-real-api-key")
    genai = flaky_genai_factory(FOOD_MODELS[0], [{"food_name": "ข้าวผัด", "calories": 300}])
    monkeypatch.setitem(sys.modules, "google.generativeai", genai)

    res = parse_food_text("กิน ข้าวผัด")
    assert res["items"][0]["food_name"] == "ข้าวผัด"
