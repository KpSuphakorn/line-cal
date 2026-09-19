"""Gemini Vision AI Engine for Food Calorie and Macro Estimation."""
import json
import logging
from typing import Dict, Any, Optional
from io import BytesIO
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """คุณเป็นนักโภชนาการ AI ผู้เชี่ยวชาญด้านอาหารไทยและอาหารสากล จงวิเคราะห์รูปภาพอาหารที่ส่งมาอย่างละเอียดและแม่นยำ:
1. ระบุชื่ออาหาร (ภาษาไทย)
2. ประมาณขนาดและส่วนประกอบ (เช่น ข้าวสวย 1.5 ทัพพี, เนื้อสัตว์กี่กรัม, ปรุงด้วยน้ำมันหรือไม่)
3. ประเมินพลังงานรวม (kcal)
4. ประเมินสารอาหารหลัก (Macronutrients) เป็นกรัม:
   - protein (โปรตีน)
   - carbs (คาร์โบไฮเดรต)
   - fat (ไขมัน)
5. ให้ข้อคิดเห็นสั้นๆ เกี่ยวกับเป้าหมายสร้างกล้ามเนื้อและลดพุง (notes)

ตอบกลับเป็น JSON Format เดียวเท่านั้น โดยไม่มี markdown code fence หรือข้อความอื่น:
{
  "food_name": "ชื่ออาหารหลัก",
  "portion": "ปริมาณโดยประมาณ เช่น 1 จาน (ข้าว 150g, ไก่ 120g)",
  "calories": 550.0,
  "protein": 28.0,
  "carbs": 62.0,
  "fat": 16.0,
  "notes": "คำแนะนำสั้นๆ เกี่ยวกับสารอาหาร"
}
"""


def analyze_food_image(image_bytes: bytes) -> Dict[str, Any]:
    """
    Analyze food image using Google Gemini Vision (gemini-2.0-flash / gemini-1.5-flash).
    Falls back to a structured mock response if GEMINI_API_KEY is not configured or in case of error.
    """
    if not settings.GEMINI_API_KEY or "mock" in settings.GEMINI_API_KEY:
        logger.warning("Using mock Gemini Vision response (GEMINI_API_KEY is not set).")
        return {
            "food_name": "ข้าวกะเพราอกไก่ไข่ดาว",
            "portion": "1 จาน (ข้าวสวย 150g, อกไก่ 120g, ไข่ดาว 1 ฟอง)",
            "calories": 520.0,
            "protein": 34.0,
            "carbs": 58.0,
            "fat": 14.0,
            "notes": "โปรตีนสูง เหมาะกับช่วงสร้างกล้ามเนื้อ หากลดน้ำมันทอดไข่ดาวจะลีนขึ้นอีก"
        }

    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)

        # Use latest active gemini model: gemini-3.6-flash
        model_name = "gemini-3.6-flash"
        try:
            model = genai.GenerativeModel(model_name)
        except Exception:
            model = genai.GenerativeModel("gemini-flash-latest")

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
        return {
            "food_name": str(data.get("food_name", "อาหารที่ตรวจพบ")),
            "portion": str(data.get("portion", "1 ที่")),
            "calories": float(data.get("calories", 400.0)),
            "protein": float(data.get("protein", 20.0)),
            "carbs": float(data.get("carbs", 45.0)),
            "fat": float(data.get("fat", 10.0)),
            "notes": str(data.get("notes", "บันทึกเรียบร้อย"))
        }

    except Exception as e:
        logger.error(f"Error calling Gemini Vision: {e}")
        return {
            "food_name": "อาหาร (ประมาณการทั่วไป)",
            "portion": "1 จานมาตรฐาน",
            "calories": 500.0,
            "protein": 25.0,
            "carbs": 60.0,
            "fat": 15.0,
            "notes": f"เกิดข้อผิดพลาดในการวิเคราะห์ AI: {str(e)[:50]}"
        }
