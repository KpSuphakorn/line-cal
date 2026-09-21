<div align="center">

# 🥗 LINE Calorie & Fitness Companion
### AI-Powered Vision Food Logging & Comprehensive Workout Tracker via LINE

[![CI Test Suite](https://github.com/KpSuphakorn/line-cal/actions/workflows/ci.yml/badge.svg)](https://github.com/KpSuphakorn/line-cal/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)
![Google Gemini](https://img.shields.io/badge/Gemini_AI-Multimodal_Vision-8E75B2?logo=google&logoColor=white)
![LINE API](https://img.shields.io/badge/LINE-Messaging_API_v3-00C300?logo=line&logoColor=white)
![Database](https://img.shields.io/badge/Database-PostgreSQL_%2F_Supabase-336791?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-pytest-blue)

<p align="center">
  A multi-user LINE assistant built with <b>FastAPI</b>, <b>Google Gemini</b>, and <b>LINE Messaging API</b>. Food capture and workout programs are editable from the LIFF Web App.
</p>

</div>

---

## 📖 Overview (ภาพรวมโปรเจกต์)

**LINE Calorie & Fitness Companion** ถูกพัฒนาขึ้นเพื่อแก้ปัญหาความยุ่งยากในการนับแคลอรีและการบันทึกการออกกำลังกายในชีวิตประจำวัน โดยรวมทุกอย่างไว้ในแอป **LINE** ที่เปิดใช้งานอยู่ตลอดเวลา:
- **📸 ถ่ายรูปอาหารนับแคลด้วย AI**: ส่งรูปอาหารเข้าแชต $\rightarrow$ Gemini Multimodal วิเคราะห์สัดส่วนอาหาร, ประมาณการแคลอรี และแยกสารอาหารหลัก (Protein, Carbs, Fat) ส่งกลับเป็นการ์ด Interactive Flex Message ทันที
- **🎯 คำนวณพลังงานอัจฉริยะ (BMR / TDEE & Recomposition)**: คำนวณตามสูตร Mifflin-St Jeor ปรับโควตาแคลอรีและเป้าหมายโปรตีนอัตโนมัติตามสัดส่วนร่างกาย
- **🏋️‍♂️ โปรแกรมออกกำลังส่วนตัว**: ระบบคัดลอก template Push, Pull และ Legs ให้ผู้ใช้แต่ละคนแก้ไขชื่อท่า เซ็ต ครั้ง น้ำหนัก และหมายเหตุได้แยกกัน
- **📖 ประวัติย้อนหลัง**: ดูปฏิทินรายเดือน รายการอาหาร และ Workout Sessions พร้อมแก้ไขย้อนหลังได้ใน LIFF Web App

---

## 🏗️ System Architecture (สถาปัตยกรรมระบบ)

```mermaid
flowchart TD
    User([LINE App User]) -->|Photo / Text Commands / Postback Buttons| LineGateway[LINE Messaging API Gateway]
    LineGateway -->|Secure Webhook with HMAC-SHA256 Signature| FastAPIServer[Backend: FastAPI Service]

    subgraph Core Logic Engines
        FastAPIServer --> AICalEngine[AI Vision Engine\nGemini 2.0 / 1.5 Flash]
        FastAPIServer --> FitnessEngine[BMR / TDEE & METs Energy Calculator]
        FastAPIServer --> FlexGenerator[LINE Flex Message Card Generator]
    end

    subgraph Data & Storage Layer
        FastAPIServer --> ORM[SQLAlchemy ORM + Connection Pooling]
        ORM --> DB[(PostgreSQL / Supabase or SQLite)]
        DB --> UsersTable[Users & Body Metrics]
        DB --> FoodTable[Food Logs & Macros]
        DB --> WorkoutTable[Workout & Cardio Logs]
    end

    FlexGenerator -->|Interactive JSON Bubbles & Carousels| LineGateway
    LineGateway -->|Instant Rich Cards UI| User
```

---

## 🚀 Key Engineering Highlights (จุดเด่นทางวิศวกรรม)

- **Clean Architecture & Modularity**: แยกโครงสร้างเป็นสัดส่วนชัดเจน (`app/services`, `app/templates`, `app/db`, `app/data`)
- **12-Factor App & Security**: แยกการตั้งค่าความลับทั้งหมดออกจากโค้ดผ่าน Pydantic V2 Settings และ `.env` โดยเด็ดขาด
- **Cloud Database Ready**: รองรับ **Supabase (PostgreSQL)** พร้อม Connection Pooling (`pool_size`, `max_overflow`, `pool_pre_ping`) และ fallback SQLite สำหรับ Local Development
- **Robust Multimodal AI Pipeline**: สกัดผลลัพธ์จาก Gemini Vision ออกมาเป็น Strict JSON Schema พร้อม Error Handling และ Fallback Mock สำหรับ Local Offline Testing
- **Automated tests**: มีชุดทดสอบสูตรคำนวณ, Flex Message และ REST API; รันด้วย `pytest -v` ใน CI
- **Containerized**: มาพร้อม `Dockerfile` (Multi-stage build) และ `docker-compose.yml` พร้อม Deploy ได้ทุก Cloud Provider (Render, Railway, Fly.io, AWS, VPS)

---

## 🏋️ Workout programs

หลัง onboarding ระบบจะคัดลอก template Push, Pull และ Legs เป็นโปรแกรมของผู้ใช้แต่ละคน โปรแกรมไม่ผูกกับวันในสัปดาห์ และแก้ไขได้จาก Web App; Cardio อยู่ใน entry point เดียวกับโปรแกรมเวท

---

## 💬 Command Cheatsheet (คำสั่งใช้งานใน LINE)

| คำสั่ง | ผลลัพธ์ |
|---|---|
| 📸 **ส่งรูปภาพอาหาร** | AI วิเคราะห์ชื่ออาหาร, แคลอรี, โปรตีน/คาร์บ/ไขมัน พร้อมการ์ดกดยืนยันบันทึก |
| `สรุป` | ดูสรุปอาหารและการออกกำลังกายวันนี้ |
| `กิน <รายการอาหาร>` | ให้ AI เสนอรายการอาหารเพื่อแก้ไขและยืนยันก่อนบันทึก |
| `เวท` | เลือกโปรแกรมเวทหรือ Cardio |
| `ประวัติ` | เปิดปฏิทินและรายละเอียดรายการย้อนหลังใน LIFF Web App |
| `วิธีใช้` | ดูคำสั่งที่รองรับ |

การตั้งค่า Profile ทำในแท็บ Profile ของ LIFF Web App และต้องกรอกให้ครบก่อนบันทึกข้อมูล

---

## 🛠️ Quick Start (วิธีติดตั้งและเริ่มรัน)

### 1. Clone Repository & Setup Virtual Environment
```bash
git clone https://github.com/KpSuphakorn/line-cal.git
cd line-cal

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables
คัดลอกไฟล์ `.env.example` เป็น `.env`:
```bash
cp .env.example .env
```
กำหนดค่าคีย์ของคุณใน `.env`:
```ini
LINE_CHANNEL_SECRET=your_line_channel_secret
LINE_CHANNEL_ACCESS_TOKEN=your_line_channel_access_token
GEMINI_API_KEY=your_gemini_api_key

# ฐานข้อมูล: เลือกใช้ Local SQLite หรือ Supabase PostgreSQL
DATABASE_URL=sqlite:///./line_cal.db
# หรือ Supabase (production runtime):
# DATABASE_URL=postgresql://postgres.xxxx:your_password@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres
# ใช้ Direct connection (หรือ Session pooler 5432) สำหรับ Alembic migrations;
# อย่าใช้ Transaction pooler 6543 ใน migration
# Production also requires APP_ENV=production, LINE_LOGIN_CHANNEL_ID, LIFF_ID,
# WEBAPP_BASE_URL, and GEMINI_API_KEY. Apply `alembic upgrade head` before starting the service.
```

### 3. Run Locally
```bash
uvicorn app.main:app --reload --port 8000
```
- Interactive API Docs (Swagger): `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/health`

### 4. Run with Docker
```bash
docker-compose up --build
```

### 5. Running Tests
```bash
pytest -v
```

---

## 📁 Project Structure

```text
line-cal/
├── .github/
│   └── workflows/
│       └── ci.yml             # GitHub Actions CI Workflow
├── app/
│   ├── data/
│   │   └── presets.py         # System Push/Pull/Legs program templates
│   ├── db/
│   │   ├── database.py        # SQLAlchemy engine & Supabase connection pool
│   │   └── models.py          # Relational ORM models (food captures, programs, sessions)
│   ├── services/
│   │   ├── ai_vision.py       # Gemini Multimodal AI vision analysis
│   │   ├── fitness.py         # BMR, TDEE and daily/monthly summaries
│   │   └── line_handler.py    # LINE Webhook event dispatcher & supported commands
│   ├── templates/
│   │   └── flex_cards.py      # Canonical LINE Flex Message cards
│   ├── config.py              # Pydantic Settings
│   └── main.py                # FastAPI entrypoint & simulation endpoints
├── tests/
│   ├── test_api.py            # API endpoint integration tests
│   ├── test_fitness.py        # Exercise & nutrition calculations unit tests
│   └── test_flex_cards.py     # LINE Flex Container schema verification
├── Dockerfile                 # Multi-stage containerization
├── docker-compose.yml         # Container orchestration
├── requirements.txt           # Python dependencies
└── README.md
```

---

## 📄 License
This project is licensed under the [MIT License](LICENSE).
