"""System starting points copied into each user's workout programs."""
from typing import Any, Dict, List


# Static seed data is intentionally separate from user-owned program rows.
PROGRAM_TEMPLATES: List[Dict[str, Any]] = [
    {
        "key": "push",
        "name": "Push",
        "exercises": [
            {"name": "Pec dec fly", "sets": 3, "repetitions": 10, "weight": 40.0, "notes": ""},
            {"name": "Flat bench press", "sets": 3, "repetitions": 10, "weight": 20.0, "notes": ""},
            {"name": "Incline bench press", "sets": 3, "repetitions": 10, "weight": 20.0, "notes": ""},
            {"name": "Lower chest fly", "sets": 3, "repetitions": 10, "weight": 15.0, "notes": ""},
            {"name": "Lateral raises", "sets": 3, "repetitions": 12, "weight": 4.0, "notes": ""},
            {"name": "Triceps push down", "sets": 3, "repetitions": 10, "weight": 7.5, "notes": ""},
        ],
    },
    {
        "key": "pull",
        "name": "Pull",
        "exercises": [
            {"name": "Lat pull down", "sets": 3, "repetitions": 10, "weight": 35.0, "notes": ""},
            {"name": "T-bar row", "sets": 3, "repetitions": 10, "weight": 17.5, "notes": ""},
            {"name": "One arm row", "sets": 3, "repetitions": 10, "weight": 12.0, "notes": ""},
            {"name": "Seated row", "sets": 3, "repetitions": 10, "weight": 40.0, "notes": ""},
            {"name": "Lat pull over", "sets": 3, "repetitions": 10, "weight": 10.0, "notes": ""},
            {"name": "Biceps curl", "sets": 3, "repetitions": 10, "weight": 30.0, "notes": ""},
        ],
    },
    {
        "key": "legs",
        "name": "Legs",
        "exercises": [
            {"name": "Hip adductors", "sets": 3, "repetitions": 10, "weight": 40.0, "notes": ""},
            {"name": "Leg curl", "sets": 3, "repetitions": 10, "weight": 60.0, "notes": ""},
            {"name": "Hack squat", "sets": 3, "repetitions": 10, "weight": None, "notes": "ตามระดับ"},
            {"name": "Leg press", "sets": 3, "repetitions": 10, "weight": 80.0, "notes": ""},
            {"name": "Leg extension", "sets": 3, "repetitions": 10, "weight": 60.0, "notes": ""},
            {"name": "Abdominal crunch", "sets": 3, "repetitions": 12, "weight": 45.0, "notes": ""},
        ],
    },
]
