"""Gemini AI Text-based Food Parsing Engine for natural language food logging."""
import json
import logging
from typing import Dict, Any

from app.config import settings

logger = logging.getLogger(__name__)

FOOD_PARSE_PROMPT = """คุณเป็นนักโภชนาการ AI ผู้เชี่ยวชาญด้านอาหารไทยและอาหารสากล
ผู้ใช้จะพิมพ์รายการอาหารที่กินเข้ามา จงแยกเป็นรายการอิสระหลายรายการเมื่อมีหลายเมนู
และประเมินปริมาณสารอาหารให้แม่นยำที่สุด

กฎสำคัญ:
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

    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)

        # Use standard production gemini model: gemini-flash-latest (1,500 RPD free tier)
        model_name = "gemini-flash-latest"
        try:
            model = genai.GenerativeModel(model_name)
        except Exception:
            model = genai.GenerativeModel("gemini-1.5-flash")




        response = model.generate_content(
            [
                FOOD_PARSE_PROMPT,
                f"ผู้ใช้พิมพ์: {clean_text}"
            ],
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.2
            }
        )

        content_text = response.text.strip()
        # Remove any lingering markdown
        if content_text.startswith("```json"):
            content_text = content_text[7:]
        if content_text.startswith("```"):
            content_text = content_text[3:]
        if content_text.endswith("```"):
            content_text = content_text[:-3]

        data = json.loads(content_text.strip())
        return data if isinstance(data.get("items"), list) else {"items": [data]}

    except Exception as e:
        logger.error(f"Error calling Gemini text food parse: {e}")
        return _default_food_response(clean_text)


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

