"""Shared error type and call helper for Gemini food-analysis requests."""
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Pinned explicit model names, tried in order — never a "-latest" alias, which
# Google silently repoints to newer preview models with much smaller free-tier
# daily quotas. Verify a replacement with a live generate_content call, not
# genai.list_models(): that endpoint listed gemini-2.5-flash as available while
# calls to it 404'd as "no longer available to new users".
#
# Measured on this account: 3.5-flash-lite answers in ~0.9s, while 3.6-flash is
# capped at 20 requests/day and 3.7-flash / 3.1-flash-lite both time out, which
# only spends the webhook's time budget without producing an answer.
FOOD_MODELS = ("gemini-3.5-flash-lite",)

# A 429 from a quota-exhausted model carries a "retry in 22s" hint that
# google-api-core honours by sleeping and retrying in-process. The whole call
# has to finish inside LINE's webhook window, and the model chain above already
# covers an exhausted model, so retry is disabled: fail fast, try the next one.
GEMINI_REQUEST_OPTIONS = {"retry": None, "timeout": 8}


class FoodAnalysisError(RuntimeError):
    """Raised when Gemini fails to produce a real food analysis.

    Never caught to synthesize a fake estimate — callers must surface the
    failure so a made-up answer is never shown to the user as if it were a
    real AI result.
    """


def generate_food_json(genai_module: Any, contents: list, log_label: str) -> dict:
    """Call Gemini across FOOD_MODELS in order, returning the first successful JSON reply.

    Raises FoodAnalysisError only once every pinned model has failed — never
    falls back to fabricated data.
    """
    last_error: Exception | None = None
    for model_name in FOOD_MODELS:
        try:
            model = genai_module.GenerativeModel(model_name)
            response = model.generate_content(
                contents,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.2,
                },
                request_options=GEMINI_REQUEST_OPTIONS,
            )
            content_text = response.text.strip()
            if content_text.startswith("```json"):
                content_text = content_text[7:]
            if content_text.startswith("```"):
                content_text = content_text[3:]
            if content_text.endswith("```"):
                content_text = content_text[:-3]
            return json.loads(content_text.strip())
        except Exception as e:
            logger.error(f"Error calling Gemini ({log_label}) with {model_name}: {e}")
            last_error = e
            continue

    raise FoodAnalysisError(f"Gemini {log_label} failed") from last_error
