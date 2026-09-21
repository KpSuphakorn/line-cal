"""Fitness and Nutrition calculations engine."""
from datetime import datetime, date, time, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional, Iterable
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.models import (
    User,
    FoodLog,
    WorkoutSession,
    ProgramTemplate,
    TemplateExercise,
    WorkoutProgram,
    ProgramExercise,
    CardioPreset,
    FoodCapture,
    FoodAnalysisDraft,
    SessionExercise,
    CardioDetails,
    ProcessedWebhook,
)
from app.data.presets import PROGRAM_TEMPLATES
from app.config import settings

BANGKOK = ZoneInfo("Asia/Bangkok")


def estimate_strength_duration_min(exercises: Iterable[Any]) -> float:
    """Estimate strength time using the agreed defaults, without a timer UI."""
    exercises = list(exercises or [])
    seconds = 0
    for exercise in exercises:
        sets = max(0, int(getattr(exercise, "sets", 0)))
        repetitions = max(0, int(getattr(exercise, "repetitions", 0)))
        seconds += sets * repetitions * 3
        seconds += max(sets - 1, 0) * 60
    seconds += max(len(exercises) - 1, 0) * 120
    return round(seconds / 60.0, 1)


def estimate_strength_calories(weight_kg: float | None, duration_min: float, met: float | None = None) -> float:
    """Conservative session-level estimate; lifted weight is progression data only."""
    if not weight_kg or duration_min <= 0:
        return 0.0
    return round(float(met or getattr(settings, "STRENGTH_MET", 3.5)) * 3.5 * float(weight_kg) / 200.0 * float(duration_min), 1)


def bangkok_day_bounds(target_date: date | None = None):
    """Return timezone-aware UTC bounds for a Bangkok calendar day.

    Kept timezone-aware (not naive) so the comparison against
    `DateTime(timezone=True)` columns is correct regardless of the
    database session's timezone setting; a naive bound is interpreted
    using the session's local TimeZone on Postgres, which silently
    shifts "today" if that session default is ever not UTC.
    """
    day = target_date or datetime.now(BANGKOK).date()
    start = datetime.combine(day, time.min, tzinfo=BANGKOK).astimezone(timezone.utc)
    end = datetime.combine(day, time.max, tzinfo=BANGKOK).astimezone(timezone.utc)
    return start, end


def as_bangkok(value: datetime | None) -> datetime | None:
    """Interpret persisted naive values as UTC, then render in Bangkok time."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(BANGKOK)


def seed_program_templates(db: Session) -> None:
    """Create the three system templates once; templates are never user-owned."""
    for template_data in PROGRAM_TEMPLATES:
        template = db.query(ProgramTemplate).filter(ProgramTemplate.key == template_data["key"]).first()
        if template is None:
            template = ProgramTemplate(key=template_data["key"], name=template_data["name"])
            db.add(template)
            db.flush()
            for index, exercise in enumerate(template_data["exercises"], start=1):
                db.add(TemplateExercise(
                    template_id=template.id,
                    name=exercise["name"],
                    sets=exercise.get("sets", 3),
                    repetitions=exercise.get("repetitions", 10),
                    weight=exercise.get("weight"),
                    notes=exercise.get("notes"),
                    order_num=index,
                ))
    db.commit()


def _existing_user_programs(db: Session, user_id: str) -> List[WorkoutProgram]:
    return db.query(WorkoutProgram).filter(WorkoutProgram.user_id == user_id).all()


def seed_user_programs_if_needed(db: Session, user_id: str) -> List[WorkoutProgram]:
    """Copy Push/Pull/Legs templates for a completed user, idempotently."""
    existing = _existing_user_programs(db, user_id)
    if existing:
        return existing
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not is_user_profile_customized(user):
        return []

    seed_program_templates(db)
    templates = db.query(ProgramTemplate).order_by(ProgramTemplate.id.asc()).all()
    try:
        for template in templates:
            program = WorkoutProgram(
                user_id=user_id,
                template_id=template.id,
                source_key=template.key,
                name=template.name,
            )
            db.add(program)
            db.flush()
            for exercise in sorted(template.exercises, key=lambda item: item.order_num):
                db.add(ProgramExercise(
                    program_id=program.id,
                    name=exercise.name,
                    sets=exercise.sets,
                    repetitions=exercise.repetitions,
                    weight=exercise.weight,
                    notes=exercise.notes,
                    order_num=exercise.order_num,
                ))
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _existing_user_programs(db, user_id)
        if existing:
            return existing
        raise
    return _existing_user_programs(db, user_id)


def get_user_programs(db: Session, user_id: str) -> Dict[str, Any]:
    """Return only the authenticated user's editable workout programs."""
    programs = seed_user_programs_if_needed(db, user_id)
    return {
        str(program.id): {
            "id": program.id,
            "name": program.name,
            "source_key": program.source_key,
            "exercises": [
                {
                    "id": exercise.id,
                    "name": exercise.name,
                    "sets": exercise.sets,
                    "repetitions": exercise.repetitions,
                    "weight": exercise.weight,
                    "notes": exercise.notes or "",
                }
                for exercise in program.exercises
            ],
        }
        for program in programs
    }


def update_exercise_weight(db: Session, user_id: str, exercise_query: str, new_weight: str) -> Optional[Any]:
    """Update a matching exercise in the user's program."""
    programs = seed_user_programs_if_needed(db, user_id)
    exercises = [exercise for program in programs for exercise in program.exercises]
    q = exercise_query.strip().lower()

    # Find matching exercise
    match = None
    for ex in exercises:
        if q in ex.name.lower():
            match = ex
            break

    if match:
        try:
            match.weight = float(str(new_weight).replace("kg", "").strip())
        except ValueError:
            match.notes = new_weight.strip()
        db.commit()
        db.refresh(match)
        return match
    return None


def calculate_bmr(gender: str, weight_kg: float, height_cm: float, age: int) -> float:
    """
    Calculate Basal Metabolic Rate (BMR) using Mifflin-St Jeor formula.
    Men: BMR = (10 * weight) + (6.25 * height) - (5 * age) + 5
    Women: BMR = (10 * weight) + (6.25 * height) - (5 * age) - 161
    """
    base = (10.0 * weight_kg) + (6.25 * height_cm) - (5.0 * age)
    if gender.lower() in ["male", "m", "ชาย"]:
        return round(base + 5.0, 1)
    else:
        return round(base - 161.0, 1)


def calculate_tdee(bmr: float, activity_multiplier: float = 1.45) -> float:
    """Calculate Total Daily Energy Expenditure (TDEE)."""
    return round(bmr * activity_multiplier, 1)


def calculate_incline_walk_burn(weight_kg: float, duration_min: int, incline_pct: float = 10.0) -> float:
    """
    Calculate calories burned during incline walking.
    Walking at ~4.8 km/h on 10-12% incline has MET ~7.5.
    Calories = (MET * 3.5 * weight_kg / 200) * duration_min
    """
    # MET increases slightly with higher incline
    met = 6.5 + (incline_pct * 0.1)
    burn = (met * 3.5 * weight_kg / 200.0) * duration_min
    return round(burn, 1)


def is_user_profile_customized(user: User) -> bool:
    """Check if the user has completed their profile setup."""
    return bool(
        user
        and user.profile_completed
        and user.name
        and user.gender
        and user.age
        and user.height_cm
        and user.weight_kg
        and user.goal
        and user.activity_level
    )


def get_or_create_user(db: Session, user_id: str, default_settings: Any) -> User:
    """Ensure a neutral, incomplete user exists until onboarding is submitted."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        user = User(
            id=user_id,
            name="",
            timezone="Asia/Bangkok",
            profile_completed=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_daily_summary(db: Session, user_id: str, target_date: date = None) -> Dict[str, Any]:
    """Calculate daily calorie intake, expenditure, remaining budget and macro breakdown."""
    if target_date is None:
        target_date = datetime.now(BANGKOK).date()

    start_dt, end_dt = bangkok_day_bounds(target_date)

    user = db.query(User).filter(User.id == user_id).first()
    target_kcal = (user.daily_target_kcal if user and user.daily_target_kcal is not None else 0.0)
    target_protein = (user.target_protein_g if user and user.target_protein_g is not None else 0.0)
    target_carbs = (user.target_carbs_g if user and user.target_carbs_g is not None else 0.0)
    target_fat = (user.target_fat_g if user and user.target_fat_g is not None else 0.0)

    # Get food logs for today
    food_logs = db.query(FoodLog).filter(
        FoodLog.user_id == user_id,
        FoodLog.logged_at >= start_dt,
        FoodLog.logged_at <= end_dt
    ).all()

    total_calories_in = sum(f.calories for f in food_logs)
    total_protein = sum(f.protein for f in food_logs)
    total_carbs = sum(f.carbs for f in food_logs)
    total_fat = sum(f.fat for f in food_logs)

    workout_sessions = db.query(WorkoutSession).filter(
        WorkoutSession.user_id == user_id,
        WorkoutSession.occurred_at >= start_dt,
        WorkoutSession.occurred_at <= end_dt,
    ).all()

    total_calories_burned = sum(w.estimated_calories or 0 for w in workout_sessions)

    # Exercise is shown separately; it never increases the food target.
    remaining_kcal = round(target_kcal - total_calories_in, 1)
    net_kcal = round(total_calories_in - total_calories_burned, 1)

    # Percentage consumed towards base target
    pct_consumed = round((total_calories_in / target_kcal) * 100, 1) if target_kcal > 0 else 0

    return {
        "user_id": user_id,
        "user_name": user.name if user else "User",
        "date": target_date.strftime("%Y-%m-%d"),
        "date_display": target_date.strftime("%d/%m/%Y"),
        "target_kcal": round(target_kcal, 0),
        "calories_in": round(total_calories_in, 1),
        "calories_burned": round(total_calories_burned, 1),
        "food_consumed": round(total_calories_in, 1),
        "food_target": round(target_kcal, 1),
        "exercise_estimate": round(total_calories_burned, 1),
        "net": net_kcal,
        "remaining_kcal": remaining_kcal,
        "pct_consumed": pct_consumed,
        "protein": round(total_protein, 1),
        "target_protein": round(target_protein, 1),
        "carbs": round(total_carbs, 1),
        "target_carbs": round(target_carbs, 1),
        "fat": round(total_fat, 1),
        "target_fat": round(target_fat, 1),
        "food_logs": [
            {
                "id": f.id,
                "name": f.food_name,
                "portion": f.portion,
                "calories": round(f.calories, 1),
                "protein": round(f.protein, 1),
                "carbs": round(f.carbs, 1),
                "fat": round(f.fat, 1),
                "time": as_bangkok(f.logged_at).strftime("%H:%M")
            }
            for f in food_logs
        ],
        "workout_logs": sorted([
            {
                "id": w.id,
                "name": w.name,
                "duration": round(w.estimated_duration_min or 0, 1),
                "burned": round(w.estimated_calories or 0, 1),
                "time": as_bangkok(w.occurred_at).strftime("%H:%M"),
                "type": w.session_type,
                "estimated": bool(w.calories_estimated),
            }
            for w in workout_sessions
        ],
            key=lambda item: item["time"],
        )
    }


def get_history_summary(
    db: Session,
    user_id: str,
    period: str = "week",
    anchor: date | None = None,
) -> Dict[str, Any]:
    """Return a bounded history summary without loading unrelated sessions."""
    import calendar

    period = period.lower().strip()
    anchor = anchor or datetime.now(BANGKOK).date()
    if period == "month":
        start_date = date(anchor.year, anchor.month, 1)
        end_date = date(anchor.year, anchor.month, calendar.monthrange(anchor.year, anchor.month)[1])
    elif period == "week":
        start_date = anchor - timedelta(days=anchor.weekday())
        end_date = start_date + timedelta(days=6)
    else:
        raise ValueError("period must be week or month")

    start_dt, _ = bangkok_day_bounds(start_date)
    _, end_dt = bangkok_day_bounds(end_date)
    food_logs = db.query(FoodLog).filter(
        FoodLog.user_id == user_id,
        FoodLog.logged_at >= start_dt,
        FoodLog.logged_at <= end_dt,
    ).order_by(FoodLog.logged_at.asc()).all()
    workout_sessions = db.query(WorkoutSession).filter(
        WorkoutSession.user_id == user_id,
        WorkoutSession.occurred_at >= start_dt,
        WorkoutSession.occurred_at <= end_dt,
    ).order_by(WorkoutSession.occurred_at.asc()).all()

    daily_data = {}
    day_count = (end_date - start_date).days + 1
    for offset in range(day_count):
        day = start_date + timedelta(days=offset)
        daily_data[day.isoformat()] = {
            "date": day.isoformat(),
            "date_display": day.strftime("%d/%m"),
            "calories_in": 0.0,
            "calories_burned": 0.0,
            "protein": 0.0,
            "food_logs": [],
            "workout_logs": [],
        }

    for food in food_logs:
        local_time = as_bangkok(food.logged_at)
        item = daily_data.get(local_time.date().isoformat())
        if item is None:
            continue
        item["calories_in"] += food.calories or 0
        item["protein"] += food.protein or 0
        item["food_logs"].append({
            "id": food.id,
            "name": food.food_name,
            "portion": food.portion,
            "calories": round(food.calories or 0, 1),
            "protein": round(food.protein or 0, 1),
            "time": local_time.strftime("%H:%M"),
        })

    for session in workout_sessions:
        local_time = as_bangkok(session.occurred_at)
        item = daily_data.get(local_time.date().isoformat())
        if item is None:
            continue
        item["calories_burned"] += session.estimated_calories or 0
        item["workout_logs"].append({
            "id": session.id,
            "name": session.name,
            "type": session.session_type,
            "occurred_at": session.occurred_at.isoformat() if session.occurred_at else None,
            # Keep history rows aligned with the canonical session serializer
            # consumed by Today and the workout editor.
            "estimated_duration_min": round(session.estimated_duration_min or 0, 1),
            "estimated_calories": round(session.estimated_calories or 0, 1),
            "time": local_time.strftime("%H:%M"),
        })

    for item in daily_data.values():
        item["calories_in"] = round(item["calories_in"], 1)
        item["calories_burned"] = round(item["calories_burned"], 1)
        item["protein"] = round(item["protein"], 1)

    user = db.query(User).filter(User.id == user_id).first()
    target_kcal = float(user.daily_target_kcal) if user and user.daily_target_kcal is not None else 0.0
    total_in = round(sum(item["calories_in"] for item in daily_data.values()), 1)
    total_burned = round(sum(item["calories_burned"] for item in daily_data.values()), 1)
    active_days = sum(1 for item in daily_data.values() if item["food_logs"] or item["workout_logs"])
    food_logged_days = sum(1 for item in daily_data.values() if item["food_logs"])
    workout_logged_days = sum(1 for item in daily_data.values() if item["workout_logs"])
    food_day_divisor = max(food_logged_days, 1)
    workout_day_divisor = max(workout_logged_days, 1)
    peak_day = max(
        daily_data.values(),
        key=lambda item: (item["calories_in"], item["date"]),
    ) if daily_data else None
    years = {datetime.now(BANGKOK).year, anchor.year}
    for value in db.query(FoodLog.logged_at).filter(FoodLog.user_id == user_id).all():
        years.add(as_bangkok(value[0]).year)
    for value in db.query(WorkoutSession.occurred_at).filter(WorkoutSession.user_id == user_id).all():
        years.add(as_bangkok(value[0]).year)
    oldest_year = min(years)
    newest_year = max(years)
    return {
        "period": period,
        "anchor": anchor.isoformat(),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "available_years": list(range(oldest_year, newest_year + 1)),
        "summary": {
            "total_calories_in": total_in,
            "total_calories_burned": total_burned,
            "total_food_entries": len(food_logs),
            "total_workout_sessions": len(workout_sessions),
            "active_days": active_days,
            "food_logged_days": food_logged_days,
            "workout_logged_days": workout_logged_days,
            "average_daily_calories": round(total_in / food_day_divisor, 1),
            "average_daily_burned": round(total_burned / workout_day_divisor, 1),
            "target_kcal": target_kcal,
            "peak_day": {
                "date": peak_day["date"],
                "date_display": peak_day["date_display"],
                "calories_in": peak_day["calories_in"],
            } if peak_day and peak_day["calories_in"] > 0 else None,
        },
        "daily_breakdown": list(daily_data.values()),
    }


def update_food_log(db: Session, food_id: int, updates: Dict[str, Any], user_id: str | None = None) -> Optional[FoodLog]:
    """Update calories and macros for an existing food log entry."""
    query = db.query(FoodLog).filter(FoodLog.id == food_id)
    if user_id is not None:
        query = query.filter(FoodLog.user_id == user_id)
    food = query.first()
    if not food:
        return None

    if "calories" in updates:
        food.calories = float(updates["calories"])
    if "protein" in updates:
        food.protein = float(updates["protein"])
    if "carbs" in updates:
        food.carbs = float(updates["carbs"])
    if "fat" in updates:
        food.fat = float(updates["fat"])
    if "food_name" in updates:
        food.food_name = str(updates["food_name"])
    if "portion" in updates:
        food.portion = str(updates["portion"])

    db.commit()
    db.refresh(food)
    return food


def delete_food_log(db: Session, food_id: int, user_id: str | None = None) -> bool:
    """Delete a food log entry by ID."""
    query = db.query(FoodLog).filter(FoodLog.id == food_id)
    if user_id is not None:
        query = query.filter(FoodLog.user_id == user_id)
    food = query.first()
    if not food:
        return False
    db.delete(food)
    db.commit()
    return True


def get_user_profile(db: Session, user_id: str) -> Dict[str, Any]:
    """Retrieve personal metrics, BMR, TDEE, and targets for a user."""
    from app.config import settings
    user = get_or_create_user(db, user_id, settings)
    gender = user.gender or ""
    weight = user.weight_kg
    height = user.height_cm
    age = user.age
    if not is_user_profile_customized(user):
        return {
            "id": user.id,
            "name": user.name or "",
            "gender": gender,
            "age": age,
            "height_cm": height,
            "weight_kg": weight,
            "goal": user.goal or "",
            "activity_level": user.activity_level or "",
            "profile_completed": False,
            "bmr": None,
            "tdee": None,
            "daily_target_kcal": None,
            "target_protein_g": None,
            "target_carbs_g": None,
            "target_fat_g": None,
            "targets_customized": False,
        }
    bmr = calculate_bmr(gender, weight, height, age)
    tdee = calculate_tdee(bmr, float(user.activity_level or 1.45))
    return {
        "id": user.id,
        "name": user.name or "User",
        "gender": gender,
        "age": age,
        "height_cm": height,
        "weight_kg": weight,
        "goal": user.goal or "recomposition",
        "activity_level": user.activity_level,
        "profile_completed": True,
        "bmr": bmr,
        "tdee": tdee,
        "daily_target_kcal": round(user.daily_target_kcal or 1950.0, 0),
        "target_protein_g": round(user.target_protein_g or 145.0, 0),
        "target_carbs_g": round(user.target_carbs_g or 220.0, 0),
        "target_fat_g": round(user.target_fat_g or 55.0, 0),
        "targets_customized": bool(user.targets_customized),
    }


def _calculate_nutrition_targets(user: User, activity_multiplier: float) -> Dict[str, float]:
    bmr = calculate_bmr(user.gender, user.weight_kg, user.height_cm, user.age)
    tdee = calculate_tdee(bmr, activity_multiplier)
    goal = (user.goal or "").lower()
    if "cut" in goal or "ลด" in goal:
        target_kcal = round(tdee - 500, 0)
    elif "bulk" in goal or "เพิ่ม" in goal:
        target_kcal = round(tdee + 300, 0)
    else:
        target_kcal = round(tdee - 300, 0)

    target_protein = round(user.weight_kg * 2.0, 0)
    fat_cals = target_kcal * 0.25
    target_fat = round(fat_cals / 9, 0)
    carb_cals = max(0, target_kcal - (target_protein * 4) - fat_cals)
    return {
        "daily_target_kcal": target_kcal,
        "target_protein_g": target_protein,
        "target_carbs_g": round(carb_cals / 4, 0),
        "target_fat_g": target_fat,
    }


def update_user_profile(db: Session, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Update user personal metrics and recalculate BMR, TDEE, and nutrition targets."""
    from app.config import settings
    user = get_or_create_user(db, user_id, settings)

    data = dict(data)
    if "name" in data and data["name"]:
        user.name = str(data["name"]).strip()
    if "gender" in data and data["gender"]:
        user.gender = str(data["gender"]).strip().lower()
    if "age" in data and data["age"]:
        user.age = int(data["age"])
    if "height_cm" in data and data["height_cm"]:
        user.height_cm = float(data["height_cm"])
    if "weight_kg" in data and data["weight_kg"]:
        user.weight_kg = float(data["weight_kg"])
    if "goal" in data and data["goal"]:
        user.goal = str(data["goal"]).strip()

    if "birth_date" in data and data["birth_date"]:
        from datetime import date as date_type
        value = data["birth_date"]
        user.birth_date = date_type.fromisoformat(value) if isinstance(value, str) else value

    if "activity_level" in data and data["activity_level"]:
        user.activity_level = str(data["activity_level"]).strip()

    raw_activity = data.get("activity_multiplier")
    if raw_activity is None:
        raw_activity = data.get("activity_level", user.activity_level or 1.45)
    try:
        activity_mult = float(raw_activity)
    except (TypeError, ValueError):
        activity_mult = {"sedentary": 1.2, "light": 1.375, "moderate": 1.45, "active": 1.55, "very_active": 1.725}.get(str(raw_activity).lower(), 1.45)
    if activity_mult not in {1.2, 1.375, 1.45, 1.55, 1.725}:
        raise ValueError("activity_multiplier must be one of the supported activity levels")
    user.activity_level = str(activity_mult)
    required_profile_fields = ("name", "gender", "age", "height_cm", "weight_kg", "goal", "activity_level")
    if any(getattr(user, field, None) in (None, "") for field in required_profile_fields):
        user.profile_completed = False
        db.commit()
        db.refresh(user)
        return get_user_profile(db, user_id)
    reset_targets = bool(data.get("reset_targets", False))
    target_fields = ("daily_target_kcal", "target_protein_g", "target_carbs_g", "target_fat_g")
    has_manual_target_input = any(field in data and data[field] is not None for field in target_fields)
    if reset_targets:
        user.targets_customized = False
    elif has_manual_target_input:
        user.targets_customized = True

    targets = _calculate_nutrition_targets(user, activity_mult)
    if not user.targets_customized:
        for field, value in targets.items():
            setattr(user, field, value)
    if not reset_targets:
        for field in target_fields:
            if data.get(field) is not None:
                setattr(user, field, float(data[field]))
    user.profile_completed = is_user_profile_customized(user) or all(
        getattr(user, field, None) not in (None, "")
        for field in ("name", "gender", "age", "height_cm", "weight_kg", "goal", "activity_level")
    )

    db.commit()
    db.refresh(user)
    if user.profile_completed:
        seed_user_programs_if_needed(db, user_id)
    return get_user_profile(db, user_id)


def delete_user_account(db: Session, user_id: str) -> bool:
    """Delete one user's private data while retaining global program templates."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        return False

    capture_ids = [row[0] for row in db.query(FoodCapture.id).filter(FoodCapture.user_id == user_id).all()]
    program_ids = [row[0] for row in db.query(WorkoutProgram.id).filter(WorkoutProgram.user_id == user_id).all()]
    session_ids = [row[0] for row in db.query(WorkoutSession.id).filter(WorkoutSession.user_id == user_id).all()]

    try:
        # Keep webhook idempotency history without retaining the deleted LINE ID.
        db.query(ProcessedWebhook).filter(ProcessedWebhook.user_id == user_id).update(
            {ProcessedWebhook.user_id: None}, synchronize_session=False
        )
        db.query(FoodLog).filter(FoodLog.user_id == user_id).delete(synchronize_session=False)
        if capture_ids:
            db.query(FoodAnalysisDraft).filter(FoodAnalysisDraft.capture_id.in_(capture_ids)).delete(synchronize_session=False)
            db.query(FoodCapture).filter(FoodCapture.id.in_(capture_ids)).delete(synchronize_session=False)
        if session_ids:
            db.query(CardioDetails).filter(CardioDetails.session_id.in_(session_ids)).delete(synchronize_session=False)
            db.query(SessionExercise).filter(SessionExercise.session_id.in_(session_ids)).delete(synchronize_session=False)
            db.query(WorkoutSession).filter(WorkoutSession.id.in_(session_ids)).delete(synchronize_session=False)
        if program_ids:
            db.query(ProgramExercise).filter(ProgramExercise.program_id.in_(program_ids)).delete(synchronize_session=False)
            db.query(WorkoutProgram).filter(WorkoutProgram.id.in_(program_ids)).delete(synchronize_session=False)
        db.query(CardioPreset).filter(CardioPreset.user_id == user_id).delete(synchronize_session=False)
        db.delete(user)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return True
