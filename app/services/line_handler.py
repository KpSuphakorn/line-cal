"""LINE Messaging API Event Handler & Dispatcher."""
import urllib.parse
import logging
import hashlib
import json
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
    FlexContainer,
    QuickReply
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    ImageMessageContent,
    PostbackEvent,
    FollowEvent
)
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import ProcessedWebhook
from app.services.fitness import (
    get_or_create_user,
    get_daily_summary,
    is_user_profile_customized,
)
from app.services.workouts import create_strength_session, list_programs
from app.services.ai_vision import analyze_food_image
from app.services.ai_chat import parse_food_text
from app.services.food_capture import create_capture, serialize_capture, confirm_capture, cancel_capture, ai_quota_remaining
from app.templates.flex_cards import (
    create_food_analyzed_card,
    create_daily_dashboard_card,
    create_workout_splits_carousel,
    create_workout_logged_card,
    create_welcome_guide_card,
    create_history_card,
    create_profile_onboarding_card,
)

logger = logging.getLogger(__name__)

WELCOME_INTRO_TEXT = (
    "💙 สวัสดี! เราชื่อ LINE Cal ผู้ช่วยบันทึกข้อมูลอาหารและคำนวณแคลอรี่อัจฉริยะของคุณ\n\n"
    "🔬 การใช้งาน LINE Cal นี้เป็นส่วนหนึ่งของการวิจัยและพัฒนาเทคโนโลยีปัญญาประดิษฐ์ (AI) ด้านสุขภาพ, อาหารและโภชนาการ\n\n"
    "🙏 ขอขอบพระคุณที่ร่วมเป็นส่วนหนึ่งในการต่อยอดโปรเจกต์นี้ และหากมีข้อผิดพลาดประการใดขออภัยมา ณ ที่นี้ เราพร้อมที่จะปรับปรุง LINE Cal ให้ดียิ่งขึ้น\n\n"
    "💬 คำแนะนำรวมถึงข้อมูลจาก LINE Cal เป็นเพียงข้อมูลและการประเมินเบื้องต้นเท่านั้น"
)

WELCOME_FEATURES_TEXT = (
    "💙💙 น้อง LINE Cal ทำอะไรได้บ้าง 💙💙\n\n"
    "📸 ถ่ายภาพอาหาร:\n"
    "ส่งภาพอาหารที่คุณทานในแต่ละวัน เพื่อรับข้อมูลโภชนาการ แคลอรี่ โปรตีน คาร์บ ไขมัน แล้วแก้ไขก่อนยืนยันได้\n\n"
    "🍲 บันทึกอาหารจากการพิมพ์แชท:\n"
    "พิมพ์ 'กิน' + เว้นวรรค + ชื่อเมนู (เช่น 'กิน ข้าวมันไก่พิเศษ') เพื่อเข้าสู่ flow เดียวกับการถ่ายรูป\n\n"
    "🏋️ ตารางเวท & คาร์ดิโอ:\n"
    "พิมพ์ 'ออกกำลังกาย' หรือ 'โปรแกรม' เพื่อเลือกโปรแกรมของคุณ\n\n"
    "📊 สรุปยอดบาลานซ์วันนี้:\n"
    "พิมพ์ 'สรุป' เพื่อดูงบแคลอรี่คงเหลือและโปรตีนวันนี้\n\n"
    "🎯 ข้อมูลส่วนตัว & เป้าหมาย:\n"
    "เปิด Profile จาก Rich Menu หรือ Web App เพื่อแก้ไขข้อมูลส่วนตัวและเป้าหมาย"
)


def get_line_clients():
    """Initialize LINE API client configuration."""
    configuration = Configuration(access_token=settings.LINE_CHANNEL_ACCESS_TOKEN)
    api_client = ApiClient(configuration)
    messaging_api = MessagingApi(api_client)
    blob_api = MessagingApiBlob(api_client)
    return api_client, messaging_api, blob_api


def reply_flex(messaging_api: MessagingApi, reply_token: str, alt_text: str, flex_dict: Dict[str, Any], quick_reply: Optional[QuickReply] = None):
    """Helper to reply with a LINE Flex Message."""
    container = FlexContainer.from_dict(flex_dict)
    flex_msg = FlexMessage(alt_text=alt_text, contents=container, quick_reply=quick_reply)
    messaging_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[flex_msg]
        )
    )


def reply_text(messaging_api: MessagingApi, reply_token: str, text: str, quick_reply: Optional[QuickReply] = None):
    """Helper to reply with a plain text message."""
    msg = TextMessage(text=text, quick_reply=quick_reply)
    messaging_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[msg]
        )
    )


def reply_messages(messaging_api: MessagingApi, reply_token: str, messages: list):
    """Helper to reply with multiple messages (up to 5) in a single request."""
    messaging_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=messages
        )
    )


def require_completed_profile(db: Session, user_id: str, messaging_api: MessagingApi, reply_token: str) -> bool:
    """Gate all capture/logging actions until the user completes onboarding."""
    user = get_or_create_user(db, user_id, settings)
    if is_user_profile_customized(user):
        return True
    reply_flex(
        messaging_api,
        reply_token,
        "กรุณาตั้งค่าโปรไฟล์ก่อนเริ่มบันทึก",
        create_profile_onboarding_card(user_id),
    )
    return False


def _capture_food(
    db: Session,
    user_id: str,
    source: str,
    source_message_id: str | None,
    analyzer,
    messaging_api: MessagingApi,
    reply_token: str,
) -> None:
    """Shared image/text capture path; only the analyzer differs."""
    if ai_quota_remaining(db, user_id) <= 0:
        reply_text(messaging_api, reply_token, "วันนี้ใช้โควต้าวิเคราะห์อาหารครบแล้ว ลองใหม่พรุ่งนี้ได้เลยครับ")
        return
    try:
        result = analyzer()
        capture = create_capture(db, user_id, source, result.get("items", [result]), source_message_id=source_message_id)
        if not capture.drafts:
            reply_text(messaging_api, reply_token, "ยังไม่พบรายการอาหารที่วิเคราะห์ได้ ลองพิมพ์รายละเอียดเองอีกครั้งครับ")
            return
        card = create_food_analyzed_card({"items": serialize_capture(capture)["items"]}, capture.token, user_id=user_id)
        reply_flex(messaging_api, reply_token, "ตรวจสอบรายการอาหารก่อนยืนยัน", card)
    except Exception as exc:
        logger.error("Failed to create food capture: %s", exc, exc_info=True)
        reply_text(messaging_api, reply_token, "ขออภัยครับ ไม่สามารถวิเคราะห์รายการอาหารได้ กรุณาลองใหม่อีกครั้ง")


def handle_line_events(events: list, db: Session):
    """Process incoming LINE webhook events."""
    api_client, messaging_api, blob_api = get_line_clients()

    for event in events:
        try:
            user_id = event.source.user_id
            event_id = getattr(event, "webhook_event_id", None) or hashlib.sha256(
                json.dumps(event.to_dict() if hasattr(event, "to_dict") else str(event), sort_keys=True, default=str).encode()
            ).hexdigest()
            if db.query(ProcessedWebhook).filter(ProcessedWebhook.event_id == event_id).first():
                logger.info("Skipping duplicate webhook event %s", event_id)
                continue
            user = get_or_create_user(db, user_id, settings)

            if isinstance(event, FollowEvent):
                # 3-step onboarding flow modeled after KinDee:
                # 1. Intro & Research purpose & Disclaimer
                # 2. Features overview
                # 3. Profile onboarding card (canonical Web App Profile tab)
                intro_msg = TextMessage(text=WELCOME_INTRO_TEXT)
                features_msg = TextMessage(text=WELCOME_FEATURES_TEXT)
                onboard_card = create_profile_onboarding_card(user_id)
                onboard_msg = FlexMessage(
                    alt_text="กรุณาตั้งค่าข้อมูลร่างกายเพื่อเริ่มใช้งาน LINE Cal",
                    contents=FlexContainer.from_dict(onboard_card)
                )
                reply_messages(messaging_api, event.reply_token, [intro_msg, features_msg, onboard_msg])

            elif isinstance(event, MessageEvent):
                if isinstance(event.message, ImageMessageContent):
                    handle_image_message(event, user_id, messaging_api, blob_api, db)
                elif isinstance(event.message, TextMessageContent):
                    handle_text_message(event, user_id, messaging_api, db)

            elif isinstance(event, PostbackEvent):
                handle_postback_event(event, user_id, messaging_api, db)

            # Record only after the handler completed.  A failed handler has
            # no marker and therefore remains eligible for LINE redelivery.
            db.add(ProcessedWebhook(event_id=event_id, user_id=user_id))
            db.commit()

        except Exception as e:
            logger.error(f"Error handling LINE event: {e}", exc_info=True)
            db.rollback()
            raise


def handle_image_message(event: MessageEvent, user_id: str, messaging_api: MessagingApi, blob_api: MessagingApiBlob, db: Session):
    """Download food image transiently and use the shared capture flow."""
    if not require_completed_profile(db, user_id, messaging_api, event.reply_token):
        return
    message_id = event.message.id

    try:
        # Download image bytes from LINE
        image_bytes = blob_api.get_message_content(message_id)

        _capture_food(db, user_id, "image", message_id, lambda: analyze_food_image(image_bytes), messaging_api, event.reply_token)

    except Exception as e:
        logger.error(f"Failed to process image: {e}")
        reply_text(messaging_api, event.reply_token, "ขออภัยครับ ไม่สามารถดาวน์โหลดหรือวิเคราะห์รูปภาพได้ กรุณาลองใหม่อีกครั้ง")


def handle_text_message(event: MessageEvent, user_id: str, messaging_api: MessagingApi, db: Session):
    """Handle the explicit LINE command contract."""
    raw_text = event.message.text.strip()
    text = raw_text.lower()
    if any(k in text for k in ["สวัสดี", "หวัดดี", "hello", "hi"]):
        reply_text(messaging_api, event.reply_token, "สวัสดีครับ! พิมพ์ 'กิน [ชื่ออาหาร]' หรือ 'วิธีใช้' เพื่อเริ่มใช้งานได้เลยครับ")
        return

    if any(k in text for k in ["วิธีใช้", "วิธีใช้งาน", "คู่มือ", "สอน", "help"]):
        reply_flex(messaging_api, event.reply_token, "คู่มือการใช้งาน LINE Cal", create_welcome_guide_card(user_id))
        return

    if text.startswith("กิน "):
        if not require_completed_profile(db, user_id, messaging_api, event.reply_token):
            return
        _capture_food(db, user_id, "text", getattr(event.message, "id", None), lambda: parse_food_text(raw_text), messaging_api, event.reply_token)
        return

    if text in {"สรุป", "summary"}:
        if not require_completed_profile(db, user_id, messaging_api, event.reply_token):
            return
        reply_flex(messaging_api, event.reply_token, "สรุปยอดแคลอรีและสารอาหารวันนี้", create_daily_dashboard_card(get_daily_summary(db, user_id)))
        return

    if text in {"ประวัติ", "history"}:
        if not require_completed_profile(db, user_id, messaging_api, event.reply_token):
            return
        reply_flex(messaging_api, event.reply_token, "ประวัติของคุณ", create_history_card())
        return

    if text in {"ออกกำลังกาย", "โปรแกรม", "exercise", "workout"}:
        if not require_completed_profile(db, user_id, messaging_api, event.reply_token):
            return
        reply_flex(messaging_api, event.reply_token, "โปรแกรมออกกำลังกายของคุณ", create_workout_splits_carousel(list_programs(db, user_id), user_id=user_id))
        return

    reply_flex(messaging_api, event.reply_token, "วิธีใช้ LINE Cal", create_welcome_guide_card(user_id))


def handle_postback_event(event: PostbackEvent, user_id: str, messaging_api: MessagingApi, db: Session):
    """Handle interactive button clicks from Flex Messages."""
    query_params = dict(urllib.parse.parse_qsl(event.postback.data))
    action = query_params.get("action")

    if action == "confirm_food_capture":
        if not require_completed_profile(db, user_id, messaging_api, event.reply_token):
            return
        capture_token = query_params.get("capture_token")
        logs = confirm_capture(db, user_id, capture_token or "")
        if not logs:
            reply_text(messaging_api, event.reply_token, "รายการนี้หมดอายุหรือถูกบันทึกไปแล้วครับ")
            return
        summary = get_daily_summary(db, user_id)
        card = create_daily_dashboard_card(summary, last_food_id=logs[-1].id)
        reply_flex(messaging_api, event.reply_token, f"บันทึกอาหาร {len(logs)} รายการเรียบร้อย!", card)

    elif action in {"cancel", "cancel_food_capture"}:
        if query_params.get("capture_token"):
            cancel_capture(db, user_id, query_params["capture_token"])
        reply_text(messaging_api, event.reply_token, "ยกเลิกการบันทึกรายการอาหารเรียบร้อยครับ")

    elif action == "log_workout":
        if not require_completed_profile(db, user_id, messaging_api, event.reply_token):
            return
        program_id = query_params.get("program_id") or query_params.get("split_id")
        try:
            session = log_program_session(
                db,
                user_id,
                int(program_id),
                source_event_id=getattr(event, "webhook_event_id", None),
            )
        except (LookupError, PermissionError, ValueError):
            reply_text(messaging_api, event.reply_token, "ไม่พบโปรแกรมนี้ หรือกรุณาตั้งค่าโปรไฟล์ให้ครบก่อนครับ")
            return
        card = create_workout_logged_card(session.name, session.estimated_calories)
        reply_flex(messaging_api, event.reply_token, "บันทึกการออกกำลังกายสำเร็จ", card)

    elif action == "log_cardio":
        reply_text(messaging_api, event.reply_token, "กรุณาเปิดแบบฟอร์ม Cardio ใน Web App แล้วใส่เวลาที่ทำครับ")

    elif action == "view_dashboard":
        summary = get_daily_summary(db, user_id)
        card = create_daily_dashboard_card(summary)
        reply_flex(messaging_api, event.reply_token, "สรุปยอดวันนี้", card)

    elif action == "view_workouts":
        carousel = create_workout_splits_carousel(list_programs(db, user_id), user_id=user_id)
        reply_flex(messaging_api, event.reply_token, "โปรแกรมออกกำลังกายของคุณ", carousel)

    elif action == "view_history":
        if not require_completed_profile(db, user_id, messaging_api, event.reply_token):
            return
        reply_flex(messaging_api, event.reply_token, "ประวัติของคุณ", create_history_card())

    elif action in ["view_help", "view_guide", "view_main_menu"]:
        guide_card = create_welcome_guide_card(user_id)
        reply_flex(messaging_api, event.reply_token, "คู่มือการใช้งาน LINE Cal", guide_card)



def log_program_session(
    db: Session,
    user_id: str,
    program_id: int,
    source_event_id: str | None = None,
):
    """One-tap program logging creates an immutable exercise snapshot."""
    return create_strength_session(db, user_id, program_id, source_event_id=source_event_id)
