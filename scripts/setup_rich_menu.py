"""Generate and upload an official LINE Rich Menu directly to the bot."""
import io
import sys
from PIL import Image, ImageDraw, ImageFont
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    MessagingApiBlob,
    RichMenuRequest,
    RichMenuSize,
    RichMenuArea,
    RichMenuBounds,
    MessageAction,
    URIAction,
    PostbackAction
)
from app.config import settings


def generate_rich_menu_image() -> bytes:
    """Generate a clean, high-resolution 2500x1686 Rich Menu 6-tile image."""
    width = 2500
    height = 1686
    img = Image.new("RGB", (width, height), color="#0F172A")
    draw = ImageDraw.Draw(img)

    # 6 Tiles layout (3 columns x 2 rows)
    # Cell dimensions: width = 833.3, height = 843
    col_w = width // 3
    row_h = height // 2

    tiles = [
        # Row 1
        {"title": "📸 ถ่ายรูปอาหาร", "sub": "เปิดกล้องสแกนแคล", "bg": "#064E3B", "border": "#10B981"},
        {"title": "📊 สรุปยอดวันนี้", "sub": "ดูโควตา & Balance", "bg": "#1E3A8A", "border": "#3B82F6"},
        {"title": "🏋️‍♂️ ตารางเวท 4 วัน", "sub": "Push / Pull / Lower / Upper", "bg": "#4C1D95", "border": "#8B5CF6"},
        # Row 2
        {"title": "🏃 เดินชัน Cardio", "sub": "40 / 50 / 60 นาที", "bg": "#14532D", "border": "#22C55E"},
        {"title": "⚡ Quick Snacks", "sub": "กล้วย นม มัจฉะ ถั่ว", "bg": "#78350F", "border": "#F59E0B"},
        {"title": "✏️ แก้ไขน้ำหนัก", "sub": "ปรับเปลี่ยนน้ำหนักที่เล่น", "bg": "#334155", "border": "#94A3B8"},
    ]

    # Try to load a font or fallback to default
    try:
        font_title = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", 68)
        font_sub = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", 42)
    except Exception:
        try:
            font_title = ImageFont.truetype("Arial.ttf", 68)
            font_sub = ImageFont.truetype("Arial.ttf", 42)
        except Exception:
            font_title = ImageFont.load_default()
            font_sub = ImageFont.load_default()

    for idx, tile in enumerate(tiles):
        col = idx % 3
        row = idx // 3
        x1 = col * col_w
        y1 = row * row_h
        x2 = (col + 1) * col_w if col < 2 else width
        y2 = (row + 1) * row_h if row < 1 else height

        # Draw box background with margin
        margin = 12
        draw.rounded_rectangle(
            [x1 + margin, y1 + margin, x2 - margin, y2 - margin],
            radius=30,
            fill=tile["bg"],
            outline=tile["border"],
            width=6
        )

        # Center text inside cell
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2

        # Draw title
        draw.text((cx, cy - 35), tile["title"], fill="#FFFFFF", font=font_title, anchor="mm")
        # Draw subtitle
        draw.text((cx, cy + 45), tile["sub"], fill="#E2E8F0", font=font_sub, anchor="mm")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def setup_rich_menu():
    """Register Rich Menu with LINE API and set as default."""
    print("Connecting to LINE API...")
    config = Configuration(access_token=settings.LINE_CHANNEL_ACCESS_TOKEN)
    api_client = ApiClient(config)
    messaging_api = MessagingApi(api_client)
    blob_api = MessagingApiBlob(api_client)

    width = 2500
    height = 1686
    col_w = width // 3
    row_h = height // 2

    # Define the 6 clickable areas
    areas = [
        # Tile 1: Camera (Opens native LINE camera!)
        RichMenuArea(
            bounds=RichMenuBounds(x=0, y=0, width=col_w, height=row_h),
            action=URIAction(uri="https://line.me/R/nv/camera/")
        ),
        # Tile 2: Dashboard
        RichMenuArea(
            bounds=RichMenuBounds(x=col_w, y=0, width=col_w, height=row_h),
            action=MessageAction(text="สรุป")
        ),
        # Tile 3: Workouts
        RichMenuArea(
            bounds=RichMenuBounds(x=col_w * 2, y=0, width=width - (col_w * 2), height=row_h),
            action=MessageAction(text="เวท")
        ),
        # Tile 4: Incline Walk
        RichMenuArea(
            bounds=RichMenuBounds(x=0, y=row_h, width=col_w, height=row_h),
            action=MessageAction(text="เดินชัน 40")
        ),
        # Tile 5: Quick Snacks
        RichMenuArea(
            bounds=RichMenuBounds(x=col_w, y=row_h, width=col_w, height=row_h),
            action=MessageAction(text="ของว่าง")
        ),
        # Tile 6: Edit Weight
        RichMenuArea(
            bounds=RichMenuBounds(x=col_w * 2, y=row_h, width=width - (col_w * 2), height=row_h),
            action=MessageAction(text="แก้น้ำหนัก")
        ),
    ]

    rich_menu_request = RichMenuRequest(
        size=RichMenuSize(width=width, height=height),
        selected=True,
        name="Main Navigation Menu",
        chat_bar_text="เมนูลัด (Menu)",
        areas=areas
    )

    print("Creating Rich Menu...")
    res = messaging_api.create_rich_menu(rich_menu_request)
    rich_menu_id = res.rich_menu_id
    print(f"Rich Menu created: {rich_menu_id}")

    print("Generating and uploading Rich Menu graphic image...")
    image_bytes = generate_rich_menu_image()
    blob_api.set_rich_menu_image(
        rich_menu_id=rich_menu_id,
        body=image_bytes,
        _headers={"Content-Type": "image/png"}
    )
    print("Image uploaded successfully.")

    print("Setting as default Rich Menu for all users...")
    messaging_api.set_default_rich_menu(rich_menu_id)
    print("SUCCESS: Rich Menu is now live on your LINE Bot!")


if __name__ == "__main__":
    setup_rich_menu()
