"""Shared error type and call helper for Gemini food-analysis requests."""
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class FoodAnalysisError(RuntimeError):
    """Raised when Gemini fails to produce a real food analysis.

    Never caught to synthesize a fake estimate — callers must surface the
    failure so a made-up answer is never shown to the user as if it were a
    real AI result.
    """


def generate_food_json(genai_module: Any, models: tuple[str, ...], contents: list, log_label: str) -> dict:
    """Call Gemini across pinned models in order, returning the first successful JSON reply.

    Models are tried in order and never a "-latest" alias, which Google
    silently repoints to newer preview models with much smaller free-tier
    daily quotas. Raises FoodAnalysisError only once every pinned model has
    failed — never falls back to fabricated data.
    """
    last_error: Exception | None = None
    for model_name in models:
        try:
            model = genai_module.GenerativeModel(model_name)
            response = model.generate_content(
                contents,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.2,
                },
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
