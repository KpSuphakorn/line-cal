"""Gemini AI Text-based Food Parsing Engine for natural language food logging."""
import logging
from typing import Dict, Any

from app.config import settings
from app.services.ai_errors import generate_food_json

logger = logging.getLogger(__name__)

ITEM_SEPARATOR = "+"

FOOD_PARSE_PROMPT = """คุณเป็นนักโภชนาการ AI ผู้เชี่ยวชาญด้านอาหารไทยและอาหารสากล
ผู้ใช้จะพิมพ์รายการอาหารที่กินเข้ามา จงประเมินปริมาณสารอาหารให้แม่นยำที่สุด

กฎสำคัญ:
- ผู้ใช้เป็นคนกำหนดว่ามีกี่รายการ ไม่ใช่คุณ จงตอบกลับตามจำนวนรายการที่ระบุเท่านั้น
- หนึ่งรายการคือหนึ่งจานที่สั่ง ห้ามแยกเป็นส่วนประกอบย่อย
  (เช่น "ข้าวเนื้อทอดผัดพริกเกลือไข่ข้น" คือ 1 รายการ ไม่ใช่ ข้าวสวย + เนื้อทอด + ไข่ข้น)
- ใช้ชื่อตามที่ผู้ใช้พิมพ์มา ไม่ต้องเปลี่ยนเป็นชื่ออื่น
- ถ้าผู้ใช้ระบุจำนวน ให้คำนวณตามจำนวนนั้น (เช่น "ไข่ต้ม 3 ฟอง" = 3 x ไข่ต้ม 1 ฟอง)
- ถ้าไม่ระบุจำนวน ให้ประมาณ 1 ที่มาตรฐาน
- ให้ค่าเป็นตัวเลขจริง ไม่ใช่ช่วง
- ตอบเป็น JSON เท่านั้น ไม่มี markdown code fence

ตอบกลับ JSON format นี้เท่านั้น:
{"items":[{"food_name":"ชื่ออาหาร (ภาษาไทย)","portion":"ปริมาณโดยประมาณ","calories":0.0,"protein":0.0,"carbs":0.0,"fat":0.0,"confidence":0.0,"notes":""}]}
"""


def parse_food_text(text: str) -> Dict[str, Any]:
    """
    Use Gemini Flash text-only to estimate calories and macros from a Thai food description.
    Falls back to a simple estimate if the API is not configured.
    """
    # Clean input: remove leading keywords
    clean_text = text.strip()
    for prefix in ["กิน ", "เพิ่ม ", "กิน", "เพิ่ม"]:
        if clean_text.startswith(prefix):
            clean_text = clean_text[len(prefix):].strip()
            break

    if not clean_text:
        return _default_food_response("อาหารทั่วไป")

    if not settings.GEMINI_API_KEY or "mock" in settings.GEMINI_API_KEY:
        logger.warning("Using mock Gemini text food response (GEMINI_API_KEY is not set).")
        return _default_food_response(clean_text)

    parts = _split_items(clean_text)

    import google.generativeai as genai
    genai.configure(api_key=settings.GEMINI_API_KEY)

    listing = "\n".join(f"{index}. {part}" for index, part in enumerate(parts, 1))
    data = generate_food_json(
        genai,
        [FOOD_PARSE_PROMPT, f"ผู้ใช้กิน {len(parts)} รายการ ตอบกลับให้ครบทุกรายการตามลำดับ:\n{listing}"],
        log_label="text food parse",
    )
    items = data.get("items") if isinstance(data.get("items"), list) else [data]
    return {"items": _merge_to_one(items, clean_text) if len(parts) == 1 else items}


def _split_items(clean_text: str) -> list[str]:
    """One item per separator-delimited part; the user decides the count, not the AI."""
    parts = [part.strip() for part in clean_text.split(ITEM_SEPARATOR)]
    return [part for part in parts if part] or [clean_text]


def _merge_to_one(items: list[Any], food_name: str) -> list[Dict[str, Any]]:
    """Fold a single dish back into one row when the model splits it anyway.

    The model still reasons component by component, which keeps the totals
    good, but "ข้าวเนื้อทอดผัดพริกเกลือไข่ข้น" is one plate the user ordered
    and has to be one row to stay editable as what they typed.
    """
    items = [item for item in items if isinstance(item, dict)]
    if len(items) <= 1:
        return items or [{"food_name": food_name}]

    def total(field: str) -> float:
        return round(sum(float(item.get(field) or 0) for item in items), 1)

    confidences = [item.get("confidence") for item in items if item.get("confidence") is not None]
    return [{
        "food_name": food_name,
        "portion": items[0].get("portion") or "1 ที่",
        "calories": total("calories"),
        "protein": total("protein"),
        "carbs": total("carbs"),
        "fat": total("fat"),
        "confidence": min(float(value) for value in confidences) if confidences else None,
        "notes": " • ".join(str(item.get("food_name") or "").strip() for item in items if item.get("food_name")),
    }]


def _default_food_response(food_name: str) -> Dict[str, Any]:
    """Fallback response when Gemini API is unavailable."""
    return {"items": [{
        "food_name": food_name,
        "portion": "1 ที่ (ประมาณการ)",
        "calories": 400.0,
        "protein": 20.0,
        "carbs": 45.0,
        "fat": 12.0,
        "confidence": 0.4,
        "notes": "ค่าประมาณทั่วไป — แก้ไขได้ก่อนยืนยัน"
    }]}

