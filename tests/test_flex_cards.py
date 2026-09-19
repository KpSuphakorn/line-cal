"""Unit tests for LINE Flex Message generators."""
import pytest
from linebot.v3.messaging import FlexContainer

from app.templates.flex_cards import (
    create_food_analyzed_card,
    create_daily_dashboard_card,
    create_workout_splits_carousel,
    create_quick_snacks_card,
    create_workout_logged_card,
    create_weekly_stats_card,
    create_food_history_card
)


def test_food_analyzed_card_valid():
    """Verify food analyzed card generates a valid FlexContainer."""
    food_sample = {
        "food_name": "ข้าวกะเพราอกไก่ไข่ดาว",
        "portion": "1 จาน (ข้าว 150g, ไก่ 120g)",
        "calories": 520.0,
        "protein": 34.0,
        "carbs": 58.0,
        "fat": 14.0,
        "notes": "โปรตีนสูง เหมาะกับช่วงสร้างกล้ามเนื้อ"
    }
    card_dict = create_food_analyzed_card(food_sample, "test_temp_id")
    container = FlexContainer.from_dict(card_dict)
    assert container.type == "bubble"


def test_daily_dashboard_card_valid():
    """Verify daily dashboard card generates a valid FlexContainer."""
    summary_sample = {
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
            {"id": 1, "name": "กล้วยหอม 1 ลูก", "portion": "Pre-workout", "calories": 105.0, "time": "09:45"}
        ],
        "workout_logs": [
            {"id": 1, "name": "Day 1: Push", "duration": 60, "burned": 300.0, "time": "11:00"}
        ]
    }
    card_dict = create_daily_dashboard_card(summary_sample)
    container = FlexContainer.from_dict(card_dict)
    assert container.type == "bubble"


def test_workout_splits_carousel_valid():
    """Verify workout carousel generates a valid FlexContainer."""
    carousel_dict = create_workout_splits_carousel()
    container = FlexContainer.from_dict(carousel_dict)
    assert container.type == "carousel"
    # Should have Day 1, 2, 3, 4 + Cardio = 5 bubbles
    assert len(carousel_dict["contents"]) == 5


def test_quick_snacks_card_valid():
    """Verify quick snacks menu generates a valid FlexContainer."""
    card_dict = create_quick_snacks_card()
    container = FlexContainer.from_dict(card_dict)
    assert container.type == "bubble"


def test_workout_logged_card_valid():
    """Verify workout confirmation card generates a valid FlexContainer."""
    card_dict = create_workout_logged_card("Day 1: Push", 300.0, 1650.0)
    container = FlexContainer.from_dict(card_dict)
    assert container.type == "bubble"


def test_weekly_stats_card_valid():
    """Verify weekly stats card generates a valid FlexContainer."""
    sample_stats = {
        "start_date": "13/09",
        "end_date": "19/09",
        "days_logged": 5,
        "total_calories_in": 9800.0,
        "total_calories_burned": 2100.0,
        "avg_daily_calories": 1960.0,
        "target_kcal": 1950.0,
        "avg_daily_protein": 142.0,
        "target_protein": 145.0,
        "split_done": {
            "day_1": True,
            "day_2": True,
            "day_3": True,
            "day_4": False
        },
        "weights_completed": 3,
        "weights_target": 4,
        "cardio_count": 2,
        "cardio_target": 2,
        "cardio_minutes": 90
    }
    card_dict = create_weekly_stats_card(sample_stats)
    container = FlexContainer.from_dict(card_dict)
    assert container.type == "bubble"


def test_food_history_card_valid():
    """Verify food history card generates a valid FlexContainer."""
    sample_history = [
        {
            "id": 1,
            "name": "ข้าวกะเพราอกไก่ไข่ดาว",
            "portion": "1 จาน",
            "calories": 520,
            "protein": 34.0,
            "carbs": 58.0,
            "fat": 14.0,
            "date": "19/09",
            "time": "12:30"
        }
    ]
    card_dict = create_food_history_card(sample_history)
    container = FlexContainer.from_dict(card_dict)
    assert container.type == "bubble"
