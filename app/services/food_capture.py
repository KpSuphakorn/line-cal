"""Shared durable food-capture flow for LINE and the LIFF editor."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import FoodAnalysisDraft, FoodCapture, FoodLog

BANGKOK = ZoneInfo("Asia/Bangkok")
CAPTURE_TTL = timedelta(hours=24)


@dataclass(frozen=True)
class CaptureActionResult:
    """Outcome observed while holding the capture row lock."""

    status: str
    entries: list[FoodLog]


def _expired(value: datetime | None) -> bool:
    if not value:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value < datetime.now(timezone.utc)


def normalize_food_result(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Accept the new items shape while tolerating one legacy AI result."""
    if not result:
        return []
    raw_items = result.get("items")
    if not isinstance(raw_items, list):
        raw_items = [result]
    items: list[dict[str, Any]] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("food_name") or raw.get("name") or "อาหารที่ตรวจพบ").strip()
        if not name:
            continue
        items.append({
            "food_name": name[:200],
            "portion": str(raw.get("portion") or "1 ที่")[:150],
            "calories": max(0.0, float(raw.get("calories") or 0)),
            "protein": max(0.0, float(raw.get("protein") or 0)),
            "carbs": max(0.0, float(raw.get("carbs") or 0)),
            "fat": max(0.0, float(raw.get("fat") or 0)),
            "confidence": _optional_float(raw.get("confidence")),
            "notes": str(raw.get("notes") or "").strip()[:1000] or None,
        })
    return items


def _optional_float(value: Any) -> float | None:
    try:
        return None if value in (None, "") else max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def create_capture(
    db: Session,
    user_id: str,
    source: str,
    items: Iterable[dict[str, Any]],
    source_message_id: str | None = None,
    ai_metadata: dict[str, Any] | None = None,
) -> FoodCapture:
    """Persist one capture and its ordered independent draft items."""
    if source_message_id:
        existing = db.query(FoodCapture).filter(
            FoodCapture.user_id == user_id,
            FoodCapture.source_message_id == source_message_id,
        ).first()
        if existing:
            return existing
    capture = FoodCapture(
        token=uuid4().hex,
        user_id=user_id,
        source=source,
        source_message_id=source_message_id,
        status="draft",
        ai_metadata=ai_metadata or {},
        expires_at=datetime.now(timezone.utc) + CAPTURE_TTL,
    )
    db.add(capture)
    db.flush()
    for index, item in enumerate(normalize_food_result({"items": list(items)}), start=1):
        db.add(FoodAnalysisDraft(capture_id=capture.id, order_num=index, **item))
    db.commit()
    db.refresh(capture)
    return capture


def _get_capture(db: Session, user_id: str, token: str, lock: bool = False) -> FoodCapture | None:
    query = db.query(FoodCapture).filter(FoodCapture.token == token, FoodCapture.user_id == user_id)
    return query.with_for_update().first() if lock else query.first()


def serialize_capture(capture: FoodCapture) -> dict[str, Any]:
    return {
        "id": capture.id,
        "token": capture.token,
        "source": capture.source,
        "status": capture.status,
        "created_at": capture.created_at.isoformat() if capture.created_at else None,
        "expires_at": capture.expires_at.isoformat() if capture.expires_at else None,
        "items": [
            {
                "id": draft.id,
                "order_num": draft.order_num,
                "food_name": draft.food_name,
                "portion": draft.portion,
                "calories": draft.calories,
                "protein": draft.protein,
                "carbs": draft.carbs,
                "fat": draft.fat,
                "confidence": draft.confidence,
                "notes": draft.notes,
            }
            for draft in capture.drafts
        ],
    }


def get_capture(db: Session, user_id: str, token: str) -> FoodCapture:
    capture = _get_capture(db, user_id, token)
    if not capture:
        raise HTTPException(status_code=404, detail="Food capture not found")
    return capture


def get_editable_capture(db: Session, user_id: str, token: str) -> FoodCapture:
    """Return only a live draft for the authenticated LIFF editor."""
    # Serialize the editor's expiry transition with confirm/cancel/update.
    capture = _get_capture(db, user_id, token, lock=True)
    if not capture:
        raise HTTPException(status_code=404, detail="Food capture not found")
    if capture.status != "draft":
        raise HTTPException(status_code=409, detail="รายการอาหารนี้ยืนยันหรือยกเลิกไปแล้ว จึงแก้ไขรายการร่างไม่ได้")
    if _expired(capture.expires_at):
        capture.status = "cancelled"
        capture.cancelled_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=410, detail="รายการอาหารหมดอายุแล้ว กรุณาส่งรายการใหม่อีกครั้ง")
    return capture


def update_capture(db: Session, user_id: str, token: str, items: list[dict[str, Any]]) -> FoodCapture:
    # Serialize LIFF edits with chat confirmation/cancellation on the parent
    # capture row.  The lock must cover the expiry transition and draft
    # replacement so a stale editor cannot mutate a terminal capture.
    capture = _get_capture(db, user_id, token, lock=True)
    if not capture:
        raise HTTPException(status_code=404, detail="Food capture not found")
    if capture.status != "draft":
        raise HTTPException(status_code=409, detail="Food capture is no longer editable")
    if _expired(capture.expires_at):
        capture.status = "cancelled"
        capture.cancelled_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=410, detail="Food capture expired")
    if not items:
        raise HTTPException(status_code=422, detail="At least one food item is required")
    db.query(FoodAnalysisDraft).filter(FoodAnalysisDraft.capture_id == capture.id).delete()
    for index, item in enumerate(normalize_food_result({"items": items}), start=1):
        db.add(FoodAnalysisDraft(capture_id=capture.id, order_num=index, **item))
    db.commit()
    db.refresh(capture)
    return capture


def confirm_capture_result(db: Session, user_id: str, token: str) -> CaptureActionResult:
    """Confirm at the lock boundary and retain whether this tap changed state."""
    capture = _get_capture(db, user_id, token, lock=True)
    if not capture:
        return CaptureActionResult("missing", [])
    if capture.status == "confirmed":
        entries = db.query(FoodLog).filter(FoodLog.capture_id == capture.id, FoodLog.user_id == user_id).all()
        return CaptureActionResult("already_confirmed", entries)
    if capture.status != "draft":
        return CaptureActionResult("cancelled", [])
    if _expired(capture.expires_at):
        capture.status = "cancelled"
        capture.cancelled_at = datetime.now(timezone.utc)
        db.commit()
        return CaptureActionResult("expired", [])
    now = datetime.now(timezone.utc)
    logs = [FoodLog(
        user_id=user_id,
        capture_id=capture.id,
        food_name=draft.food_name,
        portion=draft.portion,
        calories=draft.calories,
        protein=draft.protein,
        carbs=draft.carbs,
        fat=draft.fat,
        logged_at=now,
    ) for draft in capture.drafts]
    db.add_all(logs)
    capture.status = "confirmed"
    capture.confirmed_at = now
    db.commit()
    return CaptureActionResult("confirmed", logs)


def confirm_capture(db: Session, user_id: str, token: str) -> list[FoodLog]:
    """Keep the API's idempotent list contract for existing callers."""
    result = confirm_capture_result(db, user_id, token)
    return result.entries if result.status in {"confirmed", "already_confirmed"} else []


def cancel_capture_result(db: Session, user_id: str, token: str) -> CaptureActionResult:
    """Cancel only a live draft and report the locked state to chat callers."""
    capture = _get_capture(db, user_id, token, lock=True)
    if not capture:
        return CaptureActionResult("missing", [])
    if capture.status == "confirmed":
        return CaptureActionResult("confirmed", [])
    if capture.status == "cancelled":
        return CaptureActionResult("already_cancelled", [])
    if capture.status != "draft":
        return CaptureActionResult("unavailable", [])
    if _expired(capture.expires_at):
        capture.status = "cancelled"
        capture.cancelled_at = datetime.now(timezone.utc)
        db.commit()
        return CaptureActionResult("expired", [])
    capture.status = "cancelled"
    capture.cancelled_at = datetime.now(timezone.utc)
    db.commit()
    return CaptureActionResult("cancelled", [])


def cancel_capture(db: Session, user_id: str, token: str) -> bool:
    """Keep the API's existing boolean contract for callers outside chat."""
    return cancel_capture_result(db, user_id, token).status in {"cancelled", "already_cancelled"}


def ai_quota_remaining(db: Session, user_id: str) -> int:
    now = datetime.now(BANGKOK)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    end = start + timedelta(days=1)
    used = db.query(FoodCapture).filter(
        FoodCapture.user_id == user_id,
        FoodCapture.created_at >= start,
        FoodCapture.created_at < end,
    ).count()
    return max(0, int(settings.AI_DAILY_LIMIT) - used)


def ensure_ai_quota(db: Session, user_id: str) -> None:
    if ai_quota_remaining(db, user_id) <= 0:
        raise HTTPException(status_code=429, detail="วันนี้ใช้โควต้าวิเคราะห์อาหารครบแล้ว ลองใหม่พรุ่งนี้ได้เลยครับ")
