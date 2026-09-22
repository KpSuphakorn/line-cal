"""Shared error type and call helper for Gemini food-analysis requests."""
import json
import logging
import time
from typing import Any

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
# the total budget stays well clear of. Per-model timeout has to clear the
# slowest healthy model above (12.5s) without letting one hung model eat the
# whole budget.
MODEL_TIMEOUT_SECONDS = 14
TOTAL_BUDGET_SECONDS = 28


class FoodAnalysisError(RuntimeError):
    """Raised when Gemini fails to produce a real food analysis.

    Never caught to synthesize a fake estimate — callers must surface the
    failure so a made-up answer is never shown to the user as if it were a
    real AI result.
    """


def generate_food_json(genai_module: Any, contents: list, log_label: str) -> dict:
    """Call Gemini across FOOD_MODELS in order, returning the first successful JSON reply.

    A model that hangs must not consume the time the next one needs, so each
    attempt is capped both by its own timeout and by what is left of the shared
    budget. Raises FoodAnalysisError only once every pinned model has failed —
    never falls back to fabricated data.
    """
    last_error: Exception | None = None
    deadline = time.monotonic() + TOTAL_BUDGET_SECONDS
    for attempt, model_name in enumerate(FOOD_MODELS, 1):
        remaining = deadline - time.monotonic()
        if remaining < 1:
            logger.error(
                "Gemini (%s) budget of %ss exhausted before trying %s",
                log_label, TOTAL_BUDGET_SECONDS, model_name,
            )
            break
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
            logger.error(f"Error calling Gemini ({log_label}) with {model_name}: {e}")
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
