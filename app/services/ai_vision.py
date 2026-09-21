"""Gemini Vision AI Engine for Food Calorie and Macro Estimation."""
import logging
from typing import Dict, Any
from io import BytesIO
from PIL import Image

from app.config import settings
from app.services.ai_errors import FoodAnalysisError, generate_food_json

logger = logging.getLogger(__name__)

# See ai_errors.generate_food_json for why these are pinned explicitly.
FOOD_VISION_MODELS = ("gemini-2.5-flash", "gemini-2.5-flash-lite")

SYSTEM_PROMPT = """คุณเป็นนักโภชนาการ AI ผู้เชี่ยวชาญด้านอาหารไทยและอาหารสากล
วิเคราะห์อาหารทุกอย่างที่เห็นในรูปเป็นรายการอิสระ แยกข้าว เนื้อ ไข่ เครื่องดื่ม
หรือของเคียงเมื่อแยกได้ ให้ประมาณชื่อ ปริมาณ kcal และสารอาหารเป็นกรัม
(protein, carbs, fat) พร้อม confidence 0 ถึง 1 และ notes สั้นๆ
ตอบ JSON เท่านั้น ไม่มี markdown:
{"items":[{"food_name":"ชื่ออาหาร","portion":"ปริมาณโดยประมาณ","calories":0.0,"protein":0.0,"carbs":0.0,"fat":0.0,"confidence":0.0,"notes":""}]}
"""


def analyze_food_image(image_bytes: bytes) -> Dict[str, Any]:
    """
    Analyze food image using Google Gemini Vision (see FOOD_VISION_MODELS).
    Falls back to a structured mock response only if GEMINI_API_KEY is not configured.
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

    import google.generativeai as genai
    genai.configure(api_key=settings.GEMINI_API_KEY)

    try:
        image = Image.open(BytesIO(image_bytes))
    except Exception as e:
        raise FoodAnalysisError("Gemini vision analysis failed") from e

    data = generate_food_json(genai, FOOD_VISION_MODELS, [SYSTEM_PROMPT, image], log_label="vision analysis")
    return data if isinstance(data.get("items"), list) else {"items": [data]}
