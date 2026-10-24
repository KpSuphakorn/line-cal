"""Photo corrections stay on the existing owner-scoped food capture."""
import io
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from PIL import Image
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.models import Base, FoodAnalysisDraft, FoodCapture, FoodLog, FoodLookup, User
from app.services import food_capture
from app.services.food_capture import create_capture
from app.services.fitness import delete_user_account
from app.services.line_handler import handle_food_refinement_text, handle_text_message


def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _png():
    image = Image.new("RGB", (8, 8), "white")
    output = io.BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def _user(db, user_id):
    db.add(User(id=user_id))
    db.commit()


def _photo(db, owner, name="ข้าวไก่"):
    return create_capture(db, owner, "image", [{
        "food_name": name, "portion": "1 จาน", "calories": 500,
        "protein": 25, "carbs": 60, "fat": 15,
    }], source_message_id="line-photo-1")


def _event():
    event = MagicMock()
    event.reply_token = "reply-token"
    return event


def test_selected_owner_photo_is_the_only_context_and_reselection_fences_old_cancel():
    db = db_session()
    _user(db, "owner")
    first = _photo(db, "owner")
    second = create_capture(db, "owner", "image", [{
        "food_name": "ชาเย็น", "calories": 200, "protein": 2, "carbs": 40, "fat": 3,
    }], source_message_id="line-photo-2")

    assert food_capture.select_food_refinement(db, "other", first.token, 0)[0] == "missing"
    assert food_capture.select_food_refinement(db, "owner", first.token, 0)[0] == "selected"
    old_context = first.ai_metadata["refine_context_id"]
    state, first_attempt = food_capture.claim_food_refinement(db, "owner", "ครึ่งจาน", "redelivered-event")
    assert state == "claimed"
    assert food_capture.reserve_food_refinement_quota(db, "owner", first.token, first_attempt["attempt_id"]) == "reserved"
    food_capture.release_food_refinement(db, "owner", first.token, first_attempt["attempt_id"])
    assert food_capture.select_food_refinement(db, "owner", second.token, 0)[0] == "selected"
    new_context = second.ai_metadata["refine_context_id"]
    assert old_context != new_context
    assert food_capture.cancel_food_refinement(db, "owner", second.token, 0, old_context) == "stale"
    assert food_capture.select_food_refinement(db, "owner", second.token, 0)[0] == "selected"
    newest_context = second.ai_metadata["refine_context_id"]
    assert newest_context != new_context
    assert food_capture.cancel_food_refinement(db, "owner", second.token, 0, new_context) == "stale"
    assert food_capture.claim_food_refinement(db, "owner", "อย่าคิดซ้ำ", "redelivered-event")[0] == "consumed"

    status, claim = food_capture.claim_food_refinement(db, "owner", "กินแค่ครึ่งแก้ว", "event-b")
    assert status == "claimed"
    assert claim["token"] == second.token
    assert claim["source_message_id"] == "line-photo-2"


def test_plain_chat_correction_reuses_original_image_and_accumulates_context(monkeypatch):
    db = db_session()
    _user(db, "owner")
    capture = _photo(db, "owner")
    food_capture.select_food_refinement(db, "owner", capture.token, 0)
    monkeypatch.setattr("app.services.line_handler.settings.GEMINI_API_KEY", "test-real-key")
    blob = MagicMock()
    blob.get_message_content.return_value = _png()
    observed = []

    def analyze(image, correction_prompt=None, prepared_image=None):
        assert not db.in_transaction()
        assert prepared_image.size == (8, 8)
        observed.append((image, correction_prompt))
        name, calories = ("ข้าวหมู", 300) if len(observed) == 1 else ("ข้าวหมูไม่ติดหนัง", 280)
        return {"items": [{
            "food_name": name, "portion": "กินครึ่งจาน", "calories": calories,
            "protein": 18, "carbs": 32, "fat": 12,
        }]}

    monkeypatch.setattr("app.services.line_handler.analyze_food_image", analyze)
    replies = MagicMock()
    replies.reply_message.side_effect = lambda *_args, **_kwargs: (
        None if not db.in_transaction() else pytest.fail("LINE reply sent inside DB transaction")
    )
    blob.get_message_content.side_effect = lambda *_args: (
        _png() if not db.in_transaction() else pytest.fail("LINE blob read inside DB transaction")
    )
    assert handle_food_refinement_text(_event(), "owner", "เป็นหมู กินแค่ครึ่งจาน", "event-1", replies, db, blob)
    assert observed[0][0] == _png()
    assert "ข้าวไก่" in observed[0][1]
    assert "เป็นหมู กินแค่ครึ่งจาน" in observed[0][1]
    assert "ห้ามลดหรือคูณปริมาณซ้ำ" in observed[0][1]
    assert blob.get_message_content.call_args.args == ("line-photo-1",)
    assert db.query(FoodLookup).filter_by(user_id="owner", used_ai=True).count() == 1
    assert db.query(FoodLog).filter_by(user_id="owner").count() == 0
    assert db.query(FoodCapture).filter_by(token=capture.token).one().status == "draft"
    assert db.query(FoodAnalysisDraft).filter_by(capture_id=capture.id).one().food_name == "ข้าวหมู"
    assert db.query(FoodCapture).filter_by(token=capture.token).one().ai_metadata["revision"] == 1
    card = replies.reply_message.call_args.args[0].messages[0].contents.to_dict()
    assert "action=confirm_food_capture_chat" in str(card)
    assert "revision=1" in str(card)
    assert "action=refine_food_capture_chat" in str(card)
    assert "action=cancel_food_capture_chat" in str(card)
    assert "แก้ไขรายการ" in str(card)

    db.commit()
    assert food_capture.select_food_refinement(db, "owner", capture.token, 1)[0] == "selected"
    event = _event()
    event.message.text = "น้ำแก้วขวาเป็นน้ำเปล่า"
    event.webhook_event_id = "event-2"
    handle_text_message(event, "owner", replies, db, blob)
    assert len(observed) == 2
    assert "เป็นหมู กินแค่ครึ่งจาน" in observed[1][1]
    assert "น้ำแก้วขวาเป็นน้ำเปล่า" in observed[1][1]
    assert "ข้าวหมู" in observed[1][1]
    assert db.query(FoodAnalysisDraft).filter_by(capture_id=capture.id).one().food_name == "ข้าวหมูไม่ติดหนัง"
    second_card = replies.reply_message.call_args.args[0].messages[0].contents.to_dict()
    assert "action=confirm_food_capture_chat" in str(second_card)
    assert "action=refine_food_capture_chat" in str(second_card)
    assert "แก้ไขรายการ" in str(second_card)

    # A successful correction is one-shot; plain text is no longer interpreted as another edit.
    event.message.text = "ลดน้ำตาลลงอีกนิด"
    event.webhook_event_id = "event-3"
    handle_text_message(event, "owner", replies, db, blob)
    assert len(observed) == 2
    assert "วิธีใช้ LINE Cal" in str(replies.reply_message.call_args.args[0])


def test_invalid_image_does_not_charge_quota_or_replace_original_draft(monkeypatch):
    db = db_session()
    _user(db, "owner")
    capture = _photo(db, "owner")
    food_capture.select_food_refinement(db, "owner", capture.token, 0)
    monkeypatch.setattr("app.services.line_handler.settings.GEMINI_API_KEY", "test-real-key")
    blob = MagicMock()
    blob.get_message_content.side_effect = RuntimeError("content expired")
    reply = MagicMock()
    handle_food_refinement_text(_event(), "owner", "กินครึ่งจาน", "event-expired", reply, db, blob)
    assert db.query(FoodLookup).count() == 0
    assert db.query(FoodAnalysisDraft).filter_by(capture_id=capture.id).one().food_name == "ข้าวไก่"
    assert "ส่งรูปอาหารใหม่" in reply.reply_message.call_args.args[0].messages[0].text


def test_provider_failure_preserves_draft_and_redelivery_does_not_call_or_charge_twice(monkeypatch):
    db = db_session()
    _user(db, "owner")
    capture = _photo(db, "owner")
    food_capture.select_food_refinement(db, "owner", capture.token, 0)
    monkeypatch.setattr("app.services.line_handler.settings.GEMINI_API_KEY", "test-real-key")
    blob = MagicMock()
    blob.get_message_content.return_value = _png()
    provider = MagicMock(side_effect=RuntimeError("provider offline"))
    monkeypatch.setattr("app.services.line_handler.analyze_food_image", provider)
    reply = MagicMock()

    handle_food_refinement_text(_event(), "owner", "กินครึ่งจาน", "retry-event", reply, db, blob)
    handle_food_refinement_text(_event(), "owner", "กินครึ่งจาน", "retry-event", reply, db, blob)

    assert provider.call_count == 1
    assert db.query(FoodLookup).filter_by(user_id="owner", used_ai=True).count() == 1
    assert db.query(FoodAnalysisDraft).filter_by(capture_id=capture.id).one().food_name == "ข้าวไก่"


@pytest.mark.parametrize("provider_result", [
    RuntimeError("provider offline"),
    {"items": [{"food_name": "ข้าวหมู", "calories": "ไม่ทราบ", "protein": 10, "carbs": 20, "fat": 5}]},
])
def test_provider_error_or_malformed_result_spends_once_and_preserves_draft(monkeypatch, provider_result):
    db = db_session()
    _user(db, "owner")
    capture = _photo(db, "owner")
    food_capture.select_food_refinement(db, "owner", capture.token, 0)
    monkeypatch.setattr("app.services.line_handler.settings.GEMINI_API_KEY", "test-real-key")

    blob = MagicMock()
    blob.get_message_content.side_effect = lambda *_args: (
        _png() if not db.in_transaction() else pytest.fail("LINE blob read inside DB transaction")
    )
    if isinstance(provider_result, Exception):
        provider = MagicMock(side_effect=provider_result)
    else:
        provider = MagicMock(return_value=provider_result)

    def provider_without_transaction(*args, **kwargs):
        assert not db.in_transaction()
        return provider(*args, **kwargs)

    monkeypatch.setattr("app.services.line_handler.analyze_food_image", provider_without_transaction)
    reply = MagicMock()
    reply.reply_message.side_effect = lambda *_args, **_kwargs: (
        None if not db.in_transaction() else pytest.fail("LINE reply sent inside DB transaction")
    )
    handle_food_refinement_text(_event(), "owner", "กินครึ่งจาน", "provider-event", reply, db, blob)

    provider.assert_called_once()
    assert db.query(FoodLookup).filter_by(user_id="owner", used_ai=True).count() == 1
    assert db.query(FoodAnalysisDraft).filter_by(capture_id=capture.id).one().food_name == "ข้าวไก่"


def test_quota_exhaustion_skips_provider_and_does_not_reserve(monkeypatch):
    db = db_session()
    _user(db, "owner")
    capture = _photo(db, "owner")
    food_capture.select_food_refinement(db, "owner", capture.token, 0)
    monkeypatch.setattr("app.services.line_handler.settings.GEMINI_API_KEY", "test-real-key")
    monkeypatch.setattr(settings, "AI_DAILY_LIMIT", 0)
    blob = MagicMock()
    blob.get_message_content.side_effect = lambda *_args: (
        _png() if not db.in_transaction() else pytest.fail("LINE blob read inside DB transaction")
    )
    provider = MagicMock()
    monkeypatch.setattr("app.services.line_handler.analyze_food_image", provider)
    reply = MagicMock()
    reply.reply_message.side_effect = lambda *_args, **_kwargs: (
        None if not db.in_transaction() else pytest.fail("LINE reply sent inside DB transaction")
    )

    handle_food_refinement_text(_event(), "owner", "กินครึ่งจาน", "quota-event", reply, db, blob)

    provider.assert_not_called()
    assert db.query(FoodLookup).count() == 0
    assert db.query(FoodAnalysisDraft).filter_by(capture_id=capture.id).one().food_name == "ข้าวไก่"


def test_manual_edit_fences_late_ai_and_duplicate_event_cannot_charge_twice():
    db = db_session()
    _user(db, "owner")
    capture = _photo(db, "owner")
    food_capture.select_food_refinement(db, "owner", capture.token, 0)
    state, claim = food_capture.claim_food_refinement(db, "owner", "ครึ่งจาน", "event-once")
    assert state == "claimed"
    assert food_capture.reserve_food_refinement_quota(db, "owner", capture.token, claim["attempt_id"]) == "reserved"

    food_capture.update_capture(db, "owner", capture.token, [{
        "food_name": "แก้เอง", "calories": 250, "protein": 10, "carbs": 30, "fat": 5,
    }], expected_revision=0)
    status, _ = food_capture.apply_food_refinement(db, "owner", capture.token, claim["attempt_id"], "event-once", [{
        "food_name": "ผลเก่า", "portion": "1", "calories": 500, "protein": 25, "carbs": 60, "fat": 15,
    }])
    assert status == "stale"
    assert db.query(FoodAnalysisDraft).filter_by(capture_id=capture.id).one().food_name == "แก้เอง"
    food_capture.release_food_refinement(db, "owner", capture.token, claim["attempt_id"])
    assert food_capture.claim_food_refinement(db, "owner", "ครึ่งจาน", "event-once")[0] == "consumed"
    assert db.query(FoodLookup).filter_by(user_id="owner", used_ai=True).count() == 1


def test_expired_selection_and_explicit_legacy_command_exit_refinement_mode():
    db = db_session()
    _user(db, "owner")
    capture = _photo(db, "owner")
    food_capture.select_food_refinement(db, "owner", capture.token, 0)
    capture.ai_metadata = {**capture.ai_metadata, "refine_until": "2000-01-01T00:00:00+00:00"}
    db.commit()
    assert food_capture.claim_food_refinement(db, "owner", "ครึ่งจาน", "expired-event")[0] == "expired"

    food_capture.select_food_refinement(db, "owner", capture.token, 0)
    event = MagicMock()
    event.reply_token = "reply"
    event.message.text = "โปรแกรม"
    handle_text_message(event, "owner", MagicMock(), db, MagicMock())
    assert "refine_until" not in db.query(FoodCapture).filter_by(token=capture.token).one().ai_metadata
    assert db.query(FoodLookup).count() == 0


@pytest.mark.parametrize("terminal_action,expected_status", [("confirm", "confirmed"), ("cancel", "cancelled")])
def test_confirm_or_cancel_during_request_prevents_late_result_and_deleted_owner_is_not_recreated(terminal_action, expected_status):
    db = db_session()
    _user(db, "owner")
    capture = _photo(db, "owner")
    token = capture.token
    food_capture.select_food_refinement(db, "owner", capture.token, 0)
    state, claim = food_capture.claim_food_refinement(db, "owner", "ครึ่งจาน", "event-late")
    assert state == "claimed"
    assert food_capture.reserve_food_refinement_quota(db, "owner", capture.token, claim["attempt_id"]) == "reserved"
    action = food_capture.confirm_capture_result if terminal_action == "confirm" else food_capture.cancel_capture_result
    assert action(db, "owner", capture.token, 0).status == expected_status
    assert food_capture.apply_food_refinement(db, "owner", token, claim["attempt_id"], "event-late", [{
        "food_name": "ไม่ควรเขียน", "portion": "1", "calories": 1, "protein": 1, "carbs": 1, "fat": 1,
    }])[0] == "stale"

    assert delete_user_account(db, "owner")
    assert food_capture.apply_food_refinement(db, "owner", token, claim["attempt_id"], "event-late", [{
        "food_name": "ไม่ควรเขียน", "portion": "1", "calories": 1, "protein": 1, "carbs": 1, "fat": 1,
    }])[0] == "missing"
    assert db.query(User).filter_by(id="owner").count() == 0
    assert db.query(FoodCapture).filter_by(user_id="owner").count() == 0
    assert db.query(FoodLookup).filter_by(user_id="owner").count() == 0


def test_expired_attempt_lease_cannot_apply_result():
    db = db_session()
    _user(db, "owner")
    capture = _photo(db, "owner")
    food_capture.select_food_refinement(db, "owner", capture.token, 0)
    state, claim = food_capture.claim_food_refinement(db, "owner", "ครึ่งจาน", "lease-event")
    assert state == "claimed"
    metadata = dict(capture.ai_metadata)
    attempt = dict(metadata["refine_attempt"])
    attempt["lease_until"] = "2000-01-01T00:00:00+00:00"
    metadata["refine_attempt"] = attempt
    capture.ai_metadata = metadata
    db.commit()

    status, _ = food_capture.apply_food_refinement(db, "owner", capture.token, claim["attempt_id"], "lease-event", [{
        "food_name": "ไม่ควรใช้", "portion": "1", "calories": 1, "protein": 1, "carbs": 1, "fat": 1,
    }])

    assert status == "stale"
    assert db.query(FoodAnalysisDraft).filter_by(capture_id=capture.id).one().food_name == "ข้าวไก่"


def test_food_correction_quota_uses_bangkok_day_boundary(monkeypatch):
    db = db_session()
    _user(db, "owner")
    monkeypatch.setattr(settings, "AI_DAILY_LIMIT", 5)
    local_midnight = datetime.now(ZoneInfo("Asia/Bangkok")).replace(hour=0, minute=0, second=0, microsecond=0)
    previous_day = (local_midnight - timedelta(seconds=1)).astimezone(timezone.utc)
    db.add(FoodLookup(user_id="owner", used_ai=True, created_at=previous_day))
    db.commit()

    assert food_capture.ai_quota_remaining(db, "owner") == 5
    db.add(FoodLookup(user_id="owner", used_ai=True, created_at=datetime.now(timezone.utc)))
    db.commit()
    assert food_capture.ai_quota_remaining(db, "owner") == 4
