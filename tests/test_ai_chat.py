"""Unit tests for AI chat food parser."""
from app.services.ai_chat import parse_food_text


def test_parse_food_text_fallback():
    """Text input uses the same independent-item shape as image analysis."""
    res = parse_food_text("กิน ข้าวมันไก่ต้ม")
    assert isinstance(res["items"], list)
    assert len(res["items"]) == 1
    item = res["items"][0]
    assert item["food_name"] == "ข้าวมันไก่ต้ม"
    assert item["calories"] > 0
    assert item["protein"] >= 0
    assert item["carbs"] >= 0
    assert item["fat"] >= 0
