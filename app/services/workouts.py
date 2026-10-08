"""User-owned workout programs and historical session snapshots."""
from datetime import datetime, timezone
from math import isfinite
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    CardioDetails,
    CardioPreset,
    ProgramExercise,
    WorkoutProgram,
    WorkoutSession,
    SessionExercise,
    User,
)
from app.services.fitness import (
    estimate_strength_calories,
    estimate_strength_duration_min,
    is_user_profile_customized,
    seed_user_programs_if_needed,
)


CARDIO_METS = {
    "เดินชัน": 7.5,
    "เดิน": 3.5,
    "วิ่ง": 8.3,
    "จักรยาน": 7.5,
    "ว่ายน้ำ": 6.0,
    "อื่นๆ": 5.0,
}
CARDIO_ACTIVITIES = ("เดิน", "เดินชัน", "วิ่ง", "จักรยาน", "ว่ายน้ำ", "อื่นๆ")
CARDIO_VARIANTS = {
    "จักรยาน": {"outdoor_general", "outdoor_easy", "outdoor_moderate", "outdoor_vigorous",
                "stationary_general", "stationary_light", "stationary_moderate", "stationary_vigorous"},
    "ว่ายน้ำ": {"general", "freestyle_recreational", "freestyle_vigorous", "breaststroke_recreational",
                "breaststroke_training", "backstroke_recreational", "backstroke_training", "butterfly"},
    "อื่นๆ": {"stretching", "yoga", "elliptical_moderate", "elliptical_vigorous", "jump_rope", "aerobics"},
}
VARIANT_METS = {
    "outdoor_general": 7.0, "outdoor_easy": 4.3, "outdoor_moderate": 7.0, "outdoor_vigorous": 9.0,
    "stationary_general": 6.8, "stationary_light": 4.0, "stationary_moderate": 6.0, "stationary_vigorous": 10.8,
    "general": 6.0, "freestyle_recreational": 5.8, "freestyle_vigorous": 9.8,
    "breaststroke_recreational": 5.3, "breaststroke_training": 10.3,
    "backstroke_recreational": 4.8, "backstroke_training": 9.5, "butterfly": 13.8,
    "stretching": 2.3, "yoga": 2.3, "elliptical_moderate": 5.0, "elliptical_vigorous": 9.0,
    "jump_rope": 11.0, "aerobics": 7.3,
}
VARIANT_LABELS = {
    "outdoor_general": "กลางแจ้ง • ทั่วไป", "outdoor_easy": "กลางแจ้ง • เบา", "outdoor_moderate": "กลางแจ้ง • ปานกลาง", "outdoor_vigorous": "กลางแจ้ง • หนัก",
    "stationary_general": "อยู่กับที่ • ทั่วไป", "stationary_light": "อยู่กับที่ • เบา (~50W)", "stationary_moderate": "อยู่กับที่ • ปานกลาง (~90–100W)", "stationary_vigorous": "อยู่กับที่ • หนัก (~200–229W)",
    "general": "ทั่วไป", "freestyle_recreational": "ฟรีสไตล์ • สบาย", "freestyle_vigorous": "ฟรีสไตล์ • หนัก", "breaststroke_recreational": "กบ • สบาย", "breaststroke_training": "กบ • ฝึกซ้อม", "backstroke_recreational": "กรรเชียง • สบาย", "backstroke_training": "กรรเชียง • ฝึกซ้อม", "butterfly": "ผีเสื้อ",
    "stretching": "ยืดเหยียด", "yoga": "โยคะ", "elliptical_moderate": "Elliptical • ปานกลาง", "elliptical_vigorous": "Elliptical • หนัก", "jump_rope": "กระโดดเชือก", "aerobics": "แอโรบิก",
}


def _number(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    return float(value)


def _optional_number(value: Any, name: str, maximum: float) -> float | None:
    number = _number(value)
    if number is None:
        return None
    if not isfinite(number) or number <= 0 or number > maximum:
        label = {"duration_min": "เวลา", "speed_kmh": "ความเร็ว", "distance_km": "ระยะทาง"}.get(name, name)
        raise ValueError(f"{label}ต้องมากกว่า 0 และไม่เกิน {maximum}")
    return number


def _cardio_inputs(
    activity: str,
    data: dict[str, Any],
    *,
    variant: str | None = None,
    height_cm: float | None = None,
    gender: str | None = None,
) -> dict[str, Any]:
    duration = _optional_number(data.get("duration_min"), "duration_min", 1440)
    if duration is not None and duration < 0.1:
        raise ValueError("เวลาต้องอย่างน้อย 0.1 นาที")
    incline = _number(data.get("incline_pct"))
    if incline is not None and (not isfinite(incline) or not 0 <= incline <= 100):
        raise ValueError("ความชันต้องอยู่ระหว่าง 0–100%")
    speed = _optional_number(data.get("speed_kmh"), "speed_kmh", 100)
    distance = _optional_number(data.get("distance_km"), "distance_km", 1000)
    raw_steps = data.get("steps")
    if raw_steps in (None, ""):
        steps = None
    else:
        try:
            step_value = float(raw_steps)
        except (TypeError, ValueError) as exc:
            raise ValueError("จำนวนก้าวต้องเป็นจำนวนเต็ม") from exc
        if not isfinite(step_value) or not step_value.is_integer():
            raise ValueError("จำนวนก้าวต้องเป็นจำนวนเต็ม")
        steps = int(step_value)
    if steps is not None and not 1 <= steps <= 200000:
        raise ValueError("จำนวนก้าวต้องอยู่ระหว่าง 1–200,000 ก้าว")

    is_walk = activity in {"เดิน", "เดินชัน"}
    is_run = activity == "วิ่ง"
    is_bike = activity == "จักรยาน"
    bike_stationary = bool(variant and variant.startswith("stationary_"))
    is_swim = activity == "ว่ายน้ำ"
    if activity != "เดินชัน":
        incline = None
    if not (is_walk or is_run or is_bike):
        speed = None
    if not (is_walk or is_run or is_bike or is_swim):
        distance = None
    if is_swim:
        speed = None
    if is_run or not is_walk:
        steps = None

    # A rough height-based stride estimate, used only when walking steps were
    # provided without explicit kilometres. Explicit distance always wins.
    step_distance = None
    if steps is not None and distance is None:
        if height_cm is None or not isfinite(float(height_cm)) or not 80 <= float(height_cm) <= 250:
            raise ValueError("ต้องมีส่วนสูงในโปรไฟล์เพื่อประมาณระยะทางจากจำนวนก้าว")
        stride_ratio = 0.415 if gender == "male" else 0.413 if gender == "female" else 0.414
        step_distance = steps * float(height_cm) * stride_ratio / 100000

    effective_distance = distance if distance is not None else step_distance

    derived_speed = None
    if is_walk or is_run:
        if duration is None and effective_distance is None:
            raise ValueError("กรอกเวลา ระยะทาง หรือจำนวนก้าวสำหรับการเดินอย่างน้อยหนึ่งรายการ")
    elif is_bike:
        if bike_stationary:
            if duration is None:
                raise ValueError("จักรยานอยู่กับที่ต้องระบุเวลาออกกำลังกายจริง")
        elif variant is None and duration is None:
            raise ValueError("จักรยานต้องระบุเวลาออกกำลังกายจริง")
        elif duration is None and not (distance is not None and speed is not None):
            raise ValueError("จักรยานกลางแจ้งต้องระบุเวลา หรือระยะทางพร้อมความเร็ว")
    elif duration is None:
        raise ValueError("กรุณาระบุเวลาออกกำลังกายจริง")

    if duration is not None and effective_distance is not None and (is_walk or is_run or (is_bike and not bike_stationary)):
        derived_speed = effective_distance * 60 / duration
    elif speed is not None and (is_walk or is_run or (is_bike and not bike_stationary)):
        derived_speed = speed
    elif effective_distance is not None and (is_walk or is_run):
        derived_speed = 8.0 if is_run else 4.8
    elif activity == "เดินชัน" and incline is not None:
        derived_speed = 4.8

    # Keep calculated values within plausible activity ranges. This also
    # prevents a mistyped distance/time pair from inflating the kcal estimate.
    if derived_speed is not None:
        minimum, maximum = (4.18, 30.0) if is_run else (0.2, 15.0)
        if is_bike:
            minimum, maximum = 1.0, 80.0
        if not minimum <= derived_speed <= maximum:
            raise ValueError(f"ความเร็วที่คำนวณได้ต้องอยู่ระหว่าง {minimum}–{maximum} กม./ชม.")
    if activity == "เดินชัน" and incline:
        if incline > 15:
            raise ValueError("ความชันสำหรับการประเมินเดินชันต้องไม่เกิน 15%")
        if derived_speed is not None and not 3.2 <= derived_speed <= 5.6:
            raise ValueError("เดินชันประเมินได้เมื่อความเร็วอยู่ระหว่าง 3.2–5.6 กม./ชม.")
    estimated_duration = duration
    if estimated_duration is None and effective_distance is not None and derived_speed is not None:
        estimated_duration = effective_distance * 60 / derived_speed
    if estimated_duration is None or not isfinite(estimated_duration) or not 0 < estimated_duration <= 1440:
        raise ValueError("เวลาที่คำนวณได้ต้องมากกว่า 0 และไม่เกิน 1,440 นาที")

    if estimated_duration is not None and estimated_duration < 0.1:
        raise ValueError("เวลาที่คำนวณได้ต้องอย่างน้อย 0.1 นาที")
    return {
        "duration_min": duration,
        "estimated_duration_min": estimated_duration,
        "incline_pct": incline,
        "speed_kmh": speed,
        "distance_km": distance,
        "steps": steps,
        "effective_distance_km": effective_distance,
        "calculation_speed_kmh": derived_speed,
        "bike_stationary": bike_stationary,
    }


_WALK_SPEED_METS = (
    (1.6, 2.1), (1.9, 2.3), (3.2, 2.8), (4.0, 3.0), (4.8, 3.5),
    (5.6, 3.8), (6.4, 4.8), (7.2, 5.8), (8.0, 6.8), (float("inf"), 8.3),
)
_RUN_SPEED_METS = (
    (6.44, 6.5), (6.92, 7.8), (8.05, 8.5), (8.85, 9.0), (9.66, 9.3),
    (10.78, 10.5), (11.27, 11.0), (12.07, 11.8), (12.87, 12.0),
    (13.84, 12.5), (14.48, 13.0), (14.97, 14.8), (17.70, 16.8),
    (19.31, 18.5), (20.92, 19.8), (22.53, 23.0),
)
_BIKE_SPEED_METS = (
    (16.09, 4.0), (19.31, 6.8), (22.53, 8.0), (25.75, 10.0),
    (32.19, 12.0), (float("inf"), 16.8),
)


def _speed_met(speed_kmh: float, bands: tuple[tuple[float, float], ...]) -> float:
    return next(met for threshold, met in bands if speed_kmh < threshold)


def _running_speed_met(speed_kmh: float) -> float:
    # Compendium low-speed jogging begins at 2.6 mph (about 4.18 km/h).
    # Its 3.3 MET band also covers the small published gap before 4 mph.
    met = 3.3
    for lower_bound, band_met in _RUN_SPEED_METS:
        if speed_kmh < lower_bound:
            break
        met = band_met
    return met


def _cardio_estimate(activity: str, inputs: dict[str, Any], weight_kg: float, variant: str | None = None) -> tuple[float, float, float]:
    met = CARDIO_METS.get(activity, CARDIO_METS["อื่นๆ"])
    speed = inputs["calculation_speed_kmh"]
    incline = inputs["incline_pct"]
    if speed is not None and activity in {"เดิน", "เดินชัน"}:
        if activity == "เดินชัน" and incline:
            speed_m_min = speed * 1000 / 60
            met = (3.5 + 0.1 * speed_m_min + 1.8 * speed_m_min * incline / 100) / 3.5
        else:
            met = _speed_met(speed, _WALK_SPEED_METS)
    elif speed is not None and activity == "วิ่ง":
        met = _running_speed_met(speed)
    elif activity == "จักรยาน" and variant and variant.startswith("outdoor_") and speed is not None:
        met = _speed_met(speed, _BIKE_SPEED_METS)
    elif variant in VARIANT_METS:
        met = VARIANT_METS[variant]
    duration = inputs["estimated_duration_min"]
    calories = round(met * 3.5 * float(weight_kg) / 200.0 * duration, 1)
    return duration, met, calories


def _exercise_payload(exercise: Any, index: int) -> dict[str, Any]:
    return {
        "id": exercise.id,
        "name": exercise.name,
        "sets": exercise.sets,
        "repetitions": exercise.repetitions,
        "weight": exercise.weight,
        "notes": exercise.notes or "",
        "order_num": exercise.order_num if exercise.order_num is not None else index,
    }


def serialize_program(program: WorkoutProgram) -> dict[str, Any]:
    return {
        "id": program.id,
        "name": program.name,
        "source_key": program.source_key,
        "template_id": program.template_id,
        "exercises": [_exercise_payload(exercise, i) for i, exercise in enumerate(program.exercises, 1)],
    }


def serialize_cardio_preset(preset: CardioPreset) -> dict[str, Any]:
    return {
        "id": preset.id,
        "name": preset.name,
        "activity": preset.activity,
        "custom_name": preset.custom_name,
        "variant": preset.variant,
        "variant_label": VARIANT_LABELS.get(preset.variant),
        "duration_min": round(preset.duration_min, 1) if preset.duration_min is not None else None,
        "incline_pct": preset.incline_pct,
        "speed_kmh": preset.speed_kmh,
        "distance_km": preset.distance_km,
        "steps": preset.steps,
    }


def list_programs(db: Session, user_id: str) -> list[dict[str, Any]]:
    return [serialize_program(program) for program in seed_user_programs_if_needed(db, user_id)]


def _owned_cardio_preset(db: Session, user_id: str, preset_id: int) -> CardioPreset | None:
    return db.query(CardioPreset).filter(CardioPreset.id == preset_id, CardioPreset.user_id == user_id).first()


def list_cardio_presets(db: Session, user_id: str) -> list[dict[str, Any]]:
    presets = db.query(CardioPreset).filter(CardioPreset.user_id == user_id).order_by(CardioPreset.name.asc()).all()
    return [serialize_cardio_preset(preset) for preset in presets]


def save_cardio_preset(
    db: Session,
    user_id: str,
    data: dict[str, Any],
    preset_id: int | None = None,
) -> dict[str, Any]:
    preset = _owned_cardio_preset(db, user_id, preset_id) if preset_id is not None else None
    if preset_id is not None and preset is None:
        raise LookupError("Cardio preset not found")
    activity = str(data.get("activity") or "อื่นๆ").strip()[:80]
    custom_name = str(data.get("custom_name") or "").strip()[:80] or None
    name = str(data.get("name") or (custom_name if activity == "อื่นๆ" else activity) or "Cardio").strip()[:100]
    if not name:
        raise ValueError("name is required")
    conflict = db.query(CardioPreset).filter(CardioPreset.user_id == user_id, CardioPreset.name == name)
    if preset is not None:
        conflict = conflict.filter(CardioPreset.id != preset.id)
    if conflict.first() is not None:
        raise ValueError("A cardio preset with this name already exists")
    if activity not in CARDIO_ACTIVITIES:
        raise ValueError("activity must be one of the supported cardio activities")
    if activity == "อื่นๆ" and not custom_name:
        raise ValueError("custom_name is required for other cardio")
    if activity != "อื่นๆ" and custom_name:
        raise ValueError("custom_name is only allowed for other cardio")
    variant = data.get("variant")
    if variant is not None and variant not in CARDIO_VARIANTS.get(activity, set()):
        raise ValueError("ตัวเลือกระดับ/รูปแบบไม่ตรงกับประเภทกิจกรรม")
    user = db.query(User).filter(User.id == user_id).first()
    metrics = _cardio_inputs(activity, data, variant=variant, height_cm=user.height_cm if user else None, gender=user.gender if user else None)
    values = {
        "name": name,
        "activity": activity,
        "custom_name": custom_name,
        "variant": variant,
        "duration_min": metrics["duration_min"],
        "incline_pct": metrics["incline_pct"],
        "speed_kmh": metrics["speed_kmh"],
        "distance_km": metrics["distance_km"],
        "steps": metrics["steps"],
    }
    if preset is None:
        preset = CardioPreset(user_id=user_id, **values)
        db.add(preset)
    else:
        for key, value in values.items():
            setattr(preset, key, value)
    db.commit()
    db.refresh(preset)
    return serialize_cardio_preset(preset)


def delete_cardio_preset(db: Session, user_id: str, preset_id: int) -> bool:
    preset = _owned_cardio_preset(db, user_id, preset_id)
    if not preset:
        return False
    db.delete(preset)
    db.commit()
    return True


def _owned_program(db: Session, user_id: str, program_id: int) -> WorkoutProgram | None:
    return (
        db.query(WorkoutProgram)
        .options(selectinload(WorkoutProgram.exercises))
        .filter(WorkoutProgram.id == program_id, WorkoutProgram.user_id == user_id)
        .first()
    )


def save_program(db: Session, user_id: str, data: dict[str, Any], program_id: int | None = None) -> dict[str, Any]:
    program = _owned_program(db, user_id, program_id) if program_id is not None else None
    if program_id is not None and not program:
        raise LookupError("Workout program not found")
    if program is None:
        program = WorkoutProgram(user_id=user_id, name=str(data.get("name") or "โปรแกรมใหม่").strip()[:100])
        db.add(program)
        db.flush()
    if "name" in data:
        name = str(data["name"]).strip()
        if name:
            program.name = name[:100]
    if "exercises" in data:
        db.query(ProgramExercise).filter(ProgramExercise.program_id == program.id).delete(synchronize_session=False)
        for index, item in enumerate(data.get("exercises") or [], 1):
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            db.add(ProgramExercise(
                program_id=program.id,
                name=name[:100],
                sets=max(0, int(item.get("sets", 3))),
                repetitions=max(0, int(item.get("repetitions", 10))),
                weight=_number(item.get("weight")),
                notes=str(item.get("notes") or "").strip()[:2000] or None,
                order_num=index,
            ))
    db.commit()
    db.refresh(program)
    return serialize_program(_owned_program(db, user_id, program.id))


def delete_program(db: Session, user_id: str, program_id: int) -> bool:
    program = _owned_program(db, user_id, program_id)
    if not program:
        return False
    # Detach historical snapshots explicitly so this remains correct on local
    # SQLite databases where foreign-key enforcement may be disabled.
    db.query(WorkoutSession).filter(
        WorkoutSession.user_id == user_id,
        WorkoutSession.program_id == program_id,
    ).update({WorkoutSession.program_id: None}, synchronize_session=False)
    db.delete(program)
    db.commit()
    return True


def serialize_session(session: WorkoutSession) -> dict[str, Any]:
    result = {
        "id": session.id,
        "program_id": session.program_id,
        "type": session.session_type,
        "name": session.name,
        "estimated_duration_min": round(session.estimated_duration_min or 0, 1),
        "estimated_calories": round(session.estimated_calories or 0, 1),
        "calories_estimated": bool(session.calories_estimated),
        "occurred_at": session.occurred_at.isoformat() if session.occurred_at else None,
        "notes": session.notes or "",
        "exercises": [_exercise_payload(exercise, i) for i, exercise in enumerate(session.exercises, 1)],
    }
    if session.cardio:
        result["cardio"] = {
            "activity": session.cardio.activity,
            "activity_type": session.cardio.activity_type,
            "variant": session.cardio.variant,
            "variant_label": VARIANT_LABELS.get(session.cardio.variant),
            "duration_min": round(session.cardio.duration_min, 1) if session.cardio.duration_min is not None else None,
            "incline_pct": session.cardio.incline_pct,
            "speed_kmh": session.cardio.speed_kmh,
            "distance_km": session.cardio.distance_km,
            "steps": session.cardio.steps,
            "met": session.cardio.met,
        }
    return result


def _owned_session(db: Session, user_id: str, session_id: int) -> WorkoutSession | None:
    return (
        db.query(WorkoutSession)
        .options(selectinload(WorkoutSession.exercises), selectinload(WorkoutSession.cardio))
        .filter(WorkoutSession.id == session_id, WorkoutSession.user_id == user_id)
        .first()
    )


def _existing_session_by_source_event(
    db: Session, user_id: str, source_event_id: str | None
) -> WorkoutSession | None:
    if not source_event_id:
        return None
    return db.query(WorkoutSession).filter(
        WorkoutSession.user_id == user_id,
        WorkoutSession.source_event_id == source_event_id,
    ).first()


def create_strength_session(
    db: Session,
    user_id: str,
    program_id: int,
    source_event_id: str | None = None,
    occurred_at: datetime | None = None,
) -> WorkoutSession:
    existing = _existing_session_by_source_event(db, user_id, source_event_id)
    if existing:
        return existing
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not is_user_profile_customized(user):
        raise PermissionError("Complete your profile before logging exercise")
    program = _owned_program(db, user_id, program_id)
    if not program:
        raise LookupError("Workout program not found")
    exercises = list(program.exercises)
    duration = estimate_strength_duration_min(exercises)
    calories = estimate_strength_calories(user.weight_kg, duration)
    session = WorkoutSession(
        user_id=user_id,
        program_id=program.id,
        source_event_id=source_event_id,
        session_type="strength",
        name=program.name,
        estimated_duration_min=duration,
        estimated_calories=calories,
        calories_estimated=True,
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )
    db.add(session)
    try:
        db.flush()
        for index, exercise in enumerate(exercises, 1):
            db.add(SessionExercise(
                session_id=session.id,
                name=exercise.name,
                sets=exercise.sets,
                repetitions=exercise.repetitions,
                weight=exercise.weight,
                notes=exercise.notes,
                order_num=index,
            ))
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _existing_session_by_source_event(db, user_id, source_event_id)
        if existing:
            return existing
        raise
    return _owned_session(db, user_id, session.id)


def create_cardio_session(
    db: Session,
    user_id: str,
    preset_id: int,
    source_event_id: str | None = None,
    occurred_at: datetime | None = None,
) -> WorkoutSession:
    if preset_id is None:
        raise ValueError("preset_id is required")
    existing = _existing_session_by_source_event(db, user_id, source_event_id)
    if existing:
        return existing
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not is_user_profile_customized(user):
        raise PermissionError("Complete your profile before logging exercise")
    preset = _owned_cardio_preset(db, user_id, preset_id)
    if preset is None:
        raise LookupError("Cardio preset not found")
    activity_type = str(preset.activity or "อื่นๆ").strip()[:80]
    activity = str(preset.custom_name).strip()[:80] if activity_type == "อื่นๆ" and preset.custom_name else activity_type
    inputs = _cardio_inputs(activity_type, {
        "duration_min": preset.duration_min,
        "incline_pct": preset.incline_pct,
        "speed_kmh": preset.speed_kmh,
        "distance_km": preset.distance_km,
        "steps": preset.steps,
    }, variant=preset.variant, height_cm=user.height_cm, gender=user.gender)
    duration_min, met, calories = _cardio_estimate(activity_type, inputs, user.weight_kg, preset.variant)
    session = WorkoutSession(
        user_id=user_id,
        source_event_id=source_event_id,
        session_type="cardio",
        name=activity,
        estimated_duration_min=duration_min,
        estimated_calories=calories,
        calories_estimated=True,
        occurred_at=occurred_at or datetime.now(timezone.utc),
        cardio=CardioDetails(
            activity=activity,
            activity_type=activity_type,
            variant=preset.variant,
            duration_min=inputs["duration_min"],
            incline_pct=inputs["incline_pct"],
            speed_kmh=inputs["speed_kmh"],
            distance_km=inputs["distance_km"],
            steps=inputs["steps"],
            met=met,
        ),
    )
    db.add(session)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _existing_session_by_source_event(db, user_id, source_event_id)
        if existing:
            return existing
        raise
    return _owned_session(db, user_id, session.id)


def list_sessions(db: Session, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    sessions = (
        db.query(WorkoutSession)
        .options(selectinload(WorkoutSession.exercises), selectinload(WorkoutSession.cardio))
        .filter(WorkoutSession.user_id == user_id)
        .order_by(WorkoutSession.occurred_at.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [serialize_session(session) for session in sessions]


def get_session(db: Session, user_id: str, session_id: int) -> WorkoutSession | None:
    return _owned_session(db, user_id, session_id)


def update_session(db: Session, user_id: str, session_id: int, data: dict[str, Any]) -> WorkoutSession | None:
    session = _owned_session(db, user_id, session_id)
    if not session:
        return None
    cardio_calculation = None
    reset_calories = "estimated_calories" in data and data["estimated_calories"] is None
    if session.session_type == "cardio" and session.cardio and (isinstance(data.get("cardio"), dict) or reset_calories):
        cardio = session.cardio
        details = data.get("cardio") if isinstance(data.get("cardio"), dict) else {}
        raw_activity = details.get("activity")
        old_type = cardio.activity_type or (cardio.activity if cardio.activity in CARDIO_ACTIVITIES else "อื่นๆ")
        activity_type = str(raw_activity or old_type).strip()[:80]
        if activity_type not in CARDIO_ACTIVITIES:
            activity_type = "อื่นๆ"
        activity_changed = activity_type != old_type
        old_custom = cardio.activity if old_type == "อื่นๆ" and cardio.activity != "อื่นๆ" else None
        custom_name = str(details.get("custom_name") or "").strip()[:80] or None if "custom_name" in details else old_custom
        if activity_type == "อื่นๆ" and not custom_name:
            raise ValueError("กรุณาระบุชื่อกิจกรรมอื่นๆ")
        activity = custom_name if activity_type == "อื่นๆ" else activity_type
        variant = details.get("variant", None if activity_changed else cardio.variant)
        if variant is not None and variant not in CARDIO_VARIANTS.get(activity_type, set()):
            raise ValueError("ตัวเลือกระดับ/รูปแบบไม่ตรงกับประเภทกิจกรรม")
        values = {
            key: details[key] if key in details else None if activity_changed else getattr(cardio, key)
            for key in ("duration_min", "incline_pct", "speed_kmh", "distance_km", "steps")
        }
        user = db.query(User).filter(User.id == user_id).first()
        inputs = _cardio_inputs(activity_type, values, variant=variant, height_cm=user.height_cm if user else None, gender=user.gender if user else None)
        duration, met, calories = _cardio_estimate(activity_type, inputs, user.weight_kg if user else 0, variant)
        cardio_calculation = (activity, activity_type, variant, inputs, duration, met, calories)
    if "name" in data and str(data["name"]).strip():
        session.name = str(data["name"]).strip()[:150]
    if "notes" in data:
        session.notes = str(data["notes"] or "")[:5000] or None
    if "occurred_at" in data and data["occurred_at"]:
        session.occurred_at = data["occurred_at"]
    if "estimated_duration_min" in data and data["estimated_duration_min"] is not None:
        session.estimated_duration_min = max(0, float(data["estimated_duration_min"]))
    if "estimated_calories" in data:
        if data["estimated_calories"] is None:
            session.calories_estimated = True
        else:
            session.estimated_calories = max(0, float(data["estimated_calories"]))
            session.calories_estimated = False
    if session.session_type == "strength":
        exercises_changed = "exercises" in data
        duration_changed = "estimated_duration_min" in data and data["estimated_duration_min"] is not None
        if exercises_changed:
            db.query(SessionExercise).filter(SessionExercise.session_id == session.id).delete(synchronize_session=False)
            exercises = []
            for index, item in enumerate(data.get("exercises") or [], 1):
                name = str(item.get("name") or "").strip()
                if name:
                    exercises.append(SessionExercise(
                        session_id=session.id,
                        name=name[:100],
                        sets=max(0, int(item.get("sets", 0))),
                        repetitions=max(0, int(item.get("repetitions", 0))),
                        weight=_number(item.get("weight")),
                        notes=str(item.get("notes") or "").strip()[:2000] or None,
                        order_num=index,
                    ))
            db.add_all(exercises)
            if not duration_changed:
                session.estimated_duration_min = estimate_strength_duration_min(exercises)
        if session.calories_estimated and (exercises_changed or duration_changed or reset_calories):
            user = db.query(User).filter(User.id == user_id).first()
            session.estimated_calories = estimate_strength_calories(user.weight_kg if user else None, session.estimated_duration_min)
    if cardio_calculation:
        cardio = session.cardio
        activity, activity_type, variant, inputs, duration, met, calories = cardio_calculation
        cardio.activity = activity
        cardio.activity_type = activity_type
        cardio.variant = variant
        for key in ("duration_min", "incline_pct", "speed_kmh", "distance_km", "steps"):
            setattr(cardio, key, inputs[key])
        cardio.met = met
        session.estimated_duration_min = duration
        if session.calories_estimated:
            session.estimated_calories = calories
    db.commit()
    return _owned_session(db, user_id, session.id)


def delete_session(db: Session, user_id: str, session_id: int) -> bool:
    session = _owned_session(db, user_id, session_id)
    if not session:
        return False
    db.delete(session)
    db.commit()
    return True
