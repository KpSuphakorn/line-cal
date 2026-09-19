"""Fitness and Nutrition calculations engine."""
from datetime import datetime, date, time
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.models import User, FoodLog, WorkoutLog, UserExercise
from app.data.presets import WORKOUT_SPLITS


def seed_user_exercises_if_needed(db: Session, user_id: str):
    """Seed user default workout exercises into DB if not already present."""
    count = db.query(UserExercise).filter(UserExercise.user_id == user_id).count()
    if count > 0:
        return

    for split_id, split in WORKOUT_SPLITS.items():
        for idx, ex in enumerate(split["exercises"]):
            item = UserExercise(
                user_id=user_id,
                split_id=split_id,
                name=ex["name"],
                weight=ex["weight"],
                target=ex["target"],
                order_num=idx + 1
            )
            db.add(item)
    db.commit()


def get_user_splits(db: Session, user_id: str) -> Dict[str, Any]:
    """Retrieve user customized 4-day workout splits from DB."""
    seed_user_exercises_if_needed(db, user_id)
    user_exercises = db.query(UserExercise).filter(
        UserExercise.user_id == user_id
    ).order_by(UserExercise.order_num.asc()).all()

    splits = {}
    for split_id, split_meta in WORKOUT_SPLITS.items():
        splits[split_id] = {
            "id": split_id,
            "name": split_meta["name"],
            "estimated_burn_kcal": split_meta["estimated_burn_kcal"],
            "exercises": []
        }

    for ex in user_exercises:
        if ex.split_id in splits:
            splits[ex.split_id]["exercises"].append({
                "id": ex.id,
                "name": ex.name,
                "weight": ex.weight,
                "target": ex.target
            })

    return splits


def update_exercise_weight(db: Session, user_id: str, exercise_query: str, new_weight: str) -> Optional[UserExercise]:
    """Search and update exercise weight by exercise name (case-insensitive substring match)."""
    seed_user_exercises_if_needed(db, user_id)
    exercises = db.query(UserExercise).filter(UserExercise.user_id == user_id).all()
    q = exercise_query.strip().lower()

    # Find matching exercise
    match = None
    for ex in exercises:
        if q in ex.name.lower():
            match = ex
            break

    if match:
        match.weight = new_weight.strip()
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


def get_or_create_user(db: Session, user_id: str, default_settings: Any) -> User:
    """Ensure user exists with personal default metrics."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        user = User(
            id=user_id,
            name="Suphakorn",
            gender=default_settings.USER_DEFAULT_GENDER,
            age=default_settings.USER_DEFAULT_AGE,
            height_cm=default_settings.USER_DEFAULT_HEIGHT_CM,
            weight_kg=default_settings.USER_DEFAULT_WEIGHT_KG,
            daily_target_kcal=default_settings.USER_DEFAULT_DAILY_TARGET_KCAL,
            target_protein_g=default_settings.USER_DEFAULT_TARGET_PROTEIN_G,
            target_carbs_g=default_settings.USER_DEFAULT_TARGET_CARBS_G,
            target_fat_g=default_settings.USER_DEFAULT_TARGET_FAT_G,
            goal="recomposition"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_daily_summary(db: Session, user_id: str, target_date: date = None) -> Dict[str, Any]:
    """Calculate daily calorie intake, expenditure, remaining budget and macro breakdown."""
    if target_date is None:
        target_date = datetime.now().date()

    start_dt = datetime.combine(target_date, time.min)
    end_dt = datetime.combine(target_date, time.max)

    user = db.query(User).filter(User.id == user_id).first()
    target_kcal = user.daily_target_kcal if user else 1950.0
    target_protein = user.target_protein_g if user else 145.0
    target_carbs = user.target_carbs_g if user else 220.0
    target_fat = user.target_fat_g if user else 55.0

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

    # Get workout logs for today
    workout_logs = db.query(WorkoutLog).filter(
        WorkoutLog.user_id == user_id,
        WorkoutLog.logged_at >= start_dt,
        WorkoutLog.logged_at <= end_dt
    ).all()

    total_calories_burned = sum(w.calories_burned for w in workout_logs)

    # Remaining calorie budget = Target - In + Burned
    remaining_kcal = round(target_kcal - total_calories_in + total_calories_burned, 1)

    # Percentage consumed towards base target
    pct_consumed = round((total_calories_in / target_kcal) * 100, 1) if target_kcal > 0 else 0

    return {
        "date": target_date.strftime("%Y-%m-%d"),
        "date_display": target_date.strftime("%d/%m/%Y"),
        "target_kcal": round(target_kcal, 0),
        "calories_in": round(total_calories_in, 1),
        "calories_burned": round(total_calories_burned, 1),
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
                "meal_type": f.meal_type,
                "time": f.logged_at.strftime("%H:%M")
            }
            for f in food_logs
        ],
        "workout_logs": [
            {
                "id": w.id,
                "name": w.routine_name,
                "duration": w.duration_min,
                "burned": round(w.calories_burned, 1),
                "time": w.logged_at.strftime("%H:%M")
            }
            for w in workout_logs
        ]
    }


def get_weekly_stats(db: Session, user_id: str, days: int = 7) -> Dict[str, Any]:
    """Calculate 7-day fitness & nutrition performance statistics."""
    from datetime import timedelta
    today = datetime.now().date()
    start_date = today - timedelta(days=days - 1)
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(today, time.max)

    user = db.query(User).filter(User.id == user_id).first()
    target_kcal = user.daily_target_kcal if user else 1950.0
    target_protein = user.target_protein_g if user else 145.0

    # Food logs for period
    food_logs = db.query(FoodLog).filter(
        FoodLog.user_id == user_id,
        FoodLog.logged_at >= start_dt,
        FoodLog.logged_at <= end_dt
    ).all()

    # Workout logs for period
    workout_logs = db.query(WorkoutLog).filter(
        WorkoutLog.user_id == user_id,
        WorkoutLog.logged_at >= start_dt,
        WorkoutLog.logged_at <= end_dt
    ).all()

    total_calories_in = sum(f.calories for f in food_logs)
    total_protein = sum(f.protein for f in food_logs)
    total_carbs = sum(f.carbs for f in food_logs)
    total_fat = sum(f.fat for f in food_logs)
    total_burned = sum(w.calories_burned for w in workout_logs)

    # Days logged count
    days_with_logs = len(set(f.logged_at.date() for f in food_logs))
    divisor = max(days_with_logs, 1)

    avg_calories = round(total_calories_in / divisor, 1)
    avg_protein = round(total_protein / divisor, 1)

    # Check 4-Day Workout Split completion
    split_done = {
        "day_1": any("day 1" in w.routine_name.lower() or "push" in w.routine_name.lower() for w in workout_logs),
        "day_2": any("day 2" in w.routine_name.lower() or "pull" in w.routine_name.lower() for w in workout_logs),
        "day_3": any("day 3" in w.routine_name.lower() or "lower" in w.routine_name.lower() or "ขา" in w.routine_name.lower() for w in workout_logs),
        "day_4": any("day 4" in w.routine_name.lower() or "upper" in w.routine_name.lower() for w in workout_logs),
    }
    weight_sessions_count = sum(1 for w in workout_logs if w.workout_type == "weights")

    # Cardio stats
    cardio_logs = [w for w in workout_logs if w.workout_type == "cardio" or "เดินชัน" in w.routine_name]
    cardio_count = len(cardio_logs)
    cardio_minutes = sum(w.duration_min for w in cardio_logs)

    return {
        "start_date": start_date.strftime("%d/%m"),
        "end_date": today.strftime("%d/%m"),
        "days_logged": days_with_logs,
        "total_calories_in": round(total_calories_in, 0),
        "total_calories_burned": round(total_burned, 0),
        "avg_daily_calories": avg_calories,
        "target_kcal": target_kcal,
        "avg_daily_protein": avg_protein,
        "target_protein": target_protein,
        "split_done": split_done,
        "weights_completed": weight_sessions_count,
        "weights_target": 4,
        "cardio_count": cardio_count,
        "cardio_target": 2,
        "cardio_minutes": cardio_minutes
    }


def get_past_food_history(db: Session, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieve recent food log entries."""
    logs = db.query(FoodLog).filter(
        FoodLog.user_id == user_id
    ).order_by(FoodLog.logged_at.desc()).limit(limit).all()

    return [
        {
            "id": log.id,
            "name": log.food_name,
            "portion": log.portion,
            "calories": int(log.calories),
            "protein": round(log.protein, 1),
            "carbs": round(log.carbs, 1),
            "fat": round(log.fat, 1),
            "date": log.logged_at.strftime("%d/%m"),
            "time": log.logged_at.strftime("%H:%M")
        }
        for log in logs
    ]
