import logging
from pathlib import Path
from typing import Optional
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Header, HTTPException, Depends, UploadFile, File, Query
from fastapi.responses import PlainTextResponse, HTMLResponse
from pydantic import BaseModel, Field
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from sqlalchemy.orm import Session

from app.config import settings
from app.auth import AuthenticatedUser, get_current_user
from app.db.database import init_db, get_db
from app.services.line_handler import handle_line_events
from app.services.fitness import (
    get_daily_summary, get_or_create_user, get_monthly_summary, update_food_log, delete_food_log,
    get_user_profile, update_user_profile, is_user_profile_customized
)
from app.services.ai_vision import analyze_food_image
from app.services.food_capture import get_capture, serialize_capture, update_capture, confirm_capture, cancel_capture, ai_quota_remaining
from app.templates.flex_cards import create_food_analyzed_card
from app.services.workouts import (
    create_cardio_session,
    create_strength_session,
    delete_program,
    delete_session,
    get_session,
    list_programs,
    list_sessions,
    save_program,
    serialize_session,
    update_session,
)

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("line_cal")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables on application startup."""
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized successfully.")
    yield
    logger.info("Application shutting down...")


app = FastAPI(
    title="LINE Calorie & Fitness Companion API",
    description="Multi-user food capture, nutrition summaries, and workout programs",
    version="2.0.0",
    lifespan=lifespan
)


def require_completed_profile(user_id: str, db: Session) -> None:
    user = get_or_create_user(db, user_id, settings)
    if not is_user_profile_customized(user):
        raise HTTPException(status_code=409, detail="Complete your profile before logging data")

# LINE Webhook Parser
parser = WebhookParser(settings.LINE_CHANNEL_SECRET)


@app.get("/")
def root():
    return {
        "status": "online",
        "app": "LINE Calorie & Fitness Companion",
        "version": "2.0.0",
        "user": "authenticated LINE users",
        "docs_url": "/docs"
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.post("/webhook")
async def line_webhook(
    request: Request,
    x_line_signature: str = Header(None),
    db: Session = Depends(get_db)
):
    """LINE Messaging API Webhook Endpoint."""
    if not x_line_signature:
        raise HTTPException(status_code=400, detail="Missing X-Line-Signature header")

    body = await request.body()
    body_text = body.decode("utf-8")

    try:
        events = parser.parse(body_text, x_line_signature)
    except InvalidSignatureError:
        logger.warning("Invalid LINE Webhook Signature received.")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        logger.error(f"Error parsing webhook body: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # Process events synchronously
    handle_line_events(events, db)

    return PlainTextResponse("OK", status_code=200)


@app.post("/api/simulate/analyze-food")
async def simulate_analyze_food(
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Test endpoint: Upload any food image to test Gemini Vision AI
    without needing a live LINE webhook. Returns JSON and Flex Message preview.
    """
    if settings.APP_ENV.lower() in {"production", "prod"}:
        raise HTTPException(status_code=404, detail="Simulator disabled in production")
    require_completed_profile(current_user.subject, db)
    if ai_quota_remaining(db, current_user.subject) <= 0:
        raise HTTPException(status_code=429, detail="Daily AI food analysis limit reached")
    allowed = {item.strip() for item in settings.ALLOWED_IMAGE_TYPES.split(",") if item.strip()}
    if file.content_type not in allowed:
        raise HTTPException(status_code=415, detail="Unsupported image type")
    contents = await file.read(settings.MAX_UPLOAD_BYTES + 1)
    if len(contents) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image is too large")
    food_data = analyze_food_image(contents)
    flex_preview = create_food_analyzed_card(food_data, "test_id_123")

    return {
        "analysis": food_data,
        "flex_preview": flex_preview
    }


# ─── Web App Dashboard ───────────────────────────────────────────

@app.get("/webapp", response_class=HTMLResponse)
def webapp_dashboard():
    """Serve the unified mobile-first Web App Dashboard."""
    html_path = Path(__file__).parent / "templates" / "dashboard.html"
    if html_path.exists():
        return HTMLResponse(
            content=html_path.read_text(encoding="utf-8").replace(
                "</head>",
                f'<script>window.__LINE_CAL_CONFIG__={{liffId:{settings.LIFF_ID!r}}};</script></head>',
            ),
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    return HTMLResponse(content="<h1>Dashboard Not Found</h1>", status_code=404)


# ─── API Endpoints ───────────────────────────────────────────────

class FoodUpdatePayload(BaseModel):
    calories: Optional[float] = Field(default=None, ge=0, le=100000)
    protein: Optional[float] = Field(default=None, ge=0, le=10000)
    carbs: Optional[float] = Field(default=None, ge=0, le=10000)
    fat: Optional[float] = Field(default=None, ge=0, le=10000)
    food_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    portion: Optional[str] = Field(default=None, max_length=150)


class FoodDraftItemPayload(BaseModel):
    id: Optional[int] = None
    food_name: str = Field(min_length=1, max_length=200)
    portion: str = Field(default="1 ที่", max_length=150)
    calories: float = Field(default=0, ge=0, le=100000)
    protein: float = Field(default=0, ge=0, le=10000)
    carbs: float = Field(default=0, ge=0, le=10000)
    fat: float = Field(default=0, ge=0, le=10000)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    notes: Optional[str] = Field(default=None, max_length=1000)


class FoodDraftPayload(BaseModel):
    items: list[FoodDraftItemPayload] = Field(min_length=1, max_length=50)


class UserProfilePayload(BaseModel):
    name: Optional[str] = None
    birth_date: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = Field(default=None, ge=13, le=120)
    height_cm: Optional[float] = Field(default=None, ge=80, le=250)
    weight_kg: Optional[float] = Field(default=None, ge=20, le=400)
    goal: Optional[str] = None
    activity_level: Optional[str] = None
    activity_multiplier: Optional[float] = Field(default=1.45, ge=1.0, le=3.0)
    daily_target_kcal: Optional[float] = Field(default=None, ge=500, le=10000)
    target_protein_g: Optional[float] = Field(default=None, ge=0, le=1000)
    target_carbs_g: Optional[float] = Field(default=None, ge=0, le=2000)
    target_fat_g: Optional[float] = Field(default=None, ge=0, le=1000)
    reset_targets: bool = False


# Canonical owner-derived routes. These never accept an owner ID from the browser.
@app.get("/api/me/today")
def api_me_today(db: Session = Depends(get_db), current_user: AuthenticatedUser = Depends(get_current_user)):
    get_or_create_user(db, current_user.subject, settings)
    return get_daily_summary(db, current_user.subject)


@app.get("/api/me/monthly")
def api_me_monthly(year: int | None = Query(default=None), month: int | None = Query(default=None), db: Session = Depends(get_db), current_user: AuthenticatedUser = Depends(get_current_user)):
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Bangkok"))
    year, month = year or now.year, month or now.month
    if month < 1 or month > 12:
        raise HTTPException(status_code=422, detail="month must be between 1 and 12")
    return get_monthly_summary(db, current_user.subject, year, month)


@app.get("/api/me/profile")
def api_me_profile(db: Session = Depends(get_db), current_user: AuthenticatedUser = Depends(get_current_user)):
    return get_user_profile(db, current_user.subject)


@app.put("/api/me/profile")
def api_me_update_profile(payload: UserProfilePayload, db: Session = Depends(get_db), current_user: AuthenticatedUser = Depends(get_current_user)):
    return {"status": "success", "profile": update_user_profile(db, current_user.subject, payload.model_dump(exclude_none=True))}


class ProgramExercisePayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    sets: int = Field(default=3, ge=0, le=100)
    repetitions: int = Field(default=10, ge=0, le=1000)
    weight: Optional[float] = Field(default=None, ge=0, le=10000)
    notes: Optional[str] = Field(default=None, max_length=2000)


class WorkoutProgramPayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    exercises: list[ProgramExercisePayload] = Field(default_factory=list, max_length=100)


@app.get("/api/me/workout-programs")
def api_me_workout_programs(db: Session = Depends(get_db), current_user: AuthenticatedUser = Depends(get_current_user)):
    require_completed_profile(current_user.subject, db)
    return {"programs": list_programs(db, current_user.subject)}


@app.post("/api/me/workout-programs")
def api_me_create_workout_program(payload: WorkoutProgramPayload, db: Session = Depends(get_db), current_user: AuthenticatedUser = Depends(get_current_user)):
    require_completed_profile(current_user.subject, db)
    return save_program(db, current_user.subject, payload.model_dump())


@app.put("/api/me/workout-programs/{program_id}")
def api_me_update_workout_program(program_id: int, payload: WorkoutProgramPayload, db: Session = Depends(get_db), current_user: AuthenticatedUser = Depends(get_current_user)):
    require_completed_profile(current_user.subject, db)
    try:
        return save_program(db, current_user.subject, payload.model_dump(), program_id=program_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/me/workout-programs/{program_id}")
def api_me_delete_workout_program(program_id: int, db: Session = Depends(get_db), current_user: AuthenticatedUser = Depends(get_current_user)):
    require_completed_profile(current_user.subject, db)
    if not delete_program(db, current_user.subject, program_id):
        raise HTTPException(status_code=404, detail="Workout program not found")
    return {"status": "deleted"}


class SessionExercisePayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    sets: int = Field(default=0, ge=0, le=100)
    repetitions: int = Field(default=0, ge=0, le=1000)
    weight: Optional[float] = Field(default=None, ge=0, le=10000)
    notes: Optional[str] = Field(default=None, max_length=2000)


class WorkoutSessionPayload(BaseModel):
    program_id: int = Field(gt=0)
    source_event_id: Optional[str] = Field(default=None, max_length=128)
    occurred_at: Optional[datetime] = None


class CardioPayload(BaseModel):
    activity: str = Field(min_length=1, max_length=80)
    duration_min: float = Field(gt=0, le=1440)
    incline_pct: Optional[float] = Field(default=None, ge=0, le=100)
    speed_kmh: Optional[float] = Field(default=None, ge=0, le=100)
    distance_km: Optional[float] = Field(default=None, ge=0, le=1000)
    source_event_id: Optional[str] = Field(default=None, max_length=128)
    occurred_at: Optional[datetime] = None


class WorkoutSessionUpdatePayload(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    notes: Optional[str] = Field(default=None, max_length=5000)
    occurred_at: Optional[datetime] = None
    estimated_duration_min: Optional[float] = Field(default=None, ge=0, le=1440)
    estimated_calories: Optional[float] = Field(default=None, ge=0, le=100000)
    exercises: Optional[list[SessionExercisePayload]] = Field(default=None, max_length=100)
    cardio: Optional[CardioPayload] = None


@app.post("/api/me/workout-sessions")
def api_me_create_workout_session(payload: WorkoutSessionPayload, db: Session = Depends(get_db), current_user: AuthenticatedUser = Depends(get_current_user)):
    require_completed_profile(current_user.subject, db)
    try:
        session = create_strength_session(db, current_user.subject, payload.program_id, source_event_id=payload.source_event_id, occurred_at=payload.occurred_at)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return serialize_session(session)


@app.post("/api/me/workout-sessions/cardio")
def api_me_create_cardio_session(payload: CardioPayload, db: Session = Depends(get_db), current_user: AuthenticatedUser = Depends(get_current_user)):
    require_completed_profile(current_user.subject, db)
    try:
        session = create_cardio_session(db, current_user.subject, **payload.model_dump(exclude_none=True))
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return serialize_session(session)


@app.get("/api/me/workout-sessions")
def api_me_workout_sessions(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db), current_user: AuthenticatedUser = Depends(get_current_user)):
    require_completed_profile(current_user.subject, db)
    return {"sessions": list_sessions(db, current_user.subject, limit=limit)}


@app.get("/api/me/workout-sessions/{session_id}")
def api_me_get_workout_session(session_id: int, db: Session = Depends(get_db), current_user: AuthenticatedUser = Depends(get_current_user)):
    session = get_session(db, current_user.subject, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Workout session not found")
    return serialize_session(session)


@app.put("/api/me/workout-sessions/{session_id}")
def api_me_update_workout_session(session_id: int, payload: WorkoutSessionUpdatePayload, db: Session = Depends(get_db), current_user: AuthenticatedUser = Depends(get_current_user)):
    require_completed_profile(current_user.subject, db)
    data = payload.model_dump(exclude_none=True)
    if "cardio" in data and data["cardio"] is not None:
        data["cardio"] = {key: value for key, value in data["cardio"].items() if value is not None}
    session = update_session(db, current_user.subject, session_id, data)
    if not session:
        raise HTTPException(status_code=404, detail="Workout session not found")
    return serialize_session(session)


@app.delete("/api/me/workout-sessions/{session_id}")
def api_me_delete_workout_session(session_id: int, db: Session = Depends(get_db), current_user: AuthenticatedUser = Depends(get_current_user)):
    require_completed_profile(current_user.subject, db)
    if not delete_session(db, current_user.subject, session_id):
        raise HTTPException(status_code=404, detail="Workout session not found")
    return {"status": "deleted"}


@app.put("/api/me/food/{food_id}")
def api_me_update_food(food_id: int, payload: FoodUpdatePayload, db: Session = Depends(get_db), current_user: AuthenticatedUser = Depends(get_current_user)):
    food = update_food_log(
        db,
        food_id,
        payload.model_dump(exclude_none=True),
        user_id=current_user.subject,
    )
    if not food:
        raise HTTPException(status_code=404, detail="Food log not found")
    return {"status": "success", "food_id": food.id, "food_name": food.food_name}


@app.delete("/api/me/food/{food_id}")
def api_me_delete_food(food_id: int, db: Session = Depends(get_db), current_user: AuthenticatedUser = Depends(get_current_user)):
    if not delete_food_log(db, food_id, user_id=current_user.subject):
        raise HTTPException(status_code=404, detail="Food log not found")
    return {"status": "success", "message": "Food log deleted"}


@app.get("/api/me/food-captures/{token}")
def api_me_food_capture(token: str, db: Session = Depends(get_db), current_user: AuthenticatedUser = Depends(get_current_user)):
    """Return one authenticated user's editable multi-item food draft."""
    return serialize_capture(get_capture(db, current_user.subject, token))


@app.put("/api/me/food-captures/{token}")
def api_me_update_food_capture(token: str, payload: FoodDraftPayload, db: Session = Depends(get_db), current_user: AuthenticatedUser = Depends(get_current_user)):
    capture = update_capture(db, current_user.subject, token, [item.model_dump(exclude_none=True) for item in payload.items])
    return serialize_capture(capture)


@app.post("/api/me/food-captures/{token}/confirm")
def api_me_confirm_food_capture(token: str, db: Session = Depends(get_db), current_user: AuthenticatedUser = Depends(get_current_user)):
    entries = confirm_capture(db, current_user.subject, token)
    if not entries:
        raise HTTPException(status_code=409, detail="Food capture is expired, cancelled, or already unavailable")
    return {"status": "confirmed", "entry_ids": [entry.id for entry in entries]}


@app.post("/api/me/food-captures/{token}/cancel")
def api_me_cancel_food_capture(token: str, db: Session = Depends(get_db), current_user: AuthenticatedUser = Depends(get_current_user)):
    if not cancel_capture(db, current_user.subject, token):
        raise HTTPException(status_code=409, detail="Food capture is already confirmed or unavailable")
    return {"status": "cancelled"}
