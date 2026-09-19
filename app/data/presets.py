"""Presets for Suphakorn's specific workout routine & daily nutrition."""
from typing import Dict, List, Any

# Workout Split Presets (Day 1 - Day 4)
WORKOUT_SPLITS: Dict[str, Dict[str, Any]] = {
    "day_1": {
        "id": "day_1",
        "name": "Day 1: Push (อก / ไหล่ / หลังแขน)",
        "estimated_burn_kcal": 300,
        "exercises": [
            {"name": "Pec dec fly", "weight": "40 kg", "target": "อกรวม"},
            {"name": "Flat bench press", "weight": "20 kg", "target": "อกกลาง"},
            {"name": "Incline bench press", "weight": "20 kg", "target": "อกบน"},
            {"name": "Lower chest fly", "weight": "15 kg", "target": "อกล่าง"},
            {"name": "Lateral raises", "weight": "4 kg", "target": "ไหล่ข้าง"},
            {"name": "Triceps push down", "weight": "7.5 kg", "target": "หลังแขน"}
        ]
    },
    "day_2": {
        "id": "day_2",
        "name": "Day 2: Pull (หลัง / ไหล่หลัง / หน้าแขน)",
        "estimated_burn_kcal": 300,
        "exercises": [
            {"name": "Lat pull down", "weight": "35 kg", "target": "ปีกหลัง"},
            {"name": "T-bar row (หรือ Barbell bent over row)", "weight": "17.5 kg", "target": "หลังกลาง"},
            {"name": "One arm row", "weight": "12 kg", "target": "หลังปีกเดี่ยว"},
            {"name": "Seated row", "weight": "40 kg", "target": "หลังกลาง"},
            {"name": "Lat pull over", "weight": "10 kg", "target": "หลังและอก"},
            {"name": "Biceps curl", "weight": "30 kg", "target": "หน้าแขน"}
        ]
    },
    "day_3": {
        "id": "day_3",
        "name": "Day 3: Lower & Core (ขา 4 ท่า + ท้อง 1-2 ท่า)",
        "estimated_burn_kcal": 350,
        "exercises": [
            {"name": "Hip adductors", "weight": "40 kg", "target": "ขาหนีบด้านใน"},
            {"name": "Legs curl", "weight": "60 kg", "target": "ต้นขาด้านหลัง"},
            {"name": "Hack squat", "weight": "ตามระดับ", "target": "ต้นขาด้านหน้า"},
            {"name": "Legs press", "weight": "80 kg", "target": "ต้นขาและสะโพก"},
            {"name": "Legs extension", "weight": "60 kg", "target": "ต้นขาด้านหน้า"},
            {"name": "Abdominal crunch", "weight": "45 kg", "target": "กล้ามเนื้อหน้าท้อง"}
        ]
    },
    "day_4": {
        "id": "day_4",
        "name": "Day 4: Upper (ท่อนบนรวม)",
        "estimated_burn_kcal": 320,
        "exercises": [
            {"name": "Shoulders press", "weight": "10 kg", "target": "ไหล่รวม"},
            {"name": "Lateral raises", "weight": "4-6 kg", "target": "ไหล่ข้าง"},
            {"name": "Rear delt fly -> Rope face pull", "weight": "ตามระดับ", "target": "ไหล่หลัง"},
            {"name": "Pec dec fly", "weight": "40 kg", "target": "อกรวม"},
            {"name": "Cable pull over", "weight": "15 kg", "target": "หลัง"},
            {"name": "Triceps & Biceps superset", "weight": "ตามระดับ", "target": "แขนรวม"}
        ]
    }
}

# Cardio: Incline Walking (เดินชัน) Presets
CARDIO_PRESETS = [
    {
        "id": "incline_40",
        "title": "เดินชัน 40 นาที",
        "duration_min": 40,
        "incline_pct": "10-12%",
        "speed_kmh": "4.5-5.0",
        "burn_kcal": 280
    },
    {
        "id": "incline_50",
        "title": "เดินชัน 50 นาที",
        "duration_min": 50,
        "incline_pct": "10-12%",
        "speed_kmh": "4.5-5.0",
        "burn_kcal": 350
    },
    {
        "id": "incline_60",
        "title": "เดินชัน 60 นาที",
        "duration_min": 60,
        "incline_pct": "10-12%",
        "speed_kmh": "4.5-5.0",
        "burn_kcal": 420
    }
]

# Quick Snack Presets (Tailored to Suphakorn's habits)
QUICK_SNACKS = [
    {
        "id": "banana",
        "title": "กล้วยหอม 1 ลูก",
        "subtitle": "Pre-workout energy",
        "calories": 105,
        "protein": 1.3,
        "carbs": 27.0,
        "fat": 0.3,
        "icon": "🍌"
    },
    {
        "id": "milk",
        "title": "นมจืด 1 กล่อง (200ml)",
        "subtitle": "Pre-workout protein",
        "calories": 130,
        "protein": 8.0,
        "carbs": 10.0,
        "fat": 6.5,
        "icon": "🥛"
    },
    {
        "id": "matcha_latte_cow",
        "title": "มัจฉะลาเต้ หวาน 0% (นมวัว)",
        "subtitle": "เพิ่มสมาธิทำงาน บ่าย",
        "calories": 130,
        "protein": 8.0,
        "carbs": 12.0,
        "fat": 5.0,
        "icon": "🍵"
    },
    {
        "id": "matcha_coconut",
        "title": "มัจฉะน้ำมะพร้าว",
        "subtitle": "สดชื่น ตื่นตัว หวานธรรมชาติ",
        "calories": 70,
        "protein": 1.0,
        "carbs": 16.0,
        "fat": 0.2,
        "icon": "🥥"
    },
    {
        "id": "mixed_nuts",
        "title": "ถั่วรวม 1 กำมือ (30g)",
        "subtitle": "อัลมอนด์/วอลนัท ไขมันดี",
        "calories": 175,
        "protein": 6.0,
        "carbs": 6.0,
        "fat": 15.0,
        "icon": "🥜"
    }
]
