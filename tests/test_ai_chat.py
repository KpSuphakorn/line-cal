"""Unit tests for AI chat food parser."""
import json
import sys

import pytest

from app.config import settings
from app.services.ai_chat import parse_food_text
from app.services import ai_errors
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
    assert FOOD_MODELS
    assert all("latest" not in name for name in FOOD_MODELS)


def test_parse_food_text_falls_back_to_next_pinned_model_on_quota_error(monkeypatch, flaky_genai_factory):
    """FOOD_MODELS is one model today, but the chain has to still work when a spare is added back."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "genuine-real-api-key")
    monkeypatch.setattr(ai_errors, "FOOD_MODELS", ("exhausted-model", "spare-model"))
    genai = flaky_genai_factory("exhausted-model", [{"food_name": "ข้าวผัด", "calories": 300}])
    monkeypatch.setitem(sys.modules, "google.generativeai", genai)

    res = parse_food_text("กิน ข้าวผัด")

    assert res["items"][0]["food_name"] == "ข้าวผัด"
    assert [call["model"] for call in genai.calls] == ["exhausted-model", "spare-model"]


def test_parse_food_text_does_not_let_the_sdk_sleep_and_retry(monkeypatch, flaky_genai_factory):
    """A 429 must move to the next model immediately, not sleep out LINE's webhook window."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "genuine-real-api-key")
    genai = flaky_genai_factory("a-model-not-in-the-chain", [{"food_name": "ข้าวผัด", "calories": 300}])
    monkeypatch.setitem(sys.modules, "google.generativeai", genai)

    parse_food_text("กิน ข้าวผัด")

    assert genai.calls, "expected generate_content to be called"
    for call in genai.calls:
        options = call["request_options"]
        assert options["retry"] is None
        assert options["timeout"] > 0


def _genai_returning(items):
    """A fake google.generativeai module whose model returns exactly `items`."""
    class _Response:
        text = json.dumps({"items": items})

    class _Model:
        def __init__(self, name):
            self.name = name

        def generate_content(self, contents, *args, **kwargs):
            _FakeGenAI.prompts.append(contents)
            return _Response()

    class _FakeGenAI:
        prompts: list = []

        @staticmethod
        def configure(**kwargs):
            pass

        @staticmethod
        def GenerativeModel(name, *args, **kwargs):
            return _Model(name)

    _FakeGenAI.prompts = []
    return _FakeGenAI()


def test_one_dish_stays_one_item_even_if_the_model_splits_it(monkeypatch):
    """"ข้าวเนื้อทอดผัดพริกเกลือไข่ข้น" is one plate the user ordered, not three rows."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "genuine-real-api-key")
    genai = _genai_returning([
        {"food_name": "ข้าวสวย", "calories": 240, "protein": 4, "carbs": 53, "fat": 0.4, "confidence": 0.8},
        {"food_name": "เนื้อทอดผัดพริกเกลือ", "calories": 420, "protein": 28, "carbs": 12, "fat": 28, "confidence": 0.6},
        {"food_name": "ไข่ข้น", "calories": 180, "protein": 9, "carbs": 2, "fat": 15, "confidence": 0.7},
    ])
    monkeypatch.setitem(sys.modules, "google.generativeai", genai)

    res = parse_food_text("กิน ข้าวเนื้อทอดผัดพริกเกลือไข่ข้น")

    assert len(res["items"]) == 1
    item = res["items"][0]
    assert item["food_name"] == "ข้าวเนื้อทอดผัดพริกเกลือไข่ข้น"
    assert item["calories"] == 840.0
    assert item["protein"] == 41.0
    assert item["confidence"] == 0.6
    assert "ไข่ข้น" in item["notes"]


def test_plus_separator_keeps_each_part_as_its_own_item(monkeypatch):
    """The user decides the item count with "+", not the model."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "genuine-real-api-key")
    returned = [
        {"food_name": "ข้าวมันไก่", "calories": 580},
        {"food_name": "น้ำส้ม", "calories": 110},
        {"food_name": "สลัดจานเล็ก", "calories": 90},
    ]
    genai = _genai_returning(returned)
    monkeypatch.setitem(sys.modules, "google.generativeai", genai)

    res = parse_food_text("กิน ข้าวมันไก่ + น้ำส้ม + สลัดจานเล็ก")

    assert [item["food_name"] for item in res["items"]] == ["ข้าวมันไก่", "น้ำส้ม", "สลัดจานเล็ก"]
    # the prompt has to tell the model how many parts to answer for
    prompt = "\n".join(str(part) for part in genai.prompts[0])
    assert "3 รายการ" in prompt
    assert "1. ข้าวมันไก่" in prompt
