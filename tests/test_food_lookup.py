"""`ถาม <อาหาร>`: a calorie estimate that is shown and never logged."""
import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.messaging import FlexContainer
import google
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.models import Base, FoodAnalysisDraft, FoodCapture, FoodLog, FoodLookup, User
from app.services import food_cache
from app.services.ai_chat import parse_food_text
from app.services.fitness import delete_user_account
from app.services.food_capture import ai_quota_remaining
from app.services.line_handler import handle_line_events
from app.templates.flex_cards import create_food_lookup_card

ITEMS = [{"food_name": "ชาไทย", "portion": "1 แก้ว", "calories": 250.0, "protein": 3.0, "carbs": 40.0, "fat": 8.0}]


def get_test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def text_event(text, user_id="lookup-user"):
    event = MagicMock(spec=MessageEvent)
    event.reply_token = "tok"
    event.source = MagicMock()
    event.source.user_id = user_id
    event.message = MagicMock(spec=TextMessageContent)
    event.message.text = text
    event.message.id = f"msg-{text}"
    return event


def use_real_text_parser(monkeypatch, model_output):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    fake_genai = SimpleNamespace(configure=lambda **kwargs: None)
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)
    monkeypatch.setattr(google, "generativeai", fake_genai, raising=False)
    monkeypatch.setattr("app.services.ai_chat.generate_food_json", lambda *args, **kwargs: model_output)
    monkeypatch.setattr("app.services.line_handler.parse_food_text", parse_food_text)


@pytest.fixture
def line(monkeypatch):
    """Patch the LINE boundary and the model; hand back what the test inspects."""
    replies = {"flex": MagicMock(), "text": MagicMock()}
    parser = MagicMock(return_value={"items": ITEMS})
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-real-key")
    monkeypatch.setattr("app.services.line_handler.get_line_clients", lambda: (MagicMock(), MagicMock(), MagicMock()))
    monkeypatch.setattr("app.services.line_handler.reply_flex", replies["flex"])
    monkeypatch.setattr("app.services.line_handler.reply_text", replies["text"])
    monkeypatch.setattr("app.services.line_handler.parse_food_text", parser)
    return replies, parser


def test_a_lookup_answers_with_the_estimate_and_logs_nothing(line):
    replies, parser = line
    db = get_test_db()

    handle_line_events([text_event("ถาม ชาไทย")], db)

    parser.assert_called_once_with("กิน ชาไทย")
    replies["flex"].assert_called_once()
    assert "250 kcal" in json.dumps(replies["flex"].call_args.args[3], ensure_ascii=False)
    assert db.query(FoodCapture).count() == 0, "no draft to confirm"
    assert db.query(FoodLog).count() == 0, "nothing reaches the user's day"


def test_the_lookup_card_offers_nothing_to_tap():
    """A button would suggest the lookup did or could log something."""
    card = create_food_lookup_card({"items": ITEMS})

    assert "footer" not in card
    assert "action" not in json.dumps(card)


def test_lookup_card_shows_every_supported_item_and_matches_its_total():
    items = [
        {"food_name": f"เมนู {i}", "calories": 100, "protein": 1, "carbs": 2, "fat": 3}
        for i in range(1, 21)
    ]

    card = create_food_lookup_card({"items": items})
    FlexContainer.from_dict(card)
    encoded = json.dumps(card, ensure_ascii=False)

    assert "เมนู 20" in encoded
    assert "รวมประมาณ 2000 kcal" in encoded


def test_a_lookup_that_calls_the_model_spends_the_daily_allowance(line):
    """Every Gemini request comes out of the same shared allowance as กิน."""
    db = get_test_db()
    handle_line_events([text_event("ถาม ชาไทย")], db)  # creates the user too
    before = ai_quota_remaining(db, "lookup-user")

    handle_line_events([text_event("ถาม กาแฟเย็น")], db)

    assert ai_quota_remaining(db, "lookup-user") == before - 1


def test_lookup_preserves_capture_prefixes_inside_food_descriptions(line):
    _replies, parser = line
    db = get_test_db()

    handle_line_events([text_event("ถาม เพิ่มชีสในเบอร์เกอร์")], db)

    parser.assert_called_once_with("กิน เพิ่มชีสในเบอร์เกอร์")
    assert food_cache.lookup(db, "เพิ่มชีสในเบอร์เกอร์") == ITEMS


def test_a_cached_lookup_is_free(line):
    _replies, parser = line
    db = get_test_db()
    handle_line_events([text_event("ถาม ชาไทย")], db)
    before = ai_quota_remaining(db, "lookup-user")

    handle_line_events([text_event("ถาม ชาไทย ")], db)

    assert parser.call_count == 1
    assert ai_quota_remaining(db, "lookup-user") == before


def test_looking_a_dish_up_makes_logging_it_later_free(line, monkeypatch):
    """ถาม and กิน share one cache, so checking first never costs twice."""
    _replies, parser = line
    monkeypatch.setattr("app.services.line_handler.require_completed_profile", lambda *args: True)
    db = get_test_db()

    handle_line_events([text_event("ถาม ชาไทย")], db)
    handle_line_events([text_event("กิน ชาไทย")], db)

    assert parser.call_count == 1
    assert db.query(FoodCapture).one().used_ai is False


def test_an_exhausted_allowance_is_reported_and_the_model_is_not_called(line, monkeypatch):
    replies, parser = line
    monkeypatch.setattr("app.services.line_handler.ai_quota_remaining", lambda *args: 0)
    db = get_test_db()

    handle_line_events([text_event("ถาม ชาไทย")], db)

    parser.assert_not_called()
    assert "โควต้า" in replies["text"].call_args.args[2]
    assert db.query(FoodLookup).count() == 0


def test_a_cached_lookup_still_works_after_the_allowance_runs_out(line, monkeypatch):
    replies, parser = line
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "mock-disabled")
    monkeypatch.setattr("app.services.line_handler.ai_quota_remaining", lambda *args: 0)
    db = get_test_db()
    food_cache.store(db, "ชาไทย", ITEMS)

    handle_line_events([text_event("ถาม ชาไทย")], db)

    parser.assert_not_called()
    replies["flex"].assert_called_once()


def test_a_model_failure_gets_an_apology_not_silence(line):
    replies, parser = line
    parser.side_effect = RuntimeError("gemini down")
    db = get_test_db()
    before = ai_quota_remaining(db, "lookup-user")

    handle_line_events([text_event("ถาม ชาไทย")], db)

    replies["flex"].assert_not_called()
    assert "ขออภัย" in replies["text"].call_args.args[2]
    assert db.query(FoodLookup).one().used_ai is True
    assert ai_quota_remaining(db, "lookup-user") == before - 1


def test_ai_unavailable_does_not_fabricate_or_spend_quota(line, monkeypatch):
    replies, parser = line
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "mock-disabled")
    db = get_test_db()
    before = ai_quota_remaining(db, "lookup-user")

    handle_line_events([text_event("ถาม ชาไทย")], db)

    parser.assert_not_called()
    replies["flex"].assert_not_called()
    assert "AI ประเมินอาหารไม่ได้" in replies["text"].call_args.args[2]
    assert db.query(FoodLookup).count() == 0
    assert ai_quota_remaining(db, "lookup-user") == before


@pytest.mark.parametrize("invalid_item", [
    {"food_name": "ชาไทย", "protein": 3, "carbs": 40, "fat": 8},
    {"food_name": "ชาไทย", "calories": "250", "protein": 3, "carbs": 40, "fat": 8},
    {"food_name": "ชาไทย", "calories": float("nan"), "protein": 3, "carbs": 40, "fat": 8},
])
def test_invalid_model_nutrition_is_not_shown_or_cached(line, invalid_item):
    replies, parser = line
    parser.return_value = {"items": [invalid_item]}
    db = get_test_db()

    handle_line_events([text_event("ถาม ชาไทย")], db)

    replies["flex"].assert_not_called()
    assert "ประเมินข้อมูลโภชนาการ" in replies["text"].call_args.args[2]
    assert food_cache.lookup(db, "ชาไทย") is None
    assert db.query(FoodLookup).one().used_ai is True


def test_invalid_cached_nutrition_is_replaced_before_answering(line):
    replies, parser = line
    db = get_test_db()
    food_cache.store(db, "ชาไทย", [{"food_name": "ชาไทย", "calories": 0}])

    handle_line_events([text_event("ถาม ชาไทย")], db)

    parser.assert_called_once_with("กิน ชาไทย")
    replies["flex"].assert_called_once()
    assert food_cache.lookup(db, "ชาไทย") == ITEMS


def test_real_text_parser_preserves_missing_macros_for_lookup_validation(line, monkeypatch):
    replies, _mock_parser = line
    model_output = {"items": [
        {"food_name": "ข้าว", "calories": 200},
        {"food_name": "ไก่", "calories": 250},
    ]}
    use_real_text_parser(monkeypatch, model_output)
    db = get_test_db()

    handle_line_events([text_event("ถาม ข้าวไก่")], db)

    replies["flex"].assert_not_called()
    assert "ประเมินข้อมูลโภชนาการ" in replies["text"].call_args.args[2]
    assert food_cache.lookup(db, "ข้าวไก่") is None
    lookup = db.query(FoodLookup).one()
    assert lookup.used_ai is True


def test_real_parser_mixed_invalid_component_is_rejected_and_not_cached(line, monkeypatch):
    replies, _mock_parser = line
    model_output = {"items": [
        {"food_name": "ข้าว", "calories": 200, "protein": 4, "carbs": 40, "fat": 1},
        "ไก่ 250 kcal",
    ]}
    use_real_text_parser(monkeypatch, model_output)
    db = get_test_db()

    handle_line_events([text_event("ถาม ข้าวไก่")], db)

    replies["flex"].assert_not_called()
    assert "ประเมินข้อมูลโภชนาการ" in replies["text"].call_args.args[2]
    assert food_cache.lookup(db, "ข้าวไก่") is None


def test_real_parser_rejects_missing_plus_item_without_caching(line, monkeypatch):
    replies, _mock_parser = line
    model_output = {"items": [ITEMS[0]]}
    use_real_text_parser(monkeypatch, model_output)
    db = get_test_db()

    handle_line_events([text_event("ถาม ชาไทย + กาแฟเย็น")], db)

    replies["flex"].assert_not_called()
    assert "แยกรายการ" in replies["text"].call_args.args[2]
    assert food_cache.lookup(db, "ชาไทย + กาแฟเย็น") is None


@pytest.mark.parametrize(("dish", "items"), [
    ("ถาม ชาไทย", [{"food_name": " ", "calories": 250, "protein": 3, "carbs": 40, "fat": 8}]),
    ("ถาม ชาไทย + กาแฟ", [
        {"food_name": "ชาไทย", "calories": 250, "protein": 3, "carbs": 40, "fat": 8},
        {"food_name": " ", "calories": 100, "protein": 1, "carbs": 10, "fat": 2},
    ]),
])
def test_real_parser_rejects_missing_food_names(line, monkeypatch, dish, items):
    replies, _mock_parser = line
    use_real_text_parser(monkeypatch, {"items": items})
    db = get_test_db()

    handle_line_events([text_event(dish)], db)

    replies["flex"].assert_not_called()
    assert "ประเมินข้อมูลโภชนาการ" in replies["text"].call_args.args[2]
    assert db.query(FoodLookup).one().used_ai is True
    assert food_cache.lookup(db, dish.removeprefix("ถาม ")) is None


def test_real_parser_keeps_mixed_invalid_capture_editable(line, monkeypatch):
    _replies, _mock_parser = line
    model_output = {"items": [
        {"food_name": "ข้าว", "calories": 200, "protein": 4, "carbs": 40, "fat": 1},
        "ไก่ 250 kcal",
    ]}
    use_real_text_parser(monkeypatch, model_output)
    monkeypatch.setattr("app.services.line_handler.require_completed_profile", lambda *args: True)
    db = get_test_db()

    handle_line_events([text_event("กิน ข้าวไก่")], db)

    capture = db.query(FoodCapture).one()
    draft = db.query(FoodAnalysisDraft).one()
    assert capture.status == "draft"
    assert (draft.calories, draft.protein, draft.carbs, draft.fat) == (0, 0, 0, 0)


def test_real_parser_sums_numeric_strings_for_editable_food_capture(line, monkeypatch):
    replies, _mock_parser = line
    model_output = {"items": [
        {"food_name": "ข้าว", "calories": "200", "protein": "4", "carbs": 40, "fat": 1},
        {"food_name": "ไก่", "calories": "250", "protein": "25", "carbs": 0, "fat": 8},
    ]}
    use_real_text_parser(monkeypatch, model_output)
    monkeypatch.setattr("app.services.line_handler.require_completed_profile", lambda *args: True)
    db = get_test_db()

    handle_line_events([text_event("กิน ข้าวไก่")], db)

    draft = db.query(FoodAnalysisDraft).one()
    assert draft.calories == 450
    assert draft.protein == 29
    replies["flex"].assert_called_once()


def test_real_parser_does_not_treat_blank_numeric_string_as_zero_for_lookup(line, monkeypatch):
    replies, _mock_parser = line
    model_output = {"items": [
        {"food_name": "ข้าว", "calories": 200, "protein": 4, "carbs": 40, "fat": 1},
        {"food_name": "ไก่", "calories": 250, "protein": 25, "carbs": " ", "fat": 8},
    ]}
    use_real_text_parser(monkeypatch, model_output)
    db = get_test_db()

    handle_line_events([text_event("ถาม ข้าวไก่")], db)

    replies["flex"].assert_not_called()
    assert "ประเมินข้อมูลโภชนาการ" in replies["text"].call_args.args[2]
    assert food_cache.lookup(db, "ข้าวไก่") is None


def test_lookup_rejects_more_items_than_supported_before_calling_model(line):
    replies, parser = line
    db = get_test_db()
    dish = " + ".join(f"เมนู {index}" for index in range(21))

    handle_line_events([text_event(f"ถาม {dish}")], db)

    parser.assert_not_called()
    assert "ไม่เกิน 20 รายการ" in replies["text"].call_args.args[2]


@pytest.mark.parametrize("command", ["ถาม +", "ถาม + +"])
def test_lookup_without_a_dish_does_not_call_model_or_spend_quota(line, command):
    replies, parser = line
    db = get_test_db()
    before = ai_quota_remaining(db, "lookup-user")

    handle_line_events([text_event(command)], db)

    parser.assert_not_called()
    assert "ถาม ชาไทย" in replies["text"].call_args.args[2]
    assert db.query(FoodLookup).count() == 0
    assert ai_quota_remaining(db, "lookup-user") == before


def test_malformed_food_capture_stays_editable_but_is_not_cached(line, monkeypatch):
    _replies, parser = line
    parser.return_value = {"items": [{"food_name": "ชาไทย", "calories": "ไม่ทราบ"}]}
    monkeypatch.setattr("app.services.line_handler.require_completed_profile", lambda *args: True)
    db = get_test_db()

    handle_line_events([text_event("กิน ชาไทย")], db)

    capture = db.query(FoodCapture).one()
    draft = db.query(FoodAnalysisDraft).one()
    assert capture.status == "draft"
    assert draft.calories == 0, "existing editable capture behavior is preserved"
    assert food_cache.lookup(db, "ชาไทย") is None


def test_bare_ask_without_a_dish_falls_through_to_the_guide(line):
    replies, parser = line
    db = get_test_db()

    handle_line_events([text_event("ถาม")], db)

    parser.assert_not_called()
    assert replies["flex"].call_args.args[2] == "วิธีใช้ LINE Cal"


def test_deleting_the_account_removes_its_lookups(line):
    """Postgres enforces the foreign key that SQLite ignores, so a lookup left
    behind would make account deletion fail in production only."""
    db = get_test_db()
    handle_line_events([text_event("ถาม ชาไทย")], db)
    assert db.query(FoodLookup).count() == 1

    assert delete_user_account(db, "lookup-user") is True

    assert db.query(FoodLookup).count() == 0
    assert db.query(User).count() == 0
