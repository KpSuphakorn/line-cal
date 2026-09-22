"""Gemini Vision AI Engine for Food Calorie and Macro Estimation."""
import logging
from typing import Dict, Any
from io import BytesIO
from PIL import Image

from app.config import settings
from app.services.ai_errors import FoodAnalysisError, generate_food_json, merge_food_items

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """คุณเป็นนักโภชนาการ AI ผู้เชี่ยวชาญด้านอาหารไทยและอาหารสากล
วิเคราะห์รูปอาหาร นับจำนวนรายการตามจาน ชาม หรือแก้วที่แยกกันจริงเท่านั้น
ไม่ใช่ตามส่วนประกอบ เช่น ข้าว เนื้อ ไข่ดาว ที่อยู่ในจานเดียวกัน คือ 1 รายการ
ไม่ใช่ 3 รายการ ส่วนจานข้าว กับแก้วน้ำส้ม กับจานสลัด ที่แยกกันจริง คือ 3 รายการ

กฎสำคัญ:
- ประเมินสารอาหารแยกทีละส่วนประกอบเพื่อความแม่นยำ แต่ระบุเลข "plate" กำกับ
  ทุกรายการ ส่วนประกอบที่อยู่ในจาน/ชาม/แก้วเดียวกันให้ใช้เลข plate เดียวกัน
  เริ่มนับจาก 1 และเพิ่มทีละ 1 สำหรับจาน/ชาม/แก้วถัดไปที่แยกกันจริง
- ให้ประมาณชื่อ ปริมาณ kcal และสารอาหารเป็นกรัม (protein, carbs, fat) ของ
  แต่ละส่วนประกอบ พร้อม confidence 0 ถึง 1 และ notes สั้นๆ
ตอบ JSON เท่านั้น ไม่มี markdown:
{"items":[{"plate":1,"food_name":"ชื่ออาหาร","portion":"ปริมาณโดยประมาณ","calories":0.0,"protein":0.0,"carbs":0.0,"fat":0.0,"confidence":0.0,"notes":""}]}
"""


def analyze_food_image(image_bytes: bytes) -> Dict[str, Any]:
    """
    Analyze food image using Google Gemini Vision (see ai_errors.FOOD_MODELS).
    Falls back to a structured mock response only if GEMINI_API_KEY is not configured.
    """
    if not settings.GEMINI_API_KEY or "mock" in settings.GEMINI_API_KEY:
        logger.warning("Using mock Gemini Vision response (GEMINI_API_KEY is not set).")
        return {"items": [{
            "food_name": "ข้าวกะเพราอกไก่ไข่ดาว",
            "portion": "1 จาน",
            "calories": 570.0,
            "protein": 37.0,
            "carbs": 56.0,
            "fat": 22.0,
            "confidence": 0.55,
            "notes": "ค่าประมาณ แก้ไขได้ก่อนยืนยัน"
        }]}

    import google.generativeai as genai
    genai.configure(api_key=settings.GEMINI_API_KEY)

    try:
        image = Image.open(BytesIO(image_bytes))
    except Exception as e:
        raise FoodAnalysisError("Gemini vision analysis failed") from e

    data = generate_food_json(genai, [SYSTEM_PROMPT, image], log_label="vision analysis")
    raw_items = data.get("items") if isinstance(data.get("items"), list) else [data]
    return {"items": _merge_by_plate(raw_items)}


def _merge_by_plate(items: list[Any]) -> list[Dict[str, Any]]:
    """Collapse components the model tagged with the same "plate" into one row each.

    The model reasons per component for accuracy, but the item count the user
    sees has to match plates/bowls/glasses, not ingredients — a photo of rice,
    chicken and a fried egg on one plate is one menu item, not three.
    """
    groups: Dict[Any, list[dict]] = {}
    order: list[Any] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        key = item.get("plate", index)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append({k: v for k, v in item.items() if k != "plate"})

    merged: list[Dict[str, Any]] = []
    for key in order:
        merged.extend(merge_food_items(groups[key]))
    return merged
