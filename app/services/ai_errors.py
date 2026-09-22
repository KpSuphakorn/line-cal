"""Shared error type and call helper for Gemini food-analysis requests."""
import json
import logging
import time
from typing import Any, Iterator

logger = logging.getLogger(__name__)

# Pinned explicit model names, tried in order — never a "-latest" alias, which
# Google silently repoints to newer preview models with much smaller free-tier
# daily quotas. Verify a replacement with a live generate_content call, not
# genai.list_models(): that endpoint listed gemini-2.5-flash as available while
# calls to it 404'd as "no longer available to new users".
#
# Free-tier availability moves without warning, so this is a chain and not a
# single model. Measured on this account with the real food prompt on
# 2026-09-23, after 3.5-flash-lite (previously ~0.9s) degraded to 15s+ hangs:
#
#   gemini-3.6-flash        5.5s / 7.7s   ok, but capped at 20 requests/day
#   gemini-3.1-flash-lite   6.6s / 12.5s  ok, slower and more variable
#   gemini-3.5-flash-lite   timed out twice at 15s — kept last so it serves
#                           again by itself once Google's side recovers
#
# Models are tried in order and only on failure, so a healthy first entry costs
# exactly one request — a chain does not spend more quota than a single model.
FOOD_MODELS = (
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
)

# A 429 from a quota-exhausted model carries a "retry in 22s" hint that
# google-api-core honours by sleeping and retrying in-process, so retry stays
# disabled: fail fast and let the chain above provide the real retry.
#
# Webhook processing runs in a BackgroundTask, so these no longer have to fit
# inside LINE's webhook window. The remaining ceiling is the reply token, which
# the total budget stays well clear of.
#
# 8s is measured, not guessed. 12 successful calls on 2026-09-23 ran
# 2.6 3.8 4.0 4.6 4.7 5.6 6.1 6.2 7.0 11.8 13.8 19.5 (p50 5.8s), and expected
# end-to-end latency for "give up at T and try again" over that sample is:
#
#   T= 5s -> 10.9s     T= 8s ->  7.6s     T=12s ->  8.0s
#   T= 6s -> 10.2s     T=10s ->  8.3s     T=14s ->  7.7s
#
# So a tighter timeout does not buy speed — the spread is continuous, not a
# fast mode plus a stalled mode, and cutting to 5s makes things worse. 8s is
# picked because it ties for the best expected latency while capping what a
# genuinely hung model (the 15s+ stalls seen on 3.5-flash-lite) can waste, and
# leaves room for three attempts inside the budget instead of two.
MODEL_TIMEOUT_SECONDS = 8
TOTAL_BUDGET_SECONDS = 28

# Starting an attempt that cannot plausibly finish just burns the remainder.
MIN_ATTEMPT_SECONDS = 3

# One pass over the chain is not a retry, it is a single shot at each model.
# Re-walking it lets a model that stalled once answer on the next attempt.
MAX_ROUNDS = 3

# How long a model that explicitly refused sits out. Note what is NOT here: a
# timeout never benches a model. The measured spread above is one model's own
# ordinary behaviour, so treating a slow call as "this model is broken" would
# bench the only healthy model we have.
_COOLDOWN_SECONDS = {
    "missing": 86_400.0,   # 404 — not served to this account, not coming back today
    "quota": 900.0,        # 429 — the free-tier allowance is spent
    "unavailable": 60.0,   # 503 — Google calls these spikes temporary
}

# Module-level so a refusal is remembered across requests: re-probing a model
# that just returned 503 cost a measured 4.1s on every single request.
_cooldown_until: dict[str, float] = {}


class FoodAnalysisError(RuntimeError):
    """Raised when Gemini fails to produce a real food analysis.

    Never caught to synthesize a fake estimate — callers must surface the
    failure so a made-up answer is never shown to the user as if it were a
    real AI result.
    """


def _refusal_kind(error: Exception) -> str | None:
    """Classify an error as a refusal worth benching the model for, or None.

    Matched on the message text rather than on google.api_core exception types:
    the same condition reaches us as a gRPC error, a REST error or a plain
    RuntimeError depending on transport and SDK version, and only the status
    code is reliably present in all of them.
    """
    text = str(error).lower()
    if "404" in text or "not found" in text:
        return "missing"
    if "429" in text or "quota" in text or "resource_exhausted" in text:
        return "quota"
    if "503" in text or "unavailable" in text or "high demand" in text:
        return "unavailable"
    return None


def _available_models() -> list[str]:
    """The chain minus anything still cooling off.

    Falls back to the whole chain when everything is benched: a stale cooldown
    must never be the reason the user gets no answer at all.
    """
    now = time.monotonic()
    return [name for name in FOOD_MODELS if _cooldown_until.get(name, 0.0) <= now] or list(FOOD_MODELS)


def _attempt_sequence() -> Iterator[str]:
    """Model names to try, in order, re-reading cooldowns before each round."""
    for _ in range(MAX_ROUNDS):
        yield from _available_models()


def generate_food_json(genai_module: Any, contents: list, log_label: str) -> dict:
    """Call Gemini across FOOD_MODELS in order, returning the first successful JSON reply.

    A model that hangs must not consume the time the next one needs, so each
    attempt is capped both by its own timeout and by what is left of the shared
    budget. Raises FoodAnalysisError only once every pinned model has failed —
    never falls back to fabricated data.
    """
    last_error: Exception | None = None
    deadline = time.monotonic() + TOTAL_BUDGET_SECONDS
    attempt = 0
    for model_name in _attempt_sequence():
        remaining = deadline - time.monotonic()
        if remaining < MIN_ATTEMPT_SECONDS:
            logger.error(
                "Gemini (%s) ran out of its %ss budget after %d attempt(s)",
                log_label, TOTAL_BUDGET_SECONDS, attempt,
            )
            break
        attempt += 1
        try:
            model = genai_module.GenerativeModel(model_name)
            response = model.generate_content(
                contents,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.2,
                },
                request_options={
                    "retry": None,
                    "timeout": min(MODEL_TIMEOUT_SECONDS, remaining),
                },
            )
            content_text = response.text.strip()
            if content_text.startswith("```json"):
                content_text = content_text[7:]
            if content_text.startswith("```"):
                content_text = content_text[3:]
            if content_text.endswith("```"):
                content_text = content_text[:-3]
            parsed = json.loads(content_text.strip())
            if attempt > 1:
                # Which model actually answered is invisible otherwise, so a
                # degraded primary looks like "it just got slower" in the logs.
                logger.warning(
                    "Gemini (%s) answered with fallback model %s after %d failed attempt(s)",
                    log_label, model_name, attempt - 1,
                )
            return parsed
        except Exception as e:
            kind = _refusal_kind(e)
            if kind:
                _cooldown_until[model_name] = time.monotonic() + _COOLDOWN_SECONDS[kind]
            logger.error(
                "Error calling Gemini (%s) with %s%s: %s",
                log_label, model_name, f" [benched: {kind}]" if kind else "", e,
            )
            last_error = e
            continue

    raise FoodAnalysisError(f"Gemini {log_label} failed") from last_error


def merge_food_items(items: list[Any], food_name: str | None = None) -> list[dict]:
    """Fold component rows the model reported for one dish into a single row.

    The model still reasons ingredient by ingredient for accuracy, but a dish
    the user experiences as one plate has to stay one row. Sums calories and
    macros, keeps the lowest confidence across components, and lists the
    components in `notes`.

    `food_name` names the merged row when given (the text the user actually
    typed). Otherwise the components' own names are joined, since there is no
    user-typed anchor to fall back to (a food photo has none).
    """
    items = [item for item in items if isinstance(item, dict)]
    if len(items) <= 1:
        return items or ([{"food_name": food_name}] if food_name else [])

    def total(field: str) -> float:
        return round(sum(float(item.get(field) or 0) for item in items), 1)

    names = [str(item.get("food_name") or "").strip() for item in items if item.get("food_name")]
    confidences = [item.get("confidence") for item in items if item.get("confidence") is not None]
    return [{
        "food_name": food_name or " • ".join(names) or "อาหารที่ตรวจพบ",
        "portion": items[0].get("portion") or "1 ที่",
        "calories": total("calories"),
        "protein": total("protein"),
        "carbs": total("carbs"),
        "fat": total("fat"),
        "confidence": min(float(value) for value in confidences) if confidences else None,
        "notes": " • ".join(names) if food_name else "",
    }]
