"""Unit tests for the shared Gemini call helper: the model chain and its time budget."""
import json

import pytest

from app.services import ai_errors
from app.services.ai_errors import FoodAnalysisError, generate_food_json


def _chain_genai(behaviour, clock):
    """A fake google.generativeai whose models act out `behaviour` by name.

    `behaviour[name]` is the number of seconds that model burns before failing,
    or None when it answers successfully. The fake advances `clock` instead of
    really sleeping, so the budget logic is exercised without slow tests.
    """
    calls = []

    class _Response:
        text = json.dumps({"items": [{"food_name": "ข้าวผัด", "calories": 300}]})

    class _Model:
        def __init__(self, name):
            self.name = name

        def generate_content(self, contents, **kwargs):
            timeout = kwargs["request_options"]["timeout"]
            calls.append({"model": self.name, "timeout": timeout})
            burn = behaviour[self.name]
            if burn is None:
                return _Response()
            clock["now"] += burn
            raise RuntimeError("504 Deadline Exceeded")

    class _FakeGenAI:
        @staticmethod
        def configure(**kwargs):
            pass

        @staticmethod
        def GenerativeModel(name, *args, **kwargs):
            return _Model(name)

    return _FakeGenAI(), calls


@pytest.fixture
def fake_clock(monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(ai_errors.time, "monotonic", lambda: clock["now"])
    return clock


def test_an_instant_failure_leaves_the_next_model_its_full_timeout(fake_clock, monkeypatch):
    """A 503 comes back immediately, so falling through it must cost no budget."""
    monkeypatch.setattr(ai_errors, "FOOD_MODELS", ("returns-503", "answers"))
    genai, calls = _chain_genai({"returns-503": 0, "answers": None}, fake_clock)

    result = generate_food_json(genai, ["prompt"], log_label="test")

    assert result["items"][0]["food_name"] == "ข้าวผัด"
    assert [call["timeout"] for call in calls] == [
        ai_errors.MODEL_TIMEOUT_SECONDS,
        ai_errors.MODEL_TIMEOUT_SECONDS,
    ]


def test_a_hung_model_cannot_overrun_the_shared_budget(fake_clock, monkeypatch):
    """Every model hanging must still land inside TOTAL_BUDGET_SECONDS.

    The reply token is the real deadline once webhook processing is async, so
    the chain has to bound its own total, not just each attempt.
    """
    monkeypatch.setattr(ai_errors, "FOOD_MODELS", ("hangs", "hangs-too", "never-reached"))
    genai, calls = _chain_genai(
        {"hangs": ai_errors.MODEL_TIMEOUT_SECONDS, "hangs-too": ai_errors.MODEL_TIMEOUT_SECONDS, "never-reached": None},
        fake_clock,
    )

    with pytest.raises(FoodAnalysisError):
        generate_food_json(genai, ["prompt"], log_label="test")

    assert [call["model"] for call in calls] == ["hangs", "hangs-too"]
    assert fake_clock["now"] <= ai_errors.TOTAL_BUDGET_SECONDS


def test_a_slow_failure_shrinks_what_is_left_for_the_next_model(fake_clock, monkeypatch):
    """The last model gets the remainder of the budget, not a fresh full timeout."""
    monkeypatch.setattr(ai_errors, "FOOD_MODELS", ("slow-fail", "answers"))
    leftover = ai_errors.TOTAL_BUDGET_SECONDS - ai_errors.MODEL_TIMEOUT_SECONDS
    genai, calls = _chain_genai({"slow-fail": ai_errors.MODEL_TIMEOUT_SECONDS, "answers": None}, fake_clock)

    generate_food_json(genai, ["prompt"], log_label="test")

    assert calls[0]["timeout"] == ai_errors.MODEL_TIMEOUT_SECONDS
    assert calls[1]["timeout"] == min(ai_errors.MODEL_TIMEOUT_SECONDS, leftover)


def test_the_chain_has_a_real_spare_so_one_bad_model_is_not_fatal():
    """A single pinned model means any upstream hiccup reaches the user as an error."""
    assert len(ai_errors.FOOD_MODELS) >= 2
    assert all("latest" not in name for name in ai_errors.FOOD_MODELS)
