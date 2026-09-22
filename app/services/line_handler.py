"""LINE Messaging API Event Handler & Dispatcher."""
import urllib.parse
import logging
import hashlib
import json
from typing import Dict, Any, Optional

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    TextMessage,
    FlexMessage,
    FlexContainer,
    QuickReply,
    QuickReplyItem,
    URIAction,
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
from app.services.workouts import create_cardio_session, create_strength_session, list_cardio_presets, list_programs
from app.services.ai_vision import analyze_food_image
from app.services.ai_chat import parse_food_text, strip_food_command
from app.services import food_cache
from app.services.food_capture import (
    create_capture,
    serialize_capture,
    ai_quota_remaining,
    confirm_capture_result,
    cancel_capture_result,
)
from app.templates.flex_cards import (
    WEBAPP_PAGES,
    create_food_analyzed_card,
    create_daily_dashboard_card,
    create_webapp_entry_card,
    create_workout_splits_carousel,
    create_workout_logged_card,
    create_welcome_guide_card,
    create_profile_onboarding_card,
    webapp_uri,
)

logger = logging.getLogger(__name__)

WELCOME_INTRO_TEXT = (
    "👋 สวัสดีครับ LINE Cal ช่วยบันทึกอาหารและการออกกำลังกาย\n\n"
    "📸 ส่งรูปอาหาร หรือพิมพ์ เช่น กิน ข้าวมันไก่ + น้ำส้ม\n"
    "📘 พิมพ์ วิธีใช้ เพื่อดูคำสั่งทั้งหมด\n\n"
    "⚠️ ข้อมูลจาก AI เป็นการประเมินเบื้องต้น โปรดตรวจสอบก่อนยืนยัน\n\n"
    "👇 เริ่มจากกรอกโปรไฟล์ด้านล่างก่อนครับ"
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


def reply_webapp(messaging_api: MessagingApi, reply_token: str, tab: str, query: str = "") -> None:
    """Open a Web App page in one tap: the button is the message, not a follow-up to it."""
    card = create_webapp_entry_card(tab, query)
    if not card:
        reply_text(messaging_api, reply_token, "⚙️ ยังเปิดเว็บไม่ได้ กรุณาตั้งค่า LIFF_ID ในระบบก่อนครับ")
        return
    reply_flex(messaging_api, reply_token, WEBAPP_PAGES.get(tab, ("เปิดเว็บแอป",))[0], card)


def reply_today_status(messaging_api: MessagingApi, reply_token: str, text: str) -> None:
    """Keep a status message and the authenticated Today entry point together."""
    uri = webapp_uri("today")
    quick_reply = QuickReply(items=[QuickReplyItem(action=URIAction(label="📅 เปิดวันนี้", uri=uri))]) if uri else None
    reply_text(messaging_api, reply_token, text, quick_reply=quick_reply)


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
        "กรุณาตั้งค่าโปรไฟล์ให้ครบก่อนเริ่มใช้งาน",
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
    cache_text: str | None = None,
) -> None:
    """Shared image/text capture path; only the analyzer differs.

    `cache_text` is set for typed food only. A photo is never the same twice,
    but a typed lunch usually is, and reusing that estimate costs no request
    from the shared daily Gemini allowance.
    """
    if ai_quota_remaining(db, user_id) <= 0:
        reply_text(messaging_api, reply_token, "⏳ วันนี้ใช้โควต้าวิเคราะห์อาหารครบแล้ว ลองใหม่พรุ่งนี้ได้เลยครับ")
        return
    try:
        items = food_cache.lookup(db, cache_text) if cache_text else None
        if items is None:
            result = analyzer()
            items = result.get("items", [result])
            if cache_text:
                food_cache.store(db, cache_text, items)
        capture = create_capture(db, user_id, source, items, source_message_id=source_message_id)
        if not capture.drafts:
            reply_text(messaging_api, reply_token, "🤔 ยังไม่พบรายการอาหารที่วิเคราะห์ได้ ลองพิมพ์รายละเอียดเองอีกครั้งครับ")
            return
        card = create_food_analyzed_card({"items": serialize_capture(capture)["items"]}, capture.token, user_id=user_id)
        reply_flex(messaging_api, reply_token, "ตรวจสอบรายการอาหารก่อนยืนยัน", card)
    except Exception as exc:
        logger.error("Failed to create food capture: %s", exc, exc_info=True)
        reply_text(messaging_api, reply_token, "⚠️ ขออภัยครับ ไม่สามารถวิเคราะห์รายการอาหารได้ กรุณาลองใหม่อีกครั้ง")


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
                # Intro + the one action a new user can actually take.  The full
                # command list lives in the guide card, which "วิธีใช้" and any
                # unrecognized message already deliver on demand; repeating it
                # here only buries the profile step the user is gated behind.
                intro_msg = TextMessage(text=WELCOME_INTRO_TEXT)
                onboard_msg = FlexMessage(
                    alt_text="กรุณาตั้งค่าข้อมูลร่างกายเพื่อเริ่มใช้งาน LINE Cal",
                    contents=FlexContainer.from_dict(create_profile_onboarding_card(user_id)),
                )
                reply_messages(messaging_api, event.reply_token, [intro_msg, onboard_msg])

            elif isinstance(event, MessageEvent):
                if isinstance(event.message, ImageMessageContent):
                    handle_image_message(event, user_id, messaging_api, blob_api, db)
                elif isinstance(event.message, TextMessageContent):
                    handle_text_message(event, user_id, messaging_api, db)

            elif isinstance(event, PostbackEvent):
                handle_postback_event(event, user_id, messaging_api, db)

            # Record only after the handler completed, so a failed handler
            # leaves no marker and a genuine LINE redelivery still runs.
            db.add(ProcessedWebhook(event_id=event_id, user_id=user_id))
            db.commit()

        except Exception as e:
            # Keep going: the webhook is acknowledged before this runs, so a
            # raise here would silently drop every remaining event in the
            # batch with no LINE retry to recover them.
            logger.error(f"Error handling LINE event: {e}", exc_info=True)
            db.rollback()
            continue


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
        reply_text(messaging_api, event.reply_token, "⚠️ ขออภัยครับ ไม่สามารถดาวน์โหลดหรือวิเคราะห์รูปภาพได้ กรุณาลองใหม่อีกครั้ง")


def handle_text_message(event: MessageEvent, user_id: str, messaging_api: MessagingApi, db: Session):
    """Handle the explicit LINE command contract."""
    raw_text = event.message.text.strip()
    text = raw_text.lower()

    # Food text is a capture command, so match it before anything else falls
    # through to the guide.  Photo and text share the same AI-draft review flow.
    if text.startswith("กิน "):
        if not require_completed_profile(db, user_id, messaging_api, event.reply_token):
            return
        _capture_food(
            db, user_id, "text", getattr(event.message, "id", None),
            lambda: parse_food_text(raw_text), messaging_api, event.reply_token,
            cache_text=strip_food_command(raw_text),
        )
        return

    if text in {"โปรไฟล์", "profile"}:
        # Profile is the one page that must remain reachable before onboarding
        # is complete, including when the user has no Rich Menu available.
        reply_webapp(messaging_api, event.reply_token, "profile")
        return

    if text in {"สรุป", "summary"}:
        if not require_completed_profile(db, user_id, messaging_api, event.reply_token):
            return
        reply_flex(messaging_api, event.reply_token, "สรุปยอดแคลอรีและสารอาหารวันนี้", create_daily_dashboard_card(get_daily_summary(db, user_id)))
        return

    if text in {"ประวัติ", "history"}:
        if not require_completed_profile(db, user_id, messaging_api, event.reply_token):
            return
        reply_webapp(messaging_api, event.reply_token, "history")
        return

    if text == "เวท":
        if not require_completed_profile(db, user_id, messaging_api, event.reply_token):
            return
        reply_flex(
            messaging_api,
            event.reply_token,
            "โปรแกรมออกกำลังกายของคุณ",
            create_workout_splits_carousel(
                list_programs(db, user_id),
                user_id=user_id,
                cardio_presets=list_cardio_presets(db, user_id),
            ),
        )
        return

    # Greetings, "วิธีใช้" and typos all want the same answer, so there is no
    # separate branch for them that would only repeat this reply.
    reply_flex(messaging_api, event.reply_token, "วิธีใช้ LINE Cal", create_welcome_guide_card(user_id))


def handle_postback_event(event: PostbackEvent, user_id: str, messaging_api: MessagingApi, db: Session):
    """Handle interactive button clicks from Flex Messages."""
    query_params = dict(urllib.parse.parse_qsl(event.postback.data))
    action = query_params.get("action")

    if action == "log_workout":
        if not require_completed_profile(db, user_id, messaging_api, event.reply_token):
            return
        program_id = query_params.get("program_id")
        try:
            session = log_program_session(
                db,
                user_id,
                int(program_id),
                source_event_id=getattr(event, "webhook_event_id", None),
            )
        except (LookupError, PermissionError, ValueError):
            reply_text(messaging_api, event.reply_token, "❓ ไม่พบโปรแกรมนี้ กรุณาลองใหม่ครับ")
            return
        card = create_workout_logged_card(session.name, session.estimated_calories)
        reply_flex(messaging_api, event.reply_token, "บันทึกการออกกำลังกายสำเร็จ", card)

    elif action == "log_cardio_preset":
        if not require_completed_profile(db, user_id, messaging_api, event.reply_token):
            return
        try:
            session = create_cardio_session(
                db,
                user_id,
                preset_id=int(query_params.get("preset_id") or 0),
                source_event_id=getattr(event, "webhook_event_id", None),
            )
        except (LookupError, PermissionError, ValueError):
            reply_text(messaging_api, event.reply_token, "❓ ไม่พบรายการคาร์ดิโอนี้ กรุณาลองใหม่ครับ")
            return
        card = create_workout_logged_card(session.name, session.estimated_calories)
        reply_flex(messaging_api, event.reply_token, "บันทึกคาร์ดิโอสำเร็จ", card)

    elif action == "confirm_food_capture_chat":
        if not require_completed_profile(db, user_id, messaging_api, event.reply_token):
            return
        token = query_params.get("capture_token", "").strip()
        if not token:
            reply_text(messaging_api, event.reply_token, "❓ ไม่พบรายการอาหารหรือรายการนี้ไม่พร้อมใช้งานแล้วครับ")
            return
        result = confirm_capture_result(db, user_id, token)
        if result.status == "confirmed":
            reply_text(messaging_api, event.reply_token, f"✅ ยืนยันรายการอาหารแล้ว {len(result.entries)} รายการครับ")
        elif result.status == "already_confirmed":
            reply_today_status(
                messaging_api,
                event.reply_token,
                "ℹ️ รายการอาหารนี้ยืนยันไปแล้ว และแก้ไขรายการร่างไม่ได้แล้วครับ หากต้องการแก้ไข ให้เปิดหน้า วันนี้",
            )
        elif result.status == "expired":
            reply_text(messaging_api, event.reply_token, "⏰ รายการอาหารหมดอายุแล้วครับ กรุณาส่งรายการใหม่อีกครั้ง")
        elif result.status == "cancelled":
            reply_text(messaging_api, event.reply_token, "🗑️ รายการอาหารนี้ถูกยกเลิกแล้วครับ")
        else:
            # Owner-scoped lookup intentionally gives the same safe response
            # for missing and cross-user tokens.
            reply_text(messaging_api, event.reply_token, "❓ ไม่พบรายการอาหารหรือรายการนี้ไม่พร้อมใช้งานแล้วครับ")

    elif action == "cancel_food_capture_chat":
        if not require_completed_profile(db, user_id, messaging_api, event.reply_token):
            return
        token = query_params.get("capture_token", "").strip()
        if not token:
            reply_text(messaging_api, event.reply_token, "❓ ไม่พบรายการอาหารหรือรายการนี้ไม่พร้อมใช้งานแล้วครับ")
            return
        result = cancel_capture_result(db, user_id, token)
        if result.status == "cancelled":
            reply_text(messaging_api, event.reply_token, "🗑️ ยกเลิกรายการอาหารแล้วครับ")
        elif result.status == "already_cancelled":
            reply_text(messaging_api, event.reply_token, "🗑️ รายการอาหารนี้ถูกยกเลิกไปแล้วครับ")
        elif result.status == "confirmed":
            reply_today_status(messaging_api, event.reply_token, "ℹ️ รายการอาหารนี้ยืนยันไปแล้ว จึงยกเลิกจากแชทไม่ได้ครับ")
        elif result.status == "expired":
            reply_text(messaging_api, event.reply_token, "⏰ รายการอาหารหมดอายุแล้วครับ จึงยกเลิกไม่ได้")
        else:
            reply_text(messaging_api, event.reply_token, "❓ ไม่พบรายการอาหารหรือรายการนี้ไม่พร้อมใช้งานแล้วครับ")

    else:
        # Retired chat-level food actions and old Rich Menu/Flex cards can
        # outlive a deploy.  Never confirm or cancel a capture from a stale
        # card; acknowledge safely with one canonical entry point instead.
        reply_webapp(messaging_api, event.reply_token, "today")




def log_program_session(
    db: Session,
    user_id: str,
    program_id: int,
    source_event_id: str | None = None,
):
    """One-tap program logging creates an immutable exercise snapshot."""
    return create_strength_session(db, user_id, program_id, source_event_id=source_event_id)
