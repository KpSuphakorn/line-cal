"""Gemini Vision AI Engine for Food Calorie and Macro Estimation."""
import json
import logging
from typing import Dict, Any
from io import BytesIO
from PIL import Image

from app.config import settings
from app.services.ai_errors import FoodAnalysisError

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """คุณเป็นนักโภชนาการ AI ผู้เชี่ยวชาญด้านอาหารไทยและอาหารสากล
วิเคราะห์อาหารทุกอย่างที่เห็นในรูปเป็นรายการอิสระ แยกข้าว เนื้อ ไข่ เครื่องดื่ม
หรือของเคียงเมื่อแยกได้ ให้ประมาณชื่อ ปริมาณ kcal และสารอาหารเป็นกรัม
(protein, carbs, fat) พร้อม confidence 0 ถึง 1 และ notes สั้นๆ
ตอบ JSON เท่านั้น ไม่มี markdown:
{"items":[{"food_name":"ชื่ออาหาร","portion":"ปริมาณโดยประมาณ","calories":0.0,"protein":0.0,"carbs":0.0,"fat":0.0,"confidence":0.0,"notes":""}]}
"""


def analyze_food_image(image_bytes: bytes) -> Dict[str, Any]:
    """
    Analyze food image using Google Gemini Vision (gemini-2.0-flash / gemini-1.5-flash).
    Falls back to a structured mock response if GEMINI_API_KEY is not configured or in case of error.
    """
    if not settings.GEMINI_API_KEY or "mock" in settings.GEMINI_API_KEY:
        logger.warning("Using mock Gemini Vision response (GEMINI_API_KEY is not set).")
        return {"items": [{
            "food_name": "ข้าวกะเพราอกไก่",
            "portion": "1 จาน",
            "calories": 450.0,
            "protein": 30.0,
            "carbs": 55.0,
            "fat": 12.0,
            "confidence": 0.65,
            "notes": "ค่าประมาณ แก้ไขได้ก่อนยืนยัน"
        }, {
            "food_name": "ไข่ดาว",
            "portion": "1 ฟอง",
            "calories": 120.0,
            "protein": 7.0,
            "carbs": 1.0,
            "fat": 10.0,
            "confidence": 0.55,
            "notes": "ค่าประมาณ แก้ไขได้ก่อนยืนยัน"
        }]}

    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)

        # Use standard production gemini model: gemini-flash-latest (1,500 RPD free tier)
        model_name = "gemini-flash-latest"
        try:
            model = genai.GenerativeModel(model_name)
        except Exception:
            model = genai.GenerativeModel("gemini-1.5-flash")


        image = Image.open(BytesIO(image_bytes))

        response = model.generate_content(
            [
                SYSTEM_PROMPT,
                image
            ],
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.2
            }
        )

        content_text = response.text.strip()
        # Remove any lingering markdown if present
        if content_text.startswith("```json"):
            content_text = content_text[7:]
        if content_text.startswith("```"):
            content_text = content_text[3:]
        if content_text.endswith("```"):
            content_text = content_text[:-3]

        data = json.loads(content_text.strip())
        return data if isinstance(data.get("items"), list) else {"items": [data]}

    except Exception as e:
        logger.error(f"Error calling Gemini Vision: {e}")
        raise FoodAnalysisError("Gemini vision analysis failed") from e
