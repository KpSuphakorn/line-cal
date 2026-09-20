"""User-owned workout programs and historical session snapshots."""
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db.models import (
    CardioDetails,
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


def _number(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    return float(value)


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


def list_programs(db: Session, user_id: str) -> list[dict[str, Any]]:
    return [serialize_program(program) for program in seed_user_programs_if_needed(db, user_id)]


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
            "duration_min": session.cardio.duration_min,
            "incline_pct": session.cardio.incline_pct,
            "speed_kmh": session.cardio.speed_kmh,
            "distance_km": session.cardio.distance_km,
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


def create_strength_session(
    db: Session,
    user_id: str,
    program_id: int,
    source_event_id: str | None = None,
    occurred_at: datetime | None = None,
) -> WorkoutSession:
    if source_event_id:
        existing = db.query(WorkoutSession).filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.source_event_id == source_event_id,
        ).first()
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
    return _owned_session(db, user_id, session.id)


def create_cardio_session(
    db: Session,
    user_id: str,
    activity: str,
    duration_min: float,
    incline_pct: float | None = None,
    speed_kmh: float | None = None,
    distance_km: float | None = None,
    source_event_id: str | None = None,
    occurred_at: datetime | None = None,
) -> WorkoutSession:
    if source_event_id:
        existing = db.query(WorkoutSession).filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.source_event_id == source_event_id,
        ).first()
        if existing:
            return existing
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not is_user_profile_customized(user):
        raise PermissionError("Complete your profile before logging exercise")
    activity = str(activity or "อื่นๆ").strip()[:80]
    met = CARDIO_METS.get(activity, CARDIO_METS["อื่นๆ"])
    duration_min = float(duration_min)
    if duration_min <= 0:
        raise ValueError("duration_min must be positive")
    calories = round(met * 3.5 * float(user.weight_kg) / 200.0 * duration_min, 1)
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
            duration_min=duration_min,
            incline_pct=incline_pct,
            speed_kmh=speed_kmh,
            distance_km=distance_km,
            met=met,
        ),
    )
    db.add(session)
    db.commit()
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
    if "name" in data and str(data["name"]).strip():
        session.name = str(data["name"]).strip()[:150]
    if "notes" in data:
        session.notes = str(data["notes"] or "")[:5000] or None
    if "occurred_at" in data and data["occurred_at"]:
        session.occurred_at = data["occurred_at"]
    if "estimated_duration_min" in data and data["estimated_duration_min"] is not None:
        session.estimated_duration_min = max(0, float(data["estimated_duration_min"]))
    if "estimated_calories" in data and data["estimated_calories"] is not None:
        session.estimated_calories = max(0, float(data["estimated_calories"]))
        session.calories_estimated = False
    if session.session_type == "strength" and "exercises" in data:
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
        if "estimated_duration_min" not in data:
            session.estimated_duration_min = estimate_strength_duration_min(exercises)
        if "estimated_calories" not in data:
            user = db.query(User).filter(User.id == user_id).first()
            session.estimated_calories = estimate_strength_calories(user.weight_kg if user else None, session.estimated_duration_min)
    if session.session_type == "cardio" and isinstance(data.get("cardio"), dict):
        cardio = session.cardio
        if cardio:
            details = data["cardio"]
            for key in ("activity", "duration_min", "incline_pct", "speed_kmh", "distance_km"):
                if key in details:
                    setattr(cardio, key, details[key])
            cardio.activity = str(cardio.activity or "อื่นๆ")[:80]
            cardio.met = CARDIO_METS.get(cardio.activity, CARDIO_METS["อื่นๆ"])
            session.estimated_duration_min = float(cardio.duration_min)
            if "estimated_calories" not in data:
                user = db.query(User).filter(User.id == user_id).first()
                session.estimated_calories = round(cardio.met * 3.5 * float(user.weight_kg) / 200.0 * cardio.duration_min, 1)
    db.commit()
    return _owned_session(db, user_id, session.id)


def delete_session(db: Session, user_id: str, session_id: int) -> bool:
    session = _owned_session(db, user_id, session_id)
    if not session:
        return False
    db.delete(session)
    db.commit()
    return True
