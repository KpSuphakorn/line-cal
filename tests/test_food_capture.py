"""Unit tests for the food-capture draft normalization."""
from app.services.food_capture import MAX_CALORIES, MAX_MACRO_GRAMS, normalize_food_result


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
