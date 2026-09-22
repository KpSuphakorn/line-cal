"""Unit tests for the shared Gemini call helper: the model chain, its time budget
and the cooldown that keeps a refusing model out of the rotation."""
import json

import pytest

from app.services import ai_errors
from app.services.ai_errors import FoodAnalysisError, generate_food_json


def _chain_genai(behaviour, clock):
    """A fake google.generativeai whose models act out `behaviour` by name.

    `behaviour[name]` is either None (answers successfully) or a
    (seconds_burned, error_message) pair. The fake advances `clock` instead of
    really sleeping, so budget logic is exercised without slow tests.
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
            outcome = behaviour[self.name]
            if outcome is None:
                return _Response()
            burn, message = outcome
            # The SDK aborts at the timeout it was handed, so a model cannot
            # burn more than that however long it would have hung for.
            clock["now"] += min(burn, timeout)
            raise RuntimeError(message)

    class _FakeGenAI:
        @staticmethod
        def configure(**kwargs):
            pass

        @staticmethod
        def GenerativeModel(name, *args, **kwargs):
            return _Model(name)

    return _FakeGenAI(), calls


@pytest.fixture(autouse=True)
def clear_cooldowns():
    """Cooldowns live on the module, so one test must not bench a model for the next."""
    ai_errors._cooldown_until.clear()
    yield
    ai_errors._cooldown_until.clear()


@pytest.fixture
def fake_clock(monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(ai_errors.time, "monotonic", lambda: clock["now"])
    return clock


TIMEOUT = "504 Deadline Exceeded"
OVERLOADED = "503 This model is currently experiencing high demand"


def test_an_instant_failure_leaves_the_next_model_its_full_timeout(fake_clock, monkeypatch):
    """A 503 comes back immediately, so falling through it must cost no budget."""
    monkeypatch.setattr(ai_errors, "FOOD_MODELS", ("returns-503", "answers"))
    genai, calls = _chain_genai({"returns-503": (0, OVERLOADED), "answers": None}, fake_clock)

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
    monkeypatch.setattr(ai_errors, "FOOD_MODELS", ("hangs", "hangs-too"))
    burn = (ai_errors.MODEL_TIMEOUT_SECONDS, TIMEOUT)
    genai, calls = _chain_genai({"hangs": burn, "hangs-too": burn}, fake_clock)

    with pytest.raises(FoodAnalysisError):
        generate_food_json(genai, ["prompt"], log_label="test")

    assert fake_clock["now"] <= ai_errors.TOTAL_BUDGET_SECONDS
    assert len(calls) > len(ai_errors.FOOD_MODELS), "the budget should allow more than one pass"


def test_a_stalled_model_is_tried_again_rather_than_benched(fake_clock, monkeypatch):
    """A slow call is this model's ordinary behaviour (2.6s-19.5s measured), so
    one timeout must not take it out of the rotation."""
    monkeypatch.setattr(ai_errors, "FOOD_MODELS", ("stalls-once",))
    outcomes = [(ai_errors.MODEL_TIMEOUT_SECONDS, TIMEOUT), None]

    class _Response:
        text = json.dumps({"items": [{"food_name": "ข้าวผัด"}]})

    class _Model:
        def __init__(self, name):
            self.name = name

        def generate_content(self, contents, **kwargs):
            outcome = outcomes.pop(0)
            if outcome is None:
                return _Response()
            fake_clock["now"] += outcome[0]
            raise RuntimeError(outcome[1])

    genai = type("_G", (), {
        "configure": staticmethod(lambda **kw: None),
        "GenerativeModel": staticmethod(lambda name, *a, **k: _Model(name)),
    })()

    result = generate_food_json(genai, ["prompt"], log_label="test")

    assert result["items"][0]["food_name"] == "ข้าวผัด"
    assert "stalls-once" not in ai_errors._cooldown_until


@pytest.mark.parametrize("message,kind", [
    (OVERLOADED, "unavailable"),
    ("429 Resource has been exhausted (quota)", "quota"),
    ("429 quota_id: GenerateRequestsPerDayPerProjectPerModel-FreeTier", "quota_day"),
    ("429 quota_id: GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "quota_minute"),
    ("404 models/foo is not found for API version v1beta", "missing"),
])
def test_an_explicit_refusal_benches_the_model(fake_clock, monkeypatch, message, kind):
    """Re-probing a model that just refused cost a measured 4.1s per request."""
    monkeypatch.setattr(ai_errors, "FOOD_MODELS", ("refuses", "answers"))
    genai, _ = _chain_genai({"refuses": (0, message), "answers": None}, fake_clock)

    generate_food_json(genai, ["prompt"], log_label="test")
    assert ai_errors._cooldown_until["refuses"] == pytest.approx(
        fake_clock["now"] + ai_errors._COOLDOWN_SECONDS[kind]
    )

    later, later_calls = _chain_genai({"refuses": (0, message), "answers": None}, fake_clock)
    generate_food_json(later, ["prompt"], log_label="test")

    assert [call["model"] for call in later_calls] == ["answers"], "benched model must be skipped"


def test_every_model_benched_still_gets_an_attempt(fake_clock, monkeypatch):
    """A stale cooldown must never be the reason the user gets no answer at all."""
    monkeypatch.setattr(ai_errors, "FOOD_MODELS", ("only-one",))
    ai_errors._cooldown_until["only-one"] = fake_clock["now"] + 600
    genai, calls = _chain_genai({"only-one": None}, fake_clock)

    result = generate_food_json(genai, ["prompt"], log_label="test")

    assert result["items"][0]["food_name"] == "ข้าวผัด"
    assert calls, "the chain must fall back to trying a benched model"


def test_the_chain_has_a_real_spare_so_one_bad_model_is_not_fatal():
    """A single pinned model means any upstream hiccup reaches the user as an error."""
    assert len(ai_errors.FOOD_MODELS) >= 2
    assert all("latest" not in name for name in ai_errors.FOOD_MODELS)
