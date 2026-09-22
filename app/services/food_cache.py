"""Persistent cache for AI food estimates, keyed on the description typed.

Every function here swallows its own errors on purpose. The cache is an
optimisation, so a missing table — the window between deploying this code and
running its migration — has to look exactly like a cache miss rather than
taking food logging down with it.
"""
import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import FoodEstimateCache

logger = logging.getLogger(__name__)

MAX_KEY_LENGTH = 300


def cache_key(text: str) -> str:
    """Normalize a description so spacing and casing still hit the same entry."""
    return re.sub(r"\s+", " ", text or "").strip().lower()[:MAX_KEY_LENGTH]


def lookup(db: Session, text: str) -> list[dict] | None:
    """Return a stored estimate for this exact description, or None."""
    key = cache_key(text)
    if not key:
        return None
    try:
        row = db.query(FoodEstimateCache).filter(FoodEstimateCache.cache_key == key).first()
        if row is None:
            return None
        items = json.loads(row.items_json)
        if not isinstance(items, list) or not items:
            return None
        row.hit_count += 1
        row.last_used_at = datetime.now(timezone.utc)
        db.commit()
        return items
    except Exception:
        db.rollback()
        logger.warning("Food estimate cache unavailable for lookup", exc_info=True)
        return None


def store(db: Session, text: str, items: list[dict]) -> None:
    """Remember an estimate so the next identical description costs no request."""
    key = cache_key(text)
    if not key or not items:
        return
    try:
        payload = json.dumps(items, ensure_ascii=False)
        row = db.query(FoodEstimateCache).filter(FoodEstimateCache.cache_key == key).first()
        if row is None:
            db.add(FoodEstimateCache(cache_key=key, items_json=payload))
        else:
            row.items_json = payload
            row.last_used_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Food estimate cache unavailable for store", exc_info=True)
