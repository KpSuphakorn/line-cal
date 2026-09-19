import os
import logging
from pathlib import Path
from typing import Dict, List, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Header, HTTPException, Depends, UploadFile, File
from fastapi.responses import JSONResponse, PlainTextResponse, HTMLResponse
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import init_db, get_db
from app.services.line_handler import handle_line_events
from app.services.fitness import get_daily_summary, get_or_create_user, get_user_splits, save_all_user_exercises
from app.services.ai_vision import analyze_food_image
from app.templates.flex_cards import create_food_analyzed_card, create_daily_dashboard_card

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
    description="Personalized Calorie Counting, Workout Tracking, and TDEE Sync for Suphakorn",
    version="1.0.0",
    lifespan=lifespan
)

# LINE Webhook Parser
parser = WebhookParser(settings.LINE_CHANNEL_SECRET)


@app.get("/")
def root():
    return {
        "status": "online",
        "app": "LINE Calorie & Fitness Companion",
        "version": "1.0.0",
        "user": "Suphakorn (Male, 22y, 174cm, 72kg)",
        "daily_target_kcal": settings.USER_DEFAULT_DAILY_TARGET_KCAL,
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
    file: UploadFile = File(...)
):
    """
    Test endpoint: Upload any food image to test Gemini Vision AI
    without needing a live LINE webhook. Returns JSON and Flex Message preview.
    """
    contents = await file.read()
    food_data = analyze_food_image(contents)
    flex_preview = create_food_analyzed_card(food_data, "test_id_123")

    return {
        "analysis": food_data,
        "flex_preview": flex_preview
    }


@app.get("/api/summary/{user_id}")
def get_user_summary(user_id: str, db: Session = Depends(get_db)):
    """Retrieve daily nutrition and workout balance for a user."""
    get_or_create_user(db, user_id, settings)
    summary = get_daily_summary(db, user_id)
    return summary


@app.get("/api/preview/dashboard/{user_id}")
def preview_dashboard(user_id: str, db: Session = Depends(get_db)):
    """Preview the exact LINE Flex Message JSON generated for today's dashboard."""
    get_or_create_user(db, user_id, settings)
    summary = get_daily_summary(db, user_id)
    return create_daily_dashboard_card(summary)


@app.get("/workout-editor", response_class=HTMLResponse)
def workout_editor_page():
    """Serve the modern interactive Workout Routine & Weight Editor Web App (LIFF)."""
    html_path = Path(__file__).parent / "templates" / "workout_editor.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Workout Editor Template Not Found</h1>", status_code=404)


@app.get("/api/user/{user_id}/exercises")
def api_get_user_exercises(user_id: str, db: Session = Depends(get_db)):
    """API endpoint to get user workout splits and exercises."""
    get_or_create_user(db, user_id, settings)
    return get_user_splits(db, user_id)


@app.post("/api/user/{user_id}/exercises/save")
async def api_save_user_exercises(user_id: str, payload: Dict[str, List[Dict[str, Any]]], db: Session = Depends(get_db)):
    """API endpoint to bulk save customized exercises and weights for all splits."""
    get_or_create_user(db, user_id, settings)
    save_all_user_exercises(db, user_id, payload)
    return {"status": "success", "message": "Workout splits updated successfully"}

