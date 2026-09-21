"""Small, canonical LINE Flex cards used by the chat interface."""
from typing import Any, Dict
import urllib.parse

from app.config import settings


def webapp_uri(tab: str = "today", query: str = "") -> str:
    """Build a LINE deep link without putting a user identifier in the URL.

    Production cards must enter the Web App through LIFF so LINE can establish
    the authenticated browser session.  The direct endpoint remains a small
    local-development fallback for tests and non-production environments.
    """
    params = [("tab", tab)]
    if query:
        params.extend(urllib.parse.parse_qsl(query, keep_blank_values=True))
    query_string = urllib.parse.urlencode(params)

    liff_id = (settings.LIFF_ID or "").strip()
    if liff_id:
        return f"https://liff.line.me/{urllib.parse.quote(liff_id, safe='')}/?{query_string}"

    if settings.APP_ENV.lower() in {"production", "prod"}:
        return ""
    if not settings.WEBAPP_BASE_URL:
        return ""
    base = settings.WEBAPP_BASE_URL.rstrip("?")
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{query_string}"


def _button(label: str, action: Dict[str, Any], style: str = "secondary") -> Dict[str, Any]:
    return {"type": "button", "style": style, "height": "sm", "action": {**action, "label": label}}


def _uri_button(label: str, tab: str, style: str = "secondary") -> Dict[str, Any] | None:
    uri = webapp_uri(tab)
    return _button(label, {"type": "uri", "uri": uri}, style) if uri else None


def _bubble(title: str, body: list[Dict[str, Any]], footer: list[Dict[str, Any]] | None = None, color: str = "#0F172A") -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "type": "bubble",
        "size": "mega",
        "header": {"type": "box", "layout": "vertical", "backgroundColor": color, "paddingAll": "16px", "contents": [{"type": "text", "text": title, "size": "lg", "weight": "bold", "color": "#FFFFFF", "wrap": True}]},
        "body": {"type": "box", "layout": "vertical", "paddingAll": "16px", "spacing": "sm", "contents": body},
    }
    if footer:
        result["footer"] = {"type": "box", "layout": "vertical", "spacing": "sm", "paddingAll": "12px", "contents": footer}
    return result


def create_food_analyzed_card(food_data: Dict[str, Any], capture_token: str, user_id: str = "") -> Dict[str, Any]:
    items = food_data.get("items") if isinstance(food_data, dict) else None
    if not isinstance(items, list):
        items = [food_data]
    items = [item for item in items if isinstance(item, dict)] or [{"food_name": "อาหารที่ตรวจพบ"}]
    total = sum(float(item.get("calories") or 0) for item in items)
    rows = []
    for item in items[:8]:
        rows.append({"type": "box", "layout": "vertical", "backgroundColor": "#F8FAFC", "cornerRadius": "8px", "paddingAll": "10px", "contents": [
            {"type": "text", "text": str(item.get("food_name") or "อาหารที่ตรวจพบ"), "weight": "bold", "size": "sm", "color": "#0F172A", "wrap": True},
            {"type": "text", "text": f"{item.get('portion') or '1 ที่'} • {float(item.get('calories') or 0):.0f} kcal", "size": "xs", "color": "#475569", "margin": "xs"},
            {"type": "text", "text": f"P {float(item.get('protein') or 0):.1f}g  C {float(item.get('carbs') or 0):.1f}g  F {float(item.get('fat') or 0):.1f}g", "size": "xxs", "color": "#64748B"},
        ]})
    footer = []
    edit_url = webapp_uri("today", f"capture_token={urllib.parse.quote(capture_token)}")
    footer.append(_button(
        "✅ ยืนยันทั้งหมด",
        {
            "type": "postback",
            "data": f"action=confirm_food_capture_chat&capture_token={urllib.parse.quote(capture_token, safe='')}",
            "displayText": "ยืนยันรายการอาหาร",
        },
        "primary",
    ))
    if edit_url:
        footer.append(_button("✏️ แก้ไขรายการ", {"type": "uri", "uri": edit_url}, "link"))
    return _bubble(f"🥗 AI วิเคราะห์ {len(items)} รายการ", [{"type": "text", "text": f"รวมประมาณ {total:.0f} kcal • ตรวจสอบและแก้ไขก่อนยืนยัน", "size": "sm", "color": "#475569"}, *rows], footer, "#059669")


def create_text_food_card(food_data: Dict[str, Any], capture_token: str, user_id: str = "") -> Dict[str, Any]:
    return create_food_analyzed_card(food_data, capture_token, user_id=user_id)


def create_daily_dashboard_card(summary: Dict[str, Any], last_food_id: int | None = None) -> Dict[str, Any]:
    target = int(summary.get("food_target", summary.get("target_kcal", 0)))
    eaten = int(summary.get("food_consumed", summary.get("calories_in", 0)))
    burned = int(summary.get("exercise_estimate", summary.get("calories_burned", 0)))
    rows = [{"type": "text", "text": f"🍽️ อาหาร {eaten} / {target} kcal", "size": "sm", "color": "#334155"}, {"type": "text", "text": f"🏃 ออกกำลังประมาณ {burned} kcal", "size": "sm", "color": "#166534"}, {"type": "text", "text": f"🧮 สุทธิข้อมูล {eaten - burned} kcal", "size": "sm", "color": "#1E40AF"}, {"type": "separator"}, {"type": "text", "text": f"โปรตีน {int(summary.get('protein', 0))}/{int(summary.get('target_protein', 0))}g • คาร์บ {int(summary.get('carbs', 0))}g • ไขมัน {int(summary.get('fat', 0))}g", "size": "xs", "color": "#475569", "wrap": True}]
    for food in summary.get("food_logs", [])[:5]:
        rows.append({"type": "text", "text": f"• {food.get('time', '')} {food.get('name', '')} — {int(food.get('calories', 0))} kcal", "size": "xs", "color": "#374151", "wrap": True})
    footer = [button for button in (_uri_button("วันนี้", "today"), _uri_button("ออกกำลังกาย", "programs"), _uri_button("ประวัติ", "history")) if button]
    return _bubble(f"📊 สรุปวันนี้ {summary.get('date_display', '')}", rows, footer)


def create_workout_splits_carousel(
    programs: Any = None,
    user_id: str = "",
    cardio_presets: Any = None,
) -> Dict[str, Any]:
    """Render user-owned strength programs and reusable cardio presets."""
    if isinstance(programs, dict):
        programs = list(programs.values())
    if isinstance(cardio_presets, dict):
        cardio_presets = list(cardio_presets.values())
    programs = list(programs or [])
    cardio_presets = list(cardio_presets or [])
    manage_uri = webapp_uri("programs")
    max_contents = 12
    available = max_contents - (1 if manage_uri else 0)
    # Keep cardio presets visible when the user has many strength programs.
    selected_presets = cardio_presets[:available]
    selected_programs = programs[:max(0, available - len(selected_presets))]
    bubbles = []
    for program in selected_programs:
        rows = [{"type": "text", "text": f"• {exercise.get('name', '')} — {exercise.get('sets', 0)} เซ็ต × {exercise.get('repetitions', 0)} ครั้ง", "size": "xs", "color": "#334155", "wrap": True} for exercise in (program.get("exercises") or [])[:8]]
        if not rows:
            rows = [{"type": "text", "text": "ยังไม่มีท่าในโปรแกรมนี้", "size": "xs", "color": "#64748B"}]
        footer = [_button("บันทึกวันนี้", {"type": "postback", "data": f"action=log_workout&program_id={program.get('id')}"}, "primary")]
        edit_button = _uri_button("แก้ไขในเว็บ", "programs")
        if edit_button:
            footer.append(edit_button)
        bubbles.append(_bubble(program.get("name", "โปรแกรม"), rows, footer, "#1E3A8A"))
    for preset in selected_presets:
        activity = preset.get("custom_name") or preset.get("activity") or "คาร์ดิโอ"
        details = [f"{preset.get('duration_min', 0)} นาที"]
        if preset.get("incline_pct") is not None:
            details.append(f"ชัน {preset['incline_pct']}%")
        if preset.get("speed_kmh") is not None:
            details.append(f"{preset['speed_kmh']} กม./ชม.")
        if preset.get("distance_km") is not None:
            details.append(f"{preset['distance_km']} กม.")
        rows = [
            {"type": "text", "text": activity, "size": "md", "weight": "bold", "color": "#047857", "wrap": True},
            {"type": "text", "text": " • ".join(details), "size": "sm", "color": "#475569", "wrap": True},
        ]
        footer = [_button("บันทึกวันนี้", {"type": "postback", "data": f"action=log_cardio_preset&preset_id={preset.get('id')}"}, "primary")]
        edit_uri = webapp_uri("programs")
        if edit_uri:
            footer.append(_button("แก้ไขในเว็บ", {"type": "uri", "uri": edit_uri}))
        bubbles.append(_bubble(str(preset.get("name") or activity), rows, footer, "#047857"))
    if manage_uri:
        bubbles.append(_bubble("คาร์ดิโอ", [{"type": "text", "text": "สร้าง แก้ไข หรือลบรายการคาร์ดิโอของคุณ", "size": "sm", "color": "#475569", "wrap": True}], [_button("จัดการรายการคาร์ดิโอ", {"type": "uri", "uri": manage_uri}, "primary")], "#047857"))
    return {"type": "carousel", "contents": bubbles[:12]}


def create_workout_logged_card(title: str, burned_kcal: float, remaining_kcal: float = 0) -> Dict[str, Any]:
    footer = [button for button in (_uri_button("เปิดวันนี้", "today"),) if button]
    return _bubble("บันทึกวันนี้แล้ว", [{"type": "text", "text": title, "size": "lg", "weight": "bold", "color": "#1E3A8A"}, {"type": "text", "text": f"พลังงานโดยประมาณ {int(burned_kcal)} kcal", "size": "sm", "color": "#166534"}], footer, "#059669")


def create_welcome_guide_card(user_id: str = "") -> Dict[str, Any]:
    rows = [{"type": "text", "text": "ส่งรูปอาหาร หรือพิมพ์ กิน ตามด้วยชื่อเมนู เช่น กิน ข้าวมันไก่พิเศษ", "size": "sm", "color": "#334155", "wrap": True}, {"type": "text", "text": "พิมพ์ สรุป เพื่อดูข้อมูลวันนี้", "size": "sm", "color": "#334155"}, {"type": "text", "text": "พิมพ์ ออกกำลังกาย หรือ โปรแกรม เพื่อเลือกโปรแกรมและรายการคาร์ดิโอ", "size": "sm", "color": "#334155", "wrap": True}, {"type": "text", "text": "พิมพ์ ประวัติ เพื่อดูสถิติย้อนหลัง", "size": "sm", "color": "#334155"}]
    footer = [button for button in (_uri_button("วันนี้", "today"), _uri_button("ออกกำลังกาย", "programs"), _uri_button("ประวัติ", "history")) if button]
    return _bubble("วิธีใช้ LINE Cal", rows, footer)


def create_profile_onboarding_card(user_id: str = "") -> Dict[str, Any]:
    footer = [button for button in (_uri_button("เปิดโปรไฟล์", "profile", "primary"),) if button]
    return _bubble("กรอกโปรไฟล์ก่อนเริ่มใช้งาน", [{"type": "text", "text": "กรอกข้อมูลร่างกายและเป้าหมาย เพื่อคำนวณเป้าหมายอาหารและเริ่มบันทึกข้อมูล", "size": "sm", "color": "#334155", "wrap": True}], footer, "#7C2D12")


def create_profile_summary_card(profile: Dict[str, Any], user_id: str = "") -> Dict[str, Any]:
    footer = [button for button in (_uri_button("แก้ไขโปรไฟล์", "profile", "primary"),) if button]
    return _bubble("โปรไฟล์", [{"type": "text", "text": str(profile.get("name") or "ผู้ใช้งาน"), "size": "lg", "weight": "bold", "color": "#1E293B"}, {"type": "text", "text": f"เป้าอาหาร {int(profile.get('daily_target_kcal') or 0)} kcal • โปรตีน {int(profile.get('target_protein_g') or 0)}g", "size": "sm", "color": "#475569"}], footer)
