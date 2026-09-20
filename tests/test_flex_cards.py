"""Unit tests for the supported LINE Flex Message generators."""

from linebot.v3.messaging import FlexContainer

from app.templates.flex_cards import (
    create_daily_dashboard_card,
    create_food_analyzed_card,
    create_history_card,
    create_profile_onboarding_card,
    create_profile_summary_card,
    create_text_food_card,
    create_welcome_guide_card,
    create_workout_logged_card,
    create_workout_splits_carousel,
    webapp_uri,
)
from app.config import settings


def test_food_analyzed_card_valid():
    """Food analysis supports several independent items and edit/confirm actions."""
    food_sample = {
        "items": [
            {
                "food_name": "ข้าวกะเพราอกไก่",
                "portion": "1 จาน",
                "calories": 450.0,
                "protein": 32.0,
                "carbs": 52.0,
                "fat": 12.0,
            },
            {
                "food_name": "ไข่ดาว",
                "portion": "1 ฟอง",
                "calories": 120.0,
                "protein": 7.0,
                "carbs": 1.0,
                "fat": 9.0,
            },
        ]
    }
    card_dict = create_food_analyzed_card(food_sample, "test_temp_id")
    container = FlexContainer.from_dict(card_dict)
    assert container.type == "bubble"
    assert "2 รายการ" in card_dict["header"]["contents"][0]["text"]
    footer_actions = [item["action"] for item in card_dict["footer"]["contents"]]
    assert any(action.get("label") == "✏️ แก้ไขรายการ" for action in footer_actions)
    assert any(
        action.get("data") == "action=confirm_food_capture&capture_token=test_temp_id"
        for action in footer_actions
    )


def test_daily_dashboard_card_valid():
    summary_sample = {
        "user_id": "user_test",
        "date": "2026-09-19",
        "date_display": "19/09/2026",
        "target_kcal": 1950.0,
        "calories_in": 1200.0,
        "calories_burned": 580.0,
        "remaining_kcal": 1330.0,
        "pct_consumed": 61.5,
        "protein": 110.0,
        "target_protein": 145.0,
        "carbs": 140.0,
        "target_carbs": 220.0,
        "fat": 40.0,
        "target_fat": 55.0,
        "food_logs": [
            {"id": 1, "name": "กล้วยหอม 1 ลูก", "calories": 105.0, "time": "09:45"}
        ],
    }
    card_dict = create_daily_dashboard_card(summary_sample, last_food_id=1)
    container = FlexContainer.from_dict(card_dict)
    assert container.type == "bubble"
    assert "วันนี้" in card_dict["header"]["contents"][0]["text"]
    assert "action=view_history" in str(card_dict)


def test_workout_splits_carousel_valid():
    """User programs and Cardio share one workout card."""
    programs = [
        {
            "id": 1,
            "name": "Push",
            "exercises": [{"name": "Bench press", "sets": 3, "repetitions": 8}],
        },
        {
            "id": 2,
            "name": "Pull",
            "exercises": [{"name": "Lat pulldown", "sets": 3, "repetitions": 10}],
        },
        {"id": 3, "name": "Legs", "exercises": []},
    ]
    carousel_dict = create_workout_splits_carousel(programs)
    container = FlexContainer.from_dict(carousel_dict)
    assert container.type == "carousel"
    assert len(carousel_dict["contents"]) == 4
    assert carousel_dict["contents"][-1]["header"]["contents"][0]["text"] == "🏃 Cardio"
    assert "action=log_workout&program_id=1" in str(carousel_dict)


def test_workout_logged_card_valid():
    card_dict = create_workout_logged_card("Push", 300.0, 1650.0)
    container = FlexContainer.from_dict(card_dict)
    assert container.type == "bubble"
    assert "300 kcal" in str(card_dict)


def test_text_food_card_valid():
    food_sample = {
        "food_name": "ข้าวมันไก่ต้ม",
        "portion": "1 จาน",
        "calories": 596.0,
        "protein": 24.0,
        "carbs": 68.0,
        "fat": 25.0,
    }
    card_dict = create_text_food_card(food_sample, "test_text_temp_id")
    container = FlexContainer.from_dict(card_dict)
    assert container.type == "bubble"


def test_welcome_guide_card_valid():
    card_dict = create_welcome_guide_card()
    container = FlexContainer.from_dict(card_dict)
    assert container.type == "bubble"
    assert "กิน" in str(card_dict)
    assert "ออกกำลังกาย" in str(card_dict)


def test_profile_cards_valid():
    onboarding = create_profile_onboarding_card()
    profile = create_profile_summary_card(
        {
            "name": "Suphakorn",
            "daily_target_kcal": 1950.0,
            "target_protein_g": 145.0,
        }
    )
    assert FlexContainer.from_dict(onboarding).type == "bubble"
    assert FlexContainer.from_dict(profile).type == "bubble"
    assert "tab=profile" in str(profile)


def test_history_card_opens_history_tab():
    card_dict = create_history_card()
    container = FlexContainer.from_dict(card_dict)
    assert container.type == "bubble"
    action = card_dict["footer"]["contents"][0]["action"]
    assert "tab=history" in action["uri"]


def test_web_actions_use_liff_deep_link_and_preserve_query_values():
    uri = webapp_uri("today", "capture_token=abc%2F123&cardio=1")

    assert uri == "https://liff.line.me/mock_liff_id/?tab=today&capture_token=abc%2F123&cardio=1"
    assert "user_id" not in uri


def test_webapp_uri_uses_direct_endpoint_only_outside_production(monkeypatch):
    monkeypatch.setattr(settings, "LIFF_ID", None)
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "WEBAPP_BASE_URL", "http://localhost:8000/webapp")

    assert webapp_uri("history") == "http://localhost:8000/webapp?tab=history"

    monkeypatch.setattr(settings, "APP_ENV", "production")
    assert webapp_uri("history") == ""
