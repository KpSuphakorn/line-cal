"""LINE Messaging API Event Handler & Dispatcher."""
import uuid
import urllib.parse
import logging
from typing import Dict, Any, Optional

from linebot.v3 import WebhookParser
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    TextMessage,
    FlexMessage,
    FlexContainer
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    ImageMessageContent,
    PostbackEvent
)
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import FoodLog, WorkoutLog
from app.services.fitness import (
    get_or_create_user,
    get_daily_summary,
    get_weekly_stats,
    get_past_food_history,
    calculate_incline_walk_burn
)
from app.services.ai_vision import analyze_food_image
from app.data.presets import WORKOUT_SPLITS, QUICK_SNACKS
from app.templates.flex_cards import (
    create_food_analyzed_card,
    create_daily_dashboard_card,
    create_workout_splits_carousel,
    create_quick_snacks_card,
    create_workout_logged_card,
    create_weekly_stats_card,
    create_food_history_card
)

logger = logging.getLogger(__name__)

# Temporary cache for food scans awaiting user confirmation: temp_id -> food_data
PENDING_FOOD_SCANS: Dict[str, Dict[str, Any]] = {}


def get_line_clients():
    """Initialize LINE API client configuration."""
    configuration = Configuration(access_token=settings.LINE_CHANNEL_ACCESS_TOKEN)
    api_client = ApiClient(configuration)
    messaging_api = MessagingApi(api_client)
    blob_api = MessagingApiBlob(api_client)
    return api_client, messaging_api, blob_api


def reply_flex(messaging_api: MessagingApi, reply_token: str, alt_text: str, flex_dict: Dict[str, Any]):
    """Helper to reply with a LINE Flex Message."""
    container = FlexContainer.from_dict(flex_dict)
    flex_msg = FlexMessage(alt_text=alt_text, contents=container)
    messaging_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[flex_msg]
        )
    )


def reply_text(messaging_api: MessagingApi, reply_token: str, text: str):
    """Helper to reply with a plain text message."""
    messaging_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[TextMessage(text=text)]
        )
    )


def handle_line_events(events: list, db: Session):
    """Process incoming LINE webhook events."""
    api_client, messaging_api, blob_api = get_line_clients()

    for event in events:
        try:
            user_id = event.source.user_id
            user = get_or_create_user(db, user_id, settings)

            if isinstance(event, MessageEvent):
                if isinstance(event.message, ImageMessageContent):
                    handle_image_message(event, user_id, messaging_api, blob_api, db)
                elif isinstance(event.message, TextMessageContent):
                    handle_text_message(event, user_id, messaging_api, db)

            elif isinstance(event, PostbackEvent):
                handle_postback_event(event, user_id, messaging_api, db)

        except Exception as e:
            logger.error(f"Error handling LINE event: {e}", exc_info=True)


def handle_image_message(event: MessageEvent, user_id: str, messaging_api: MessagingApi, blob_api: MessagingApiBlob, db: Session):
    """Download food image, run Gemini AI analysis, and return Flex card."""
    message_id = event.message.id

    try:
        # Download image bytes from LINE
        image_bytes = blob_api.get_message_content(message_id)

        # Call Gemini Multimodal AI
        food_data = analyze_food_image(image_bytes)

        # Store in pending cache
        temp_id = str(uuid.uuid4())[:8]
        PENDING_FOOD_SCANS[temp_id] = {
            "user_id": user_id,
            **food_data
        }

        # Send interactive confirmation card
        flex_card = create_food_analyzed_card(food_data, temp_id)
        reply_flex(messaging_api, event.reply_token, f"AI วิเคราะห์: {food_data['food_name']}", flex_card)

    except Exception as e:
        logger.error(f"Failed to process image: {e}")
        reply_text(messaging_api, event.reply_token, "ขออภัยครับ ไม่สามารถดาวน์โหลดหรือวิเคราะห์รูปภาพได้ กรุณาลองใหม่อีกครั้ง")


def handle_text_message(event: MessageEvent, user_id: str, messaging_api: MessagingApi, db: Session):
    """Handle text commands and natural language shortcuts."""
    text = event.message.text.strip().lower()

    # 0. Yesterday's Balance
    if "เมื่อวาน" in text:
        from datetime import datetime, timedelta
        yesterday = datetime.now().date() - timedelta(days=1)
        summary = get_daily_summary(db, user_id, target_date=yesterday)
        card = create_daily_dashboard_card(summary)
        reply_flex(messaging_api, event.reply_token, f"สรุปยอดเมื่อวาน ({summary['date_display']})", card)
        return

    # 0.1 Weekly Stats (สถิติ 7 วัน)
    if any(k in text for k in ["สถิติ", "week", "สัปดาห์"]):
        stats = get_weekly_stats(db, user_id, days=7)
        card = create_weekly_stats_card(stats)
        reply_flex(messaging_api, event.reply_token, "สถิติภาพรวม 7 วัน", card)
        return

    # 0.2 Food History
    if any(k in text for k in ["ประวัติ", "history"]):
        history = get_past_food_history(db, user_id, limit=8)
        card = create_food_history_card(history)
        reply_flex(messaging_api, event.reply_token, "ประวัติรายการอาหารล่าสุด", card)
        return

    # 1. Daily Dashboard / Balance Summary
    if any(k in text for k in ["สรุป", "ยอด", "balance", "dashboard", "แคล", "วันนี้"]):
        summary = get_daily_summary(db, user_id)
        card = create_daily_dashboard_card(summary)
        reply_flex(messaging_api, event.reply_token, "สรุปยอดแคลอรีและสารอาหารวันนี้", card)
        return

    # 2. Workout Split Menu
    if any(k in text for k in ["เวท", "ตาราง", "workout", "ออกกำลังกาย"]):
        carousel = create_workout_splits_carousel()
        reply_flex(messaging_api, event.reply_token, "ตารางออกกำลังกายประจำสัปดาห์ 4 วัน", carousel)
        return

    # 3. Quick Snacks & Drinks Menu
    if any(k in text for k in ["ขนม", "ของว่าง", "มัจฉะ", "snack"]):
        card = create_quick_snacks_card()
        reply_flex(messaging_api, event.reply_token, "เมนูบันทึกของว่าง & มัจฉะทันใจ", card)
        return

    # 4. Direct Shortcuts for Snacks
    if "กล้วย" in text:
        log_snack_by_id(db, user_id, "banana")
        summary = get_daily_summary(db, user_id)
        reply_text(messaging_api, event.reply_token, f"🍌 บันทึก 'กล้วยหอม 1 ลูก' (+105 kcal) เรียบร้อยครับ! วันนี้เหลือโควตา {int(summary['remaining_kcal'])} kcal")
        return

    if "นม" in text and "มัจฉะ" not in text:
        log_snack_by_id(db, user_id, "milk")
        summary = get_daily_summary(db, user_id)
        reply_text(messaging_api, event.reply_token, f"🥛 บันทึก 'นมจืด 1 กล่อง' (+130 kcal, P:8g) เรียบร้อยครับ! วันนี้เหลือโควตา {int(summary['remaining_kcal'])} kcal")
        return

    if "มัจฉะมะพร้าว" in text:
        log_snack_by_id(db, user_id, "matcha_coconut")
        summary = get_daily_summary(db, user_id)
        reply_text(messaging_api, event.reply_token, f"🥥 บันทึก 'มัจฉะน้ำมะพร้าว' (+70 kcal) เรียบร้อยครับ! วันนี้เหลือโควตา {int(summary['remaining_kcal'])} kcal")
        return

    if "มัจฉะ" in text:
        log_snack_by_id(db, user_id, "matcha_latte_cow")
        summary = get_daily_summary(db, user_id)
        reply_text(messaging_api, event.reply_token, f"🍵 บันทึก 'มัจฉะลาเต้นมวัว 0%' (+130 kcal, P:8g) เรียบร้อยครับ! วันนี้เหลือโควตา {int(summary['remaining_kcal'])} kcal")
        return

    if "ถั่ว" in text:
        log_snack_by_id(db, user_id, "mixed_nuts")
        summary = get_daily_summary(db, user_id)
        reply_text(messaging_api, event.reply_token, f"🥜 บันทึก 'ถั่วรวม 30g' (+175 kcal, ไขมันดี 15g) เรียบร้อยครับ! วันนี้เหลือโควตา {int(summary['remaining_kcal'])} kcal")
        return

    # 5. Direct Shortcuts for Workouts
    if "day 1" in text or "push" in text:
        card = log_workout_by_id(db, user_id, "day_1")
        reply_flex(messaging_api, event.reply_token, "บันทึก Day 1: Push แล้ว", card)
        return

    if "day 2" in text or "pull" in text:
        card = log_workout_by_id(db, user_id, "day_2")
        reply_flex(messaging_api, event.reply_token, "บันทึก Day 2: Pull แล้ว", card)
        return

    if "day 3" in text or "lower" in text or "ขา" in text:
        card = log_workout_by_id(db, user_id, "day_3")
        reply_flex(messaging_api, event.reply_token, "บันทึก Day 3: Lower & Core แล้ว", card)
        return

    if "day 4" in text or "upper" in text:
        card = log_workout_by_id(db, user_id, "day_4")
        reply_flex(messaging_api, event.reply_token, "บันทึก Day 4: Upper แล้ว", card)
        return

    if "เดินชัน" in text:
        duration = 40
        if "50" in text:
            duration = 50
        elif "60" in text:
            duration = 60
        burn = calculate_incline_walk_burn(72.0, duration)
        card = log_cardio_entry(db, user_id, duration, burn)
        reply_flex(messaging_api, event.reply_token, f"บันทึกเดินชัน {duration} นาที", card)
        return

    # Default Help Message
    help_text = (
        "👋 สวัสดีครับ คุณศุภกร! พร้อมดูแลสุขภาพและฟิตเนสวันนี้\n\n"
        "คำสั่งที่ใช้งานได้:\n"
        "📸 ส่งรูปอาหาร เพื่อให้ AI วิเคราะห์แคลอรีและสารอาหาร\n"
        "📊 พิมพ์ 'สรุป' หรือ 'แคล' เพื่อดูแดชบอร์ดพลังงานวันนี้\n"
        "🏋️ พิมพ์ 'เวท' หรือ 'ตาราง' เพื่อดูและบันทึกเวท 4 วัน\n"
        "🏃 พิมพ์ 'เดินชัน 40' / '50' / '60' เพื่อบันทึกคาร์ดิโอ\n"
        "⚡ พิมพ์ 'กล้วย', 'นม', 'มัจฉะ', 'ถั่ว' เพื่อบันทึกของว่างทันที"
    )
    reply_text(messaging_api, event.reply_token, help_text)


def handle_postback_event(event: PostbackEvent, user_id: str, messaging_api: MessagingApi, db: Session):
    """Handle interactive button clicks from Flex Messages."""
    query_params = dict(urllib.parse.parse_qsl(event.postback.data))
    action = query_params.get("action")

    if action == "confirm_food":
        temp_id = query_params.get("temp_id")
        food_data = PENDING_FOOD_SCANS.pop(temp_id, None)

        if not food_data:
            reply_text(messaging_api, event.reply_token, "รายการนี้หมดอายุหรือถูกบันทึกไปแล้วครับ")
            return

        new_food = FoodLog(
            user_id=user_id,
            meal_type="meal",
            food_name=food_data["food_name"],
            portion=food_data["portion"],
            calories=food_data["calories"],
            protein=food_data["protein"],
            carbs=food_data["carbs"],
            fat=food_data["fat"]
        )
        db.add(new_food)
        db.commit()

        summary = get_daily_summary(db, user_id)
        card = create_daily_dashboard_card(summary)
        reply_flex(messaging_api, event.reply_token, f"บันทึก {food_data['food_name']} เรียบร้อย!", card)

    elif action == "cancel":
        reply_text(messaging_api, event.reply_token, "ยกเลิกการบันทึกรายการอาหารเรียบร้อยครับ")

    elif action == "log_workout":
        split_id = query_params.get("split_id")
        card = log_workout_by_id(db, user_id, split_id)
        reply_flex(messaging_api, event.reply_token, "บันทึกการออกกำลังกายสำเร็จ", card)

    elif action == "log_cardio":
        duration = int(query_params.get("duration", 40))
        burn = float(query_params.get("burn", 280))
        card = log_cardio_entry(db, user_id, duration, burn)
        reply_flex(messaging_api, event.reply_token, f"บันทึกเดินชัน {duration} นาที", card)

    elif action == "quick_snack":
        snack_id = query_params.get("snack_id")
        snack = log_snack_by_id(db, user_id, snack_id)
        if snack:
            summary = get_daily_summary(db, user_id)
            card = create_daily_dashboard_card(summary)
            reply_flex(messaging_api, event.reply_token, f"บันทึก {snack['title']} สำเร็จ", card)

    elif action == "view_dashboard":
        summary = get_daily_summary(db, user_id)
        card = create_daily_dashboard_card(summary)
        reply_flex(messaging_api, event.reply_token, "สรุปยอดวันนี้", card)

    elif action == "view_workouts":
        carousel = create_workout_splits_carousel()
        reply_flex(messaging_api, event.reply_token, "ตารางออกกำลังกาย 4 วัน", carousel)

    elif action == "view_weekly_stats":
        stats = get_weekly_stats(db, user_id, days=7)
        card = create_weekly_stats_card(stats)
        reply_flex(messaging_api, event.reply_token, "สถิติภาพรวม 7 วัน", card)

    elif action == "view_history":
        history = get_past_food_history(db, user_id, limit=8)
        card = create_food_history_card(history)
        reply_flex(messaging_api, event.reply_token, "ประวัติรายการอาหารล่าสุด", card)

    elif action == "view_snacks":
        card = create_quick_snacks_card()
        reply_flex(messaging_api, event.reply_token, "Quick Snacks & Drinks", card)


def log_snack_by_id(db: Session, user_id: str, snack_id: str) -> Optional[Dict[str, Any]]:
    """Helper to record a quick snack to database."""
    snack = next((s for s in QUICK_SNACKS if s["id"] == snack_id), None)
    if not snack:
        return None

    new_food = FoodLog(
        user_id=user_id,
        meal_type="snack",
        food_name=snack["title"],
        portion=snack["subtitle"],
        calories=snack["calories"],
        protein=snack["protein"],
        carbs=snack["carbs"],
        fat=snack["fat"]
    )
    db.add(new_food)
    db.commit()
    return snack


def log_workout_by_id(db: Session, user_id: str, split_id: str) -> Dict[str, Any]:
    """Helper to record a 4-day split workout to database."""
    split = WORKOUT_SPLITS.get(split_id, WORKOUT_SPLITS["day_1"])
    burn = split["estimated_burn_kcal"]

    new_workout = WorkoutLog(
        user_id=user_id,
        workout_type="weights",
        routine_name=split["name"],
        duration_min=60,
        calories_burned=burn,
        details=", ".join([ex["name"] for ex in split["exercises"]])
    )
    db.add(new_workout)
    db.commit()

    summary = get_daily_summary(db, user_id)
    return create_workout_logged_card(split["name"], burn, summary["remaining_kcal"])


def log_cardio_entry(db: Session, user_id: str, duration_min: int, burn_kcal: float) -> Dict[str, Any]:
    """Helper to record cardio incline walk to database."""
    title = f"เดินชัน {duration_min} นาที (Incline 10-12%)"
    new_workout = WorkoutLog(
        user_id=user_id,
        workout_type="cardio",
        routine_name=title,
        duration_min=duration_min,
        calories_burned=burn_kcal
    )
    db.add(new_workout)
    db.commit()

    summary = get_daily_summary(db, user_id)
    return create_workout_logged_card(title, burn_kcal, summary["remaining_kcal"])
