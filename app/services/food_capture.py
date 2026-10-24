"""Shared durable food-capture flow for LINE and the LIFF editor."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import FoodAnalysisDraft, FoodCapture, FoodLog, FoodLookup, User

BANGKOK = ZoneInfo("Asia/Bangkok")
CAPTURE_TTL = timedelta(hours=24)
REFINEMENT_TTL = timedelta(minutes=10)
REFINEMENT_LEASE = timedelta(minutes=3)
MAX_REFINEMENT_INSTRUCTIONS = 6
MAX_REFINEMENT_TEXT = 500

# Shared bound for food values, whether from an AI-parsed draft (this module)
# or a LIFF edit (main.py's Pydantic models) — keeps a malformed AI response
# (e.g. calories: 1e30) from reaching the DB unclamped.
MAX_CALORIES = 100000.0
MAX_MACRO_GRAMS = 10000.0

# A capture is one photo or one typed line, so a handful of plates is the
# realistic ceiling. Bounding it here stops a malformed AI response from
# turning into hundreds of draft rows and an unreadable review card.
MAX_DRAFT_ITEMS = 20


@dataclass(frozen=True)
class CaptureActionResult:
    """Outcome observed while holding the capture row lock."""

    status: str
    entries: list[FoodLog]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _metadata(capture: FoodCapture) -> dict[str, Any]:
    return dict(capture.ai_metadata or {})


def _lock_user(db: Session, user_id: str) -> User | None:
    return db.query(User).filter(User.id == user_id).populate_existing().with_for_update().first()


def _lock_captures(db: Session, user_id: str) -> list[FoodCapture]:
    return db.query(FoodCapture).filter(FoodCapture.user_id == user_id).populate_existing().with_for_update().all()


def _locked_capture(db: Session, user_id: str, token: str) -> FoodCapture | None:
    return db.query(FoodCapture).filter(
        FoodCapture.user_id == user_id, FoodCapture.token == token,
    ).populate_existing().with_for_update().first()


def _invalidate_refinement(metadata: dict[str, Any]) -> dict[str, Any]:
    metadata.pop("refine_until", None)
    metadata.pop("refine_attempt", None)
    metadata.pop("refine_context_id", None)
    return metadata


def _capture_snapshot(db: Session, capture: FoodCapture) -> dict[str, Any]:
    db.expire(capture, ["drafts"])
    snapshot = serialize_capture(capture)
    snapshot["refine_context_id"] = (_metadata(capture).get("refine_context_id"))
    return snapshot


def clear_food_refinement(db: Session, user_id: str) -> None:
    """Exit the owner's selected photo context and fence any in-flight result."""
    if not _lock_user(db, user_id):
        db.rollback()
        return
    for capture in _lock_captures(db, user_id):
        metadata = _metadata(capture)
        if "refine_until" in metadata or "refine_attempt" in metadata:
            capture.ai_metadata = _invalidate_refinement(metadata)
    db.commit()


def select_food_refinement(db: Session, user_id: str, token: str, expected_revision: int) -> tuple[str, dict[str, Any] | None]:
    """Select one live photo draft for ten minutes; selection is durable per user."""
    if not _lock_user(db, user_id):
        db.rollback()
        return "missing", None
    captures = _lock_captures(db, user_id)
    capture = next((row for row in captures if row.token == token), None)
    if not capture:
        db.commit()
        return "missing", None
    if capture.status != "draft" or _expired(capture.expires_at):
        snapshot = _capture_snapshot(db, capture)
        db.commit()
        return "unavailable", snapshot
    if capture.source != "image" or capture.source_message_id is None:
        db.commit()
        return "not_image", capture
    metadata = _metadata(capture)
    if int(metadata.get("revision", 0)) != expected_revision:
        snapshot = _capture_snapshot(db, capture)
        db.commit()
        return "stale", snapshot
    for row in captures:
        row_metadata = _metadata(row)
        if "refine_until" in row_metadata or "refine_attempt" in row_metadata:
            row.ai_metadata = _invalidate_refinement(row_metadata)
    metadata = _metadata(capture)
    metadata["refine_until"] = (_now() + REFINEMENT_TTL).isoformat()
    metadata["refine_context_id"] = uuid4().hex
    capture.ai_metadata = metadata
    snapshot = _capture_snapshot(db, capture)
    db.commit()
    return "selected", snapshot


def cancel_food_refinement(db: Session, user_id: str, token: str, expected_revision: int, context_id: str | None = None) -> str:
    if not _lock_user(db, user_id):
        db.rollback()
        return "missing"
    capture = _locked_capture(db, user_id, token)
    if not capture:
        db.commit()
        return "missing"
    metadata = _metadata(capture)
    if (int(metadata.get("revision", 0)) != expected_revision
            or (context_id is not None and metadata.get("refine_context_id") != context_id)):
        db.commit()
        return "stale"
    if "refine_until" not in metadata and "refine_attempt" not in metadata:
        db.commit()
        return "inactive"
    capture.ai_metadata = _invalidate_refinement(metadata)
    db.commit()
    return "cancelled"


def selected_food_refinement(db: Session, user_id: str) -> tuple[str, FoodCapture | None]:
    if not _lock_user(db, user_id):
        db.rollback()
        return "missing", None
    now = _now()
    for capture in _lock_captures(db, user_id):
        metadata = _metadata(capture)
        until = metadata.get("refine_until")
        if not until:
            continue
        try:
            expiry = datetime.fromisoformat(until)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            expiry = now
        if expiry <= now or capture.status != "draft" or _expired(capture.expires_at):
            capture.ai_metadata = _invalidate_refinement(metadata)
            db.commit()
            return "expired", None
        db.commit()
        return "selected", capture
    db.commit()
    return "none", None


def claim_food_refinement(db: Session, user_id: str, instruction: str, event_id: str) -> tuple[str, dict[str, Any] | None]:
    """Claim a selected photo correction before any network call."""
    instruction = instruction.strip()
    if not instruction or len(instruction) > MAX_REFINEMENT_TEXT:
        return "invalid", None
    if not _lock_user(db, user_id):
        db.rollback()
        return "missing", None
    captures = _lock_captures(db, user_id)
    now = _now()
    selected = None
    expired = False
    completed = next((capture for capture in captures
                      if (_metadata(capture).get("last_refinement_event_id") == event_id)), None)
    if completed:
        snapshot = _capture_snapshot(db, completed)
        db.commit()
        return "completed", {"capture": snapshot, "revision": snapshot["revision"]}
    consumed = next((capture for capture in captures
                     if event_id in _metadata(capture).get("consumed_refinement_events", [])), None)
    if consumed:
        db.commit()
        return "consumed", None
    for capture in captures:
        metadata = _metadata(capture)
        until = metadata.get("refine_until")
        if not until:
            continue
        try:
            active_until = datetime.fromisoformat(until)
            if active_until.tzinfo is None:
                active_until = active_until.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            active_until = now
        if active_until > now:
            selected = (capture, metadata)
            break
        metadata = _invalidate_refinement(metadata)
        capture.ai_metadata = metadata
        expired = True
    if not selected:
        db.commit()
        return ("expired", None) if expired else ("none", None)
    capture, metadata = selected
    consumed = metadata.get("consumed_refinement_events", [])
    if event_id in consumed:
        db.commit()
        return "consumed", None
    if capture.status != "draft" or _expired(capture.expires_at):
        capture.ai_metadata = _invalidate_refinement(metadata)
        db.commit()
        return "unavailable", None
    attempt = metadata.get("refine_attempt")
    if attempt and attempt.get("event_id") == event_id:
        db.commit()
        return "processing", None
    if attempt:
        try:
            lease_until = datetime.fromisoformat(attempt.get("lease_until", ""))
            if lease_until.tzinfo is None:
                lease_until = lease_until.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            lease_until = now
        if lease_until > now:
            db.commit()
            return "processing", None
    revision = int(metadata.get("revision", 0))
    attempt_id = uuid4().hex
    metadata["refine_attempt"] = {
        "id": attempt_id,
        "event_id": event_id,
        "base_revision": revision,
        "lease_until": (now + REFINEMENT_LEASE).isoformat(),
        "instruction": instruction,
    }
    capture.ai_metadata = metadata
    snapshot = {
        "token": capture.token,
        "source_message_id": capture.source_message_id,
        "revision": revision,
        "attempt_id": attempt_id,
        "event_id": event_id,
        "instruction": instruction,
        "corrections": list(metadata.get("corrections", [])),
        "items": [
            {"food_name": d.food_name, "portion": d.portion, "calories": d.calories,
             "protein": d.protein, "carbs": d.carbs, "fat": d.fat,
             "confidence": d.confidence, "notes": d.notes}
            for d in capture.drafts
        ],
    }
    db.commit()
    return "claimed", snapshot


def reserve_food_refinement_quota(db: Session, user_id: str, token: str, attempt_id: str) -> str:
    """Charge a real image-analysis attempt once, only while its claim is current."""
    if not _lock_user(db, user_id):
        db.rollback()
        return "missing"
    capture = _locked_capture(db, user_id, token)
    if not capture:
        db.commit()
        return "missing"
    metadata = _metadata(capture)
    attempt = metadata.get("refine_attempt") or {}
    try:
        lease_until = datetime.fromisoformat(attempt.get("lease_until", ""))
        if lease_until.tzinfo is None:
            lease_until = lease_until.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        lease_until = _now()
    if capture.status != "draft" or _expired(capture.expires_at):
        db.commit()
        return "unavailable"
    if (attempt.get("id") != attempt_id or int(metadata.get("revision", 0)) != attempt.get("base_revision")
            or lease_until <= _now()):
        db.commit()
        return "stale"
    if ai_quota_remaining(db, user_id) <= 0:
        capture.ai_metadata = _invalidate_refinement(metadata)
        db.commit()
        return "quota"
    consumed = [*metadata.get("consumed_refinement_events", []), attempt.get("event_id")][-20:]
    metadata["consumed_refinement_events"] = consumed
    capture.ai_metadata = metadata
    db.add(FoodLookup(user_id=user_id, used_ai=True))
    # shortcut: reservation commits before the provider call; a crash in that
    # narrow gap can conservatively spend one allowance without an outbound call.
    db.commit()
    return "reserved"


def release_food_refinement(db: Session, user_id: str, token: str, attempt_id: str) -> None:
    if not _lock_user(db, user_id):
        db.rollback()
        return
    capture = _locked_capture(db, user_id, token)
    if capture:
        metadata = _metadata(capture)
        if (metadata.get("refine_attempt") or {}).get("id") == attempt_id:
            metadata.pop("refine_attempt", None)
            capture.ai_metadata = metadata
    db.commit()


def apply_food_refinement(db: Session, user_id: str, token: str, attempt_id: str, event_id: str, items: list[dict[str, Any]]) -> tuple[str, FoodCapture | None]:
    """Apply only to the exact live draft revision claimed before network I/O."""
    if not items:
        return "invalid", None
    if not _lock_user(db, user_id):
        db.rollback()
        return "missing", None
    capture = _locked_capture(db, user_id, token)
    if not capture:
        db.commit()
        return "missing", None
    metadata = _metadata(capture)
    attempt = metadata.get("refine_attempt") or {}
    lease_until = None
    try:
        lease_until = datetime.fromisoformat(attempt.get("lease_until", ""))
        if lease_until.tzinfo is None:
            lease_until = lease_until.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass
    if (capture.status != "draft" or _expired(capture.expires_at)
            or attempt.get("id") != attempt_id
            or int(metadata.get("revision", 0)) != attempt.get("base_revision")
            or not lease_until or lease_until <= _now()):
        db.commit()
        return "stale", capture
    db.query(FoodAnalysisDraft).filter(FoodAnalysisDraft.capture_id == capture.id).delete()
    for index, item in enumerate(items, start=1):
        db.add(FoodAnalysisDraft(capture_id=capture.id, order_num=index, **item))
    corrections = [*metadata.get("corrections", []), attempt["instruction"]][-MAX_REFINEMENT_INSTRUCTIONS:]
    metadata["revision"] = int(metadata.get("revision", 0)) + 1
    metadata["corrections"] = corrections
    metadata.pop("refine_until", None)
    metadata.pop("refine_attempt", None)
    metadata["last_refinement_event_id"] = event_id
    capture.ai_metadata = metadata
    db.commit()
    db.refresh(capture)
    return "updated", capture


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
            "calories": _bounded_float(raw.get("calories"), MAX_CALORIES),
            "protein": _bounded_float(raw.get("protein"), MAX_MACRO_GRAMS),
            "carbs": _bounded_float(raw.get("carbs"), MAX_MACRO_GRAMS),
            "fat": _bounded_float(raw.get("fat"), MAX_MACRO_GRAMS),
            "confidence": _optional_float(raw.get("confidence")),
            "notes": str(raw.get("notes") or "").strip()[:1000] or None,
        })
        if len(items) == MAX_DRAFT_ITEMS:
            break
    return items


def _bounded_float(value: Any, ceiling: float) -> float:
    """Coerce one AI number into [0, ceiling], treating anything unusable as 0.

    The model occasionally answers with a string, a null or a NaN. None of
    those should abort a whole capture, so they become 0 and stay editable.
    """
    try:
        number = float(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if number != number:  # NaN, which every comparison below would silently pass
        return 0.0
    return min(ceiling, max(0.0, number))


def _optional_float(value: Any) -> float | None:
    try:
        number = float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
    if number is None or number != number:
        return None
    return max(0.0, min(1.0, number))


def create_capture(
    db: Session,
    user_id: str,
    source: str,
    items: Iterable[dict[str, Any]],
    source_message_id: str | None = None,
    ai_metadata: dict[str, Any] | None = None,
    used_ai: bool = True,
) -> FoodCapture:
    """Persist one capture and its ordered independent draft items.

    `used_ai` is False when the items came from the food estimate cache. The
    daily allowance exists to stop one user draining the shared Gemini pool,
    and a cached dish never reaches Gemini, so it must not count.
    """
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
        used_ai=used_ai,
        ai_metadata={"revision": 0, **(ai_metadata or {})},
        expires_at=datetime.now(timezone.utc) + CAPTURE_TTL,
    )
    db.add(capture)
    db.flush()
    for index, item in enumerate(normalize_food_result({"items": list(items)}), start=1):
        db.add(FoodAnalysisDraft(capture_id=capture.id, order_num=index, **item))
    db.commit()
    db.refresh(capture)
    return capture


def serialize_capture(capture: FoodCapture) -> dict[str, Any]:
    metadata = capture.ai_metadata or {}
    return {
        "id": capture.id,
        "token": capture.token,
        "source": capture.source,
        "status": capture.status,
        "revision": int(metadata.get("revision", 0)),
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


def get_editable_capture(db: Session, user_id: str, token: str) -> FoodCapture:
    """Return only a live draft for the authenticated LIFF editor."""
    # Serialize the editor's expiry transition with confirm/cancel/update.
    _lock_user(db, user_id)
    capture = _locked_capture(db, user_id, token)
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


def update_capture(db: Session, user_id: str, token: str, items: list[dict[str, Any]], expected_revision: int = 0) -> FoodCapture:
    # Serialize LIFF edits with chat confirmation/cancellation on the parent
    # capture row.  The lock must cover the expiry transition and draft
    # replacement so a stale editor cannot mutate a terminal capture.
    _lock_user(db, user_id)
    capture = _locked_capture(db, user_id, token)
    if not capture:
        raise HTTPException(status_code=404, detail="Food capture not found")
    if capture.status != "draft":
        raise HTTPException(status_code=409, detail="Food capture is no longer editable")
    metadata = _metadata(capture)
    if int(metadata.get("revision", 0)) != expected_revision:
        raise HTTPException(status_code=409, detail="รายการอาหารถูกแก้ไขแล้ว กรุณาเปิดรายการล่าสุดก่อนบันทึก")
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
    metadata["revision"] = expected_revision + 1
    capture.ai_metadata = _invalidate_refinement(metadata)
    db.commit()
    db.refresh(capture)
    return capture


def confirm_capture_result(db: Session, user_id: str, token: str, expected_revision: int = 0) -> CaptureActionResult:
    """Confirm at the lock boundary and retain whether this tap changed state."""
    _lock_user(db, user_id)
    capture = _locked_capture(db, user_id, token)
    if not capture:
        db.commit()
        return CaptureActionResult("missing", [])
    if capture.status == "confirmed":
        if int(_metadata(capture).get("revision", 0)) != expected_revision:
            db.commit()
            return CaptureActionResult("stale", [])
        entries = db.query(FoodLog).filter(FoodLog.capture_id == capture.id, FoodLog.user_id == user_id).all()
        db.commit()
        return CaptureActionResult("already_confirmed", entries)
    if capture.status != "draft":
        db.commit()
        return CaptureActionResult("cancelled", [])
    if int(_metadata(capture).get("revision", 0)) != expected_revision:
        db.commit()
        return CaptureActionResult("stale", [])
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
    capture.ai_metadata = _invalidate_refinement(_metadata(capture))
    db.commit()
    return CaptureActionResult("confirmed", logs)


def confirm_capture(db: Session, user_id: str, token: str, expected_revision: int = 0) -> list[FoodLog]:
    """Keep the API's idempotent list contract for existing callers."""
    result = confirm_capture_result(db, user_id, token, expected_revision)
    return result.entries if result.status in {"confirmed", "already_confirmed"} else []


def cancel_capture_result(db: Session, user_id: str, token: str, expected_revision: int = 0) -> CaptureActionResult:
    """Cancel only a live draft and report the locked state to chat callers."""
    _lock_user(db, user_id)
    capture = _locked_capture(db, user_id, token)
    if not capture:
        db.commit()
        return CaptureActionResult("missing", [])
    if capture.status == "confirmed":
        db.commit()
        return CaptureActionResult("confirmed", [])
    if capture.status == "cancelled":
        db.commit()
        return CaptureActionResult("already_cancelled", [])
    if capture.status != "draft":
        db.commit()
        return CaptureActionResult("unavailable", [])
    if int(_metadata(capture).get("revision", 0)) != expected_revision:
        db.commit()
        return CaptureActionResult("stale", [])
    if _expired(capture.expires_at):
        capture.status = "cancelled"
        capture.cancelled_at = datetime.now(timezone.utc)
        db.commit()
        return CaptureActionResult("expired", [])
    capture.status = "cancelled"
    capture.cancelled_at = datetime.now(timezone.utc)
    capture.ai_metadata = _invalidate_refinement(_metadata(capture))
    db.commit()
    return CaptureActionResult("cancelled", [])


def ai_quota_remaining(db: Session, user_id: str) -> int:
    """What is left of the user's daily AI allowance for this Bangkok day.

    Every path that reaches Gemini leaves a row with `used_ai` set — a food
    capture, lookup, or photo correction — so the allowance is their sum. A
    cached answer leaves `used_ai` false and costs nothing.
    """
    now = datetime.now(BANGKOK)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    end = start + timedelta(days=1)
    used = sum(
        db.query(model).filter(
            model.user_id == user_id,
            model.used_ai.is_(True),
            model.created_at >= start,
            model.created_at < end,
        ).count()
        for model in (FoodCapture, FoodLookup)
    )
    return max(0, int(settings.AI_DAILY_LIMIT) - used)
