"""LINE Messaging API Event Handler & Dispatcher."""
import urllib.parse
import logging
import hashlib
import json
import math
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
    PostbackAction,
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
from app.db.models import FoodLookup, ProcessedWebhook, User
from app.services.fitness import (
    get_or_create_user,
    get_daily_summary,
    is_user_profile_customized,
)
from app.services.workouts import create_cardio_session, create_strength_session, list_cardio_presets, list_programs
from app.services.ai_errors import ImageTooLargeError
from app.services.ai_vision import analyze_food_image, validate_food_image
from app.services.ai_chat import ITEM_SEPARATOR, parse_food_text, strip_food_command
from app.services import food_cache
from app.services.food_capture import (
    MAX_DRAFT_ITEMS,
    create_capture,
    normalize_food_result,
    serialize_capture,
    ai_quota_remaining,
    confirm_capture_result,
    cancel_capture_result,
    clear_food_refinement,
    select_food_refinement,
    cancel_food_refinement,
    claim_food_refinement,
    reserve_food_refinement_quota,
    release_food_refinement,
    apply_food_refinement,
    selected_food_refinement,
)
from app.templates.flex_cards import (
    WEBAPP_PAGES,
    create_food_analyzed_card,
    create_food_lookup_card,
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


ALLOWANCE_EXHAUSTED_TEXT = "⏳ วันนี้ใช้โควต้าวิเคราะห์อาหารครบแล้ว ลองใหม่พรุ่งนี้ได้เลยครับ"


def _has_complete_nutrition(items, expected_count: int | None = None) -> bool:
    """A lookup may show facts only when every dish has real numeric values."""
    if not isinstance(items, list) or not items or (expected_count is not None and len(items) != expected_count):
        return False

    def valid_number(value) -> bool:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        try:
            return math.isfinite(value) and value >= 0
        except OverflowError:
            return False

    return all(
        isinstance(item, dict)
        and isinstance(item.get("food_name"), str)
        and bool(item["food_name"].strip())
        and all(valid_number(item.get(field)) for field in ("calories", "protein", "carbs", "fat"))
        for item in items
    )


def _estimate_food(
    db: Session,
    user_id: str,
    analyzer,
    cache_text: str | None,
    expected_count: int | None = None,
) -> tuple[list, bool] | None:
    """Items for one description and whether Gemini was called to get them.

    Returns None when the model would be needed but the user's daily allowance
    is spent. The cache is consulted first on purpose: a dish already in it
    costs nothing, so it stays available even after the allowance runs out.
    """
    items = food_cache.lookup(db, cache_text) if cache_text else None
    if items is not None:
        if _has_complete_nutrition(items, expected_count):
            return items, False
        food_cache.delete(db, cache_text)
    if ai_quota_remaining(db, user_id) <= 0:
        return None
    result = analyzer()
    items = result.get("items", [result])
    if cache_text and _has_complete_nutrition(items, expected_count):
        food_cache.store(db, cache_text, items)
    return items, True


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
    try:
        estimate = _estimate_food(db, user_id, analyzer, cache_text)
        if estimate is None:
            reply_text(messaging_api, reply_token, ALLOWANCE_EXHAUSTED_TEXT)
            return
        items, used_ai = estimate
        capture = create_capture(db, user_id, source, items, source_message_id=source_message_id, used_ai=used_ai)
        if not capture.drafts:
            reply_text(messaging_api, reply_token, "🤔 ยังไม่พบรายการอาหารที่วิเคราะห์ได้ ลองพิมพ์รายละเอียดเองอีกครั้งครับ")
            return
        serialized = serialize_capture(capture)
        card = create_food_analyzed_card({"items": serialized["items"]}, capture.token, user_id=user_id,
                                         revision=serialized["revision"], allow_refinement=source == "image")
        reply_flex(messaging_api, reply_token, "ตรวจสอบรายการอาหารก่อนยืนยัน", card)
    except ImageTooLargeError:
        reply_text(messaging_api, reply_token, "🖼️ รูปนี้ใหญ่เกินไปครับ ลองถ่ายใหม่หรือย่อขนาดก่อนส่งอีกครั้ง")
    except Exception as exc:
        logger.error("Failed to create food capture: %s", exc, exc_info=True)
        reply_text(messaging_api, reply_token, "⚠️ ขออภัยครับ ไม่สามารถวิเคราะห์รายการอาหารได้ กรุณาลองใหม่อีกครั้ง")


def _lookup_food(db: Session, user_id: str, dish: str, messaging_api: MessagingApi, reply_token: str) -> None:
    """`ถาม <อาหาร>`: show an estimate without creating anything to confirm.

    Shares the estimate path with `กิน`, including its cache, so looking a dish
    up first makes logging it later free. The only row written is the
    allowance record; nothing reaches the user's food history.
    """
    ai_attempted = False
    usage_recorded = False

    def analyze():
        nonlocal ai_attempted
        ai_attempted = True
        return parse_food_text(f"กิน {dish}")

    def record_ai_use():
        nonlocal usage_recorded
        db.add(FoodLookup(user_id=user_id, used_ai=True))
        db.commit()
        usage_recorded = True

    try:
        expected_count = sum(bool(part.strip()) for part in dish.split(ITEM_SEPARATOR))
        if expected_count == 0:
            reply_text(messaging_api, reply_token, "พิมพ์ ถาม ตามด้วยชื่ออาหาร เช่น ถาม ชาไทย ครับ")
            return
        if expected_count > MAX_DRAFT_ITEMS:
            reply_text(messaging_api, reply_token, f"ถามได้ครั้งละไม่เกิน {MAX_DRAFT_ITEMS} รายการครับ ลองแบ่งถามทีละชุด")
            return
        cached_items = food_cache.lookup(db, dish)
        estimate = (cached_items, False) if _has_complete_nutrition(cached_items, expected_count) else None
        if cached_items is not None and estimate is None:
            food_cache.delete(db, dish)
        if estimate is None and (not settings.GEMINI_API_KEY or "mock" in settings.GEMINI_API_KEY):
            reply_text(messaging_api, reply_token, "⚠️ ตอนนี้ AI ประเมินอาหารไม่ได้ ลองใหม่เมื่อระบบพร้อมครับ")
            return
        if estimate is None:
            estimate = _estimate_food(db, user_id, analyze, dish, expected_count)
        if estimate is None:
            reply_text(messaging_api, reply_token, ALLOWANCE_EXHAUSTED_TEXT)
            return
        items, used_ai = estimate
        if isinstance(items, list) and len(items) != expected_count:
            if used_ai:
                record_ai_use()
            reply_text(messaging_api, reply_token, "🤔 ยังแยกรายการที่คั่นด้วย + ได้ไม่ครบ ลองถามทีละเมนูครับ")
            return
        if not _has_complete_nutrition(items, expected_count):
            if used_ai:
                record_ai_use()
            reply_text(messaging_api, reply_token, "🤔 ยังประเมินข้อมูลโภชนาการของเมนูนี้ไม่ได้ ลองพิมพ์ชื่อหรือปริมาณให้ชัดขึ้นครับ")
            return
        if used_ai:
            record_ai_use()
        items = normalize_food_result({"items": items})
        if not items:
            reply_text(messaging_api, reply_token, "🤔 ยังประเมินเมนูนี้ไม่ได้ ลองพิมพ์ชื่อให้ละเอียดขึ้นอีกนิดครับ")
            return
        reply_flex(messaging_api, reply_token, "แคลอรีโดยประมาณ", create_food_lookup_card({"items": items}))
    except Exception as exc:
        db.rollback()
        if ai_attempted and not usage_recorded:
            try:
                record_ai_use()
            except Exception:
                db.rollback()
                logger.error("Failed to record food lookup AI usage", exc_info=True)
        logger.error("Failed to look up food: %s", exc, exc_info=True)
        reply_text(messaging_api, reply_token, "⚠️ ขออภัยครับ ไม่สามารถประเมินแคลอรีได้ กรุณาลองใหม่อีกครั้ง")


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
                    handle_text_message(event, user_id, messaging_api, db, blob_api)

            elif isinstance(event, PostbackEvent):
                handle_postback_event(event, user_id, messaging_api, db)

            # Record only after the handler completed, so a failed handler
            # leaves no marker and a genuine LINE redelivery still runs.
            owner_still_exists = db.query(User.id).filter(User.id == user_id).with_for_update().first()
            db.add(ProcessedWebhook(event_id=event_id, user_id=user_id if owner_still_exists else None))
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
    clear_food_refinement(db, user_id)
    message_id = event.message.id

    try:
        # Download image bytes from LINE
        image_bytes = blob_api.get_message_content(message_id)

        _capture_food(db, user_id, "image", message_id, lambda: analyze_food_image(image_bytes), messaging_api, event.reply_token)

    except Exception as e:
        logger.error(f"Failed to process image: {e}")
        reply_text(messaging_api, event.reply_token, "⚠️ ขออภัยครับ ไม่สามารถดาวน์โหลดหรือวิเคราะห์รูปภาพได้ กรุณาลองใหม่อีกครั้ง")


def handle_text_message(event: MessageEvent, user_id: str, messaging_api: MessagingApi, db: Session, blob_api=None):
    """Handle the explicit LINE command contract."""
    raw_text = event.message.text.strip()
    text = raw_text.lower()

    # Food text is a capture command, so match it before anything else falls
    # through to the guide.  Photo and text share the same AI-draft review flow.
    if text.startswith("กิน "):
        clear_food_refinement(db, user_id)
        if not require_completed_profile(db, user_id, messaging_api, event.reply_token):
            return
        _capture_food(
            db, user_id, "text", getattr(event.message, "id", None),
            lambda: parse_food_text(raw_text), messaging_api, event.reply_token,
            cache_text=strip_food_command(raw_text),
        )
        return

    if text.startswith("ถาม "):
        clear_food_refinement(db, user_id)
        _lookup_food(db, user_id, raw_text[len("ถาม "):].strip(), messaging_api, event.reply_token)
        return

    if text in {"โปรไฟล์", "profile"}:
        clear_food_refinement(db, user_id)
        # Profile is the one page that must remain reachable before onboarding
        # is complete, including when the user has no Rich Menu available.
        reply_webapp(messaging_api, event.reply_token, "profile")
        return

    if text in {"สรุป", "summary"}:
        clear_food_refinement(db, user_id)
        if not require_completed_profile(db, user_id, messaging_api, event.reply_token):
            return
        reply_flex(messaging_api, event.reply_token, "สรุปยอดแคลอรีและสารอาหารวันนี้", create_daily_dashboard_card(get_daily_summary(db, user_id)))
        return

    if text in {"ประวัติ", "history"}:
        clear_food_refinement(db, user_id)
        if not require_completed_profile(db, user_id, messaging_api, event.reply_token):
            return
        reply_webapp(messaging_api, event.reply_token, "history")
        return

    if text == "เวท":
        clear_food_refinement(db, user_id)
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

    if text in {"ยกเลิกการปรับ", "ยกเลิกปรับ"}:
        state, capture = selected_food_refinement(db, user_id)
        if state == "selected":
            status = cancel_food_refinement(db, user_id, capture.token, int((capture.ai_metadata or {}).get("revision", 0)), (capture.ai_metadata or {}).get("refine_context_id"))
            status = "ยกเลิกโหมดปรับรายการแล้วครับ รายการอาหารเดิมยังอยู่เหมือนเดิม" if status == "cancelled" else "ℹ️ รายการนี้เปลี่ยนไปแล้ว จึงยกเลิกโหมดปรับไม่ได้ครับ"
        else:
            status = "ℹ️ ไม่มีรายการที่กำลังรอการปรับแล้วครับ"
        reply_text(messaging_api, event.reply_token, status)
        return

    if text in {"ออกกำลังกาย", "โปรแกรม", "exercise", "workout", "วิธีใช้", "วิธีใช้งาน", "help", "ช่วย", "สวัสดี"}:
        clear_food_refinement(db, user_id)
    else:
        event_id = getattr(event, "webhook_event_id", None) or hashlib.sha256(
            json.dumps(event.to_dict() if hasattr(event, "to_dict") else str(event), sort_keys=True, default=str).encode()
        ).hexdigest()
        outcome = handle_food_refinement_text(event, user_id, raw_text, event_id, messaging_api, db, blob_api)
        if outcome:
            return

    # Greetings, help and typos outside refinement mode use the command guide.
    reply_flex(messaging_api, event.reply_token, "วิธีใช้ LINE Cal", create_welcome_guide_card(user_id))


def handle_food_refinement_text(event, user_id: str, instruction: str, event_id: str, messaging_api, db: Session, blob_api) -> bool:
    state, claim = claim_food_refinement(db, user_id, instruction, event_id)
    if state == "none":
        return False
    if state == "expired":
        reply_text(messaging_api, event.reply_token, "หมดเวลาปรับรายการแล้วครับ กด ‘ปรับด้วย AI’ บนการ์ดอีกครั้งได้เลย")
        return True
    if state == "completed":
        capture = claim["capture"]
        card = create_food_analyzed_card({"items": capture["items"]}, capture["token"], revision=claim["revision"], allow_refinement=True)
        db.commit()
        reply_flex(messaging_api, event.reply_token, "ผลปรับรายการอาหาร", card)
        return True
    if state == "processing":
        reply_text(messaging_api, event.reply_token, "กำลังปรับรายการนี้อยู่ครับ รอสักครู่แล้วค่อยส่งข้อความใหม่")
        return True
    if state == "consumed":
        reply_text(messaging_api, event.reply_token, "คำขอนี้ทำงานไปแล้วครับ หากยังต้องการปรับ ให้กด ‘ปรับด้วย AI’ อีกครั้งแล้วส่งข้อความใหม่")
        return True
    if state == "invalid":
        reply_text(messaging_api, event.reply_token, "พิมพ์สิ่งที่ต้องการปรับไม่เกิน 500 ตัวอักษรครับ")
        return True
    if state != "claimed":
        reply_text(messaging_api, event.reply_token, "ไม่พบรายการรูปที่กำลังปรับแล้วครับ กด ‘ปรับด้วย AI’ บนการ์ดอีกครั้ง")
        return True

    token, attempt_id = claim["token"], claim["attempt_id"]
    try:
        if not settings.GEMINI_API_KEY or "mock" in settings.GEMINI_API_KEY:
            release_food_refinement(db, user_id, token, attempt_id)
            reply_text(messaging_api, event.reply_token, "ตอนนี้ AI ยังไม่พร้อมครับ รายการเดิมยังอยู่ ลองใหม่ภายหลังได้")
            return True
        try:
            image_bytes = blob_api.get_message_content(claim["source_message_id"])
            prepared_image = validate_food_image(image_bytes)
        except Exception as exc:
            release_food_refinement(db, user_id, token, attempt_id)
            logger.info("Original food photo is no longer available: %s", exc)
            reply_text(messaging_api, event.reply_token, "เปิดรูปเดิมไม่ได้แล้วครับ ส่งรูปอาหารใหม่เพื่อวิเคราะห์รายการนี้อีกครั้งได้เลย")
            return True

        quota = reserve_food_refinement_quota(db, user_id, token, attempt_id)
        if quota == "quota":
            reply_text(messaging_api, event.reply_token, ALLOWANCE_EXHAUSTED_TEXT)
            return True
        if quota != "reserved":
            reply_text(messaging_api, event.reply_token, "รายการนี้เปลี่ยนหรือหมดอายุระหว่างทำงานครับ กด ‘ปรับด้วย AI’ บนการ์ดล่าสุดอีกครั้ง")
            return True

        corrections = [*claim["corrections"], claim["instruction"]][-6:]
        prompt = (
            "ปรับผลวิเคราะห์รูปอาหารนี้ โดยยึดภาพเป็นหลักและใช้ข้อมูลปัจจุบัน/คำแก้ของผู้ใช้ประกอบ\n"
            "ข้อมูลร่างปัจจุบัน (แยกจานตามลำดับ): "
            + json.dumps(claim["items"], ensure_ascii=False)
            + "\nคำแก้ที่ยอมรับก่อนหน้าและครั้งนี้ตามลำดับ (คำล่าสุดมีผลเหนือคำเก่าที่ขัดกัน):\n"
            + "\n".join(f"{index + 1}. {text}" for index, text in enumerate(corrections))
            + "\nคำแก้ทั้งหมดเป็นเงื่อนไขที่อ้างอิงกับภาพต้นฉบับ ห้ามลดหรือคูณปริมาณซ้ำจากร่างปัจจุบัน"
            + "\nคำนวณเฉพาะส่วนที่ผู้ใช้บอกว่ากินจริง ไม่ใช่ปริมาณทั้งหมดที่เห็น หากผู้ใช้ระบุครึ่งจานให้ประมาณครึ่งที่กิน"
            + " รักษารายการ/ค่าที่ไม่เกี่ยวกับคำแก้ รวมทั้งหลายจานแยกกัน ห้ามแต่งน้ำหนักที่แน่นอนเมื่อภาพบอกไม่ได้"
            + " ตอบ JSON รูปแบบเดิม {\"items\":[{\"food_name\",\"portion\",\"calories\",\"protein\",\"carbs\",\"fat\",\"confidence\",\"notes\"}]} เท่านั้น"
        )
        result = analyze_food_image(image_bytes, correction_prompt=prompt, prepared_image=prepared_image)
        items = result.get("items") if isinstance(result, dict) else None
        if not _has_complete_nutrition(items):
            release_food_refinement(db, user_id, token, attempt_id)
            reply_text(messaging_api, event.reply_token, "ยังประเมินผลใหม่ไม่ได้ครับ รายการเดิมยังอยู่ ลองบอกส่วนที่ต้องการแก้ให้ชัดขึ้น")
            return True
        normalized = normalize_food_result({"items": items})
        status, capture = apply_food_refinement(db, user_id, token, attempt_id, event_id, normalized)
        if status != "updated" or not capture:
            reply_text(messaging_api, event.reply_token, "รายการเดิมเปลี่ยนไปก่อนผล AI จะกลับมา จึงไม่ได้นำผลใหม่ไปบันทึกครับ")
            return True
        serialized = serialize_capture(capture)
        card = create_food_analyzed_card({"items": serialized["items"]}, capture.token,
                                         revision=serialized["revision"], allow_refinement=True)
        db.commit()
        reply_flex(messaging_api, event.reply_token, "ตรวจผลปรับอาหารก่อนยืนยัน", card)
    except Exception as exc:
        db.rollback()
        release_food_refinement(db, user_id, token, attempt_id)
        logger.error("Food photo refinement failed: %s", exc, exc_info=True)
        reply_text(messaging_api, event.reply_token, "ปรับรายการไม่สำเร็จครับ รายการเดิมยังอยู่ ลองส่งคำแก้อีกครั้งได้")
    return True


def _postback_revision(query_params: dict[str, str]) -> int:
    try:
        return int(query_params.get("revision", "0"))
    except (TypeError, ValueError):
        return -1


def _reply_capture_card(db: Session, capture, messaging_api, reply_token: str) -> None:
    serialized = serialize_capture(capture)
    card = create_food_analyzed_card(
        {"items": serialized["items"]}, capture.token, revision=serialized["revision"],
        allow_refinement=capture.source == "image",
    )
    db.commit()
    reply_flex(messaging_api, reply_token, "รายการอาหารล่าสุด", card)


def _reply_capture_snapshot(db: Session, capture: dict, messaging_api, reply_token: str) -> None:
    card = create_food_analyzed_card(
        {"items": capture["items"]}, capture["token"], revision=capture["revision"],
        allow_refinement=capture["source"] == "image",
    )
    db.commit()
    reply_flex(messaging_api, reply_token, "รายการอาหารล่าสุด", card)


def _reply_current_capture(db: Session, user_id: str, token: str, messaging_api, reply_token: str) -> bool:
    from app.db.models import FoodCapture
    capture = db.query(FoodCapture).filter(FoodCapture.user_id == user_id, FoodCapture.token == token).populate_existing().first()
    if not capture or capture.status != "draft":
        db.commit()
        return False
    _reply_capture_card(db, capture, messaging_api, reply_token)
    return True


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
        revision = _postback_revision(query_params)
        if not token:
            reply_text(messaging_api, event.reply_token, "❓ ไม่พบรายการอาหารหรือรายการนี้ไม่พร้อมใช้งานแล้วครับ")
            return
        result = confirm_capture_result(db, user_id, token, revision)
        if result.status == "confirmed":
            reply_text(messaging_api, event.reply_token, f"✅ ยืนยันรายการอาหารแล้ว {len(result.entries)} รายการครับ")
        elif result.status == "already_confirmed":
            reply_today_status(
                messaging_api,
                event.reply_token,
                "ℹ️ รายการอาหารนี้ยืนยันไปแล้ว และแก้ไขรายการร่างไม่ได้แล้วครับ หากต้องการแก้ไข ให้เปิดหน้า วันนี้",
            )
        elif result.status == "stale":
            if not _reply_current_capture(db, user_id, token, messaging_api, event.reply_token):
                reply_text(messaging_api, event.reply_token, "รายการนี้เปลี่ยนหรือยืนยันไปแล้วครับ กรุณาเปิดหน้า วันนี้เพื่อตรวจสอบ")
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
        revision = _postback_revision(query_params)
        if not token:
            reply_text(messaging_api, event.reply_token, "❓ ไม่พบรายการอาหารหรือรายการนี้ไม่พร้อมใช้งานแล้วครับ")
            return
        result = cancel_capture_result(db, user_id, token, revision)
        if result.status == "cancelled":
            reply_text(messaging_api, event.reply_token, "🗑️ ยกเลิกรายการอาหารแล้วครับ")
        elif result.status == "already_cancelled":
            reply_text(messaging_api, event.reply_token, "🗑️ รายการอาหารนี้ถูกยกเลิกไปแล้วครับ")
        elif result.status == "confirmed":
            reply_today_status(messaging_api, event.reply_token, "ℹ️ รายการอาหารนี้ยืนยันไปแล้ว จึงยกเลิกจากแชทไม่ได้ครับ")
        elif result.status == "expired":
            reply_text(messaging_api, event.reply_token, "⏰ รายการอาหารหมดอายุแล้วครับ จึงยกเลิกไม่ได้")
        elif result.status == "stale":
            if not _reply_current_capture(db, user_id, token, messaging_api, event.reply_token):
                reply_text(messaging_api, event.reply_token, "รายการนี้เปลี่ยนไปแล้วครับ กรุณาเปิดหน้า วันนี้เพื่อตรวจสอบ")
        else:
            reply_text(messaging_api, event.reply_token, "❓ ไม่พบรายการอาหารหรือรายการนี้ไม่พร้อมใช้งานแล้วครับ")

    elif action == "refine_food_capture_chat":
        if not require_completed_profile(db, user_id, messaging_api, event.reply_token):
            return
        token = query_params.get("capture_token", "").strip()
        revision = _postback_revision(query_params)
        if not token:
            reply_text(messaging_api, event.reply_token, "ไม่พบรายการรูปที่ต้องการปรับแล้วครับ")
            return
        status, capture = select_food_refinement(db, user_id, token, revision)
        if status == "selected" and capture:
            context_id = capture.get("refine_context_id", "")
            quick = QuickReply(items=[QuickReplyItem(action=PostbackAction(
                label="ยกเลิกการปรับ",
                data=f"action=cancel_food_refinement_chat&capture_token={urllib.parse.quote(token, safe='')}&revision={revision}&context_id={context_id}",
                display_text="ยกเลิกการปรับ",
            ))])
            reply_text(messaging_api, event.reply_token, "พิมพ์สิ่งที่ต้องการแก้จากรูปนี้ได้เลยครับ เช่น ‘กินแค่ครึ่งจาน’ ไม่ต้องพิมพ์คำว่าแก้ (รอได้ 10 นาที)", quick_reply=quick)
        elif status == "stale" and capture and capture["status"] == "draft":
            _reply_capture_snapshot(db, capture, messaging_api, event.reply_token)
        elif status == "not_image":
            reply_text(messaging_api, event.reply_token, "ปรับด้วย AI ได้เฉพาะรายการที่มาจากรูปครับ")
        else:
            reply_text(messaging_api, event.reply_token, "รายการรูปนี้ยืนยัน ยกเลิก หรือหมดอายุแล้วครับ ส่งรูปใหม่เพื่อวิเคราะห์ได้เลย")

    elif action == "cancel_food_refinement_chat":
        if not require_completed_profile(db, user_id, messaging_api, event.reply_token):
            return
        token = query_params.get("capture_token", "").strip()
        context_id = query_params.get("context_id", "").strip()
        if not token or not context_id:
            reply_text(messaging_api, event.reply_token, "ปุ่มยกเลิกนี้หมดอายุแล้วครับ")
            return
        result = cancel_food_refinement(db, user_id, token, _postback_revision(query_params), context_id)
        if result == "cancelled":
            reply_text(messaging_api, event.reply_token, "ยกเลิกโหมดปรับรายการแล้วครับ รายการอาหารเดิมยังอยู่เหมือนเดิม")
        else:
            reply_text(messaging_api, event.reply_token, "ปุ่มยกเลิกนี้หมดอายุแล้วครับ รายการอาหารเดิมยังอยู่เหมือนเดิม")

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
