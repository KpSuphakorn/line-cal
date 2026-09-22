"""Unit tests for the food-capture draft normalization."""
from app.services.food_capture import (
    MAX_CALORIES,
    MAX_DRAFT_ITEMS,
    MAX_MACRO_GRAMS,
    normalize_food_result,
)


def test_normalize_food_result_clamps_negative_values():
    items = normalize_food_result({"items": [{"food_name": "ข้าว", "calories": -5, "protein": -1}]})
    assert items[0]["calories"] == 0.0
    assert items[0]["protein"] == 0.0


def test_normalize_food_result_clamps_unbounded_ai_values():
    """A garbled Gemini response must not write an unbounded value straight to the DB."""
    items = normalize_food_result({"items": [{
        "food_name": "ข้าว",
        "calories": 1e30,
        "protein": 1e30,
        "carbs": 1e30,
        "fat": 1e30,
    }]})
    item = items[0]
    assert item["calories"] == MAX_CALORIES
    assert item["protein"] == MAX_MACRO_GRAMS
    assert item["carbs"] == MAX_MACRO_GRAMS
    assert item["fat"] == MAX_MACRO_GRAMS


def test_normalize_food_result_keeps_plausible_values_unchanged():
    items = normalize_food_result({"items": [{"food_name": "ไข่ต้ม", "calories": 78, "protein": 6.3}]})
    assert items[0]["calories"] == 78.0
    assert items[0]["protein"] == 6.3


def test_an_unparsable_number_does_not_abort_the_whole_capture():
    """A model that answers "ประมาณ 300" should still produce an editable draft."""
    items = normalize_food_result({"items": [{
        "food_name": "ข้าวมันไก่",
        "calories": "ประมาณ 300",
        "protein": [25],
        "carbs": None,
        "fat": float("nan"),
    }]})
    assert len(items) == 1
    assert items[0]["food_name"] == "ข้าวมันไก่"
    assert (items[0]["calories"], items[0]["protein"], items[0]["carbs"], items[0]["fat"]) == (0.0, 0.0, 0.0, 0.0)


def test_a_nan_confidence_is_dropped_rather_than_stored():
    items = normalize_food_result({"items": [{"food_name": "ข้าว", "confidence": float("nan")}]})
    assert items[0]["confidence"] is None


def test_a_runaway_item_count_is_capped():
    """One photo or one typed line is never hundreds of plates."""
    raw = [{"food_name": f"เมนู {index}", "calories": 100} for index in range(200)]
    items = normalize_food_result({"items": raw})

    assert len(items) == MAX_DRAFT_ITEMS
    assert items[0]["food_name"] == "เมนู 0", "the cap keeps the first items, not a random slice"
