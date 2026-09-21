"""Unit tests for the supported LINE Flex Message generators."""

from linebot.v3.messaging import FlexContainer

from app.templates.flex_cards import (
    create_daily_dashboard_card,
    create_food_analyzed_card,
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
    assert len(footer_actions) == 2
    assert any(
        action.get("type") == "postback"
        and "action=confirm_food_capture_chat" in action.get("data", "")
        and "capture_token=test_temp_id" in action.get("data", "")
        for action in footer_actions
    )
    assert any(
        action.get("type") == "uri" and "capture_token=test_temp_id" in action.get("uri", "")
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
    assert "tab=history" in str(card_dict)
    footer_labels = {item["action"]["label"] for item in card_dict["footer"]["contents"]}
    assert "เวท" in footer_labels
    assert "ออกกำลังกาย" not in footer_labels


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
    assert len(carousel_dict["contents"]) == 3
    assert "จัดการรายการคาร์ดิโอ" not in str(carousel_dict)
    assert "action=log_workout&program_id=1" in str(carousel_dict)
    assert "cardio=1" not in str(carousel_dict)


def test_workout_splits_carousel_includes_owned_cardio_presets():
    carousel_dict = create_workout_splits_carousel(
        [],
        cardio_presets=[
            {
                "id": 8,
                "name": "เดินชันหลังเลิกงาน",
                "activity": "เดินชัน",
                "duration_min": 30.0,
                "incline_pct": 8.0,
                "speed_kmh": 5.0,
                "distance_km": None,
            }
        ],
    )

    assert "เดินชันหลังเลิกงาน" in str(carousel_dict)
    assert "action=log_cardio_preset&preset_id=8" in str(carousel_dict)


def test_workout_splits_carousel_caps_saved_cards_and_prioritizes_cardio():
    programs = [{"id": index, "name": f"โปรแกรม {index}", "exercises": []} for index in range(1, 14)]
    strength_only = create_workout_splits_carousel(programs)
    assert len(strength_only["contents"]) == 12
    assert strength_only["contents"][-1]["header"]["contents"][0]["text"] == "โปรแกรม 12"

    carousel_dict = create_workout_splits_carousel(
        programs,
        cardio_presets=[{
            "id": 99,
            "name": "เดินชัน",
            "activity": "เดินชัน",
            "duration_min": 30,
        }],
    )

    contents = carousel_dict["contents"]
    assert len(contents) == 12
    assert contents[-1]["header"]["contents"][0]["text"] == "เดินชัน"
    assert "action=log_cardio_preset&preset_id=99" in str(carousel_dict)
    assert "action=log_workout&program_id=11" in str(carousel_dict)
    assert "action=log_workout&program_id=12" not in str(carousel_dict)
    assert "จัดการรายการคาร์ดิโอ" not in str(carousel_dict)


def test_workout_splits_carousel_empty_state_is_valid_and_optional_link():
    carousel_dict = create_workout_splits_carousel([])

    assert FlexContainer.from_dict(carousel_dict).type == "carousel"
    assert len(carousel_dict["contents"]) == 1
    assert "ยังไม่มีโปรแกรมออกกำลังกาย" in str(carousel_dict)
    assert "tab=programs" in str(carousel_dict)


def test_workout_splits_carousel_empty_state_omits_link_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "LIFF_ID", None)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "WEBAPP_BASE_URL", "")

    carousel_dict = create_workout_splits_carousel([])

    assert FlexContainer.from_dict(carousel_dict).type == "carousel"
    assert '"type": "uri"' not in str(carousel_dict)


def test_workout_splits_saved_cards_share_log_and_edit_actions():
    carousel_dict = create_workout_splits_carousel(
        [{"id": 1, "name": "Push", "exercises": []}],
        cardio_presets=[{"id": 2, "name": "เดิน", "activity": "เดิน", "duration_min": 20}],
    )

    for bubble in carousel_dict["contents"]:
        labels = {item["action"].get("label") for item in bubble["footer"]["contents"]}
        assert labels == {"บันทึกวันนี้", "แก้ไขในเว็บ"}


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
    assert "พิมพ์ เวท" in str(card_dict)
    assert "พิมพ์ ออกกำลังกาย" not in str(card_dict)


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


def test_web_actions_use_liff_deep_link_and_preserve_query_values():
    uri = webapp_uri("today", "capture_token=abc%2F123")

    assert uri == "https://liff.line.me/mock_liff_id/?tab=today&capture_token=abc%2F123"
    assert "user_id" not in uri


def test_webapp_uri_uses_direct_endpoint_only_outside_production(monkeypatch):
    monkeypatch.setattr(settings, "LIFF_ID", None)
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "WEBAPP_BASE_URL", "http://localhost:8000/webapp")

    assert webapp_uri("history") == "http://localhost:8000/webapp?tab=history"

    monkeypatch.setattr(settings, "APP_ENV", "production")
    assert webapp_uri("history") == ""


def test_cards_omit_uri_actions_when_webapp_is_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "LIFF_ID", None)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "WEBAPP_BASE_URL", "")

    cards = [
        create_daily_dashboard_card({"target_kcal": 1800}),
        create_workout_logged_card("เดิน", 100),
        create_welcome_guide_card(),
        create_profile_onboarding_card(),
        create_profile_summary_card({"name": "ผู้ใช้"}),
        create_workout_splits_carousel(
            [{"id": 1, "name": "Push", "exercises": []}],
            cardio_presets=[{"id": 2, "name": "เดิน", "activity": "เดิน", "duration_min": 20}],
        ),
    ]

    assert all('"type": "uri"' not in str(card) for card in cards)
