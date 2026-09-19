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
![Tests](https://img.shields.io/badge/Tests-16%20Passed%20(100%25)-brightgreen)

<p align="center">
  A production-grade, life-synchronized AI Chatbot built with <b>FastAPI</b>, <b>Google Gemini 2.0 Flash</b>, and <b>LINE Messaging API</b>. Designed to count food calories from photos, compute dynamic <b>BMR/TDEE energy balances</b>, and track weekly workout routines in real time.
</p>

</div>

---

## 📖 Overview (ภาพรวมโปรเจกต์)

**LINE Calorie & Fitness Companion** ถูกพัฒนาขึ้นเพื่อแก้ปัญหาความยุ่งยากในการนับแคลอรีและการบันทึกการออกกำลังกายในชีวิตประจำวัน โดยรวมทุกอย่างไว้ในแอป **LINE** ที่เปิดใช้งานอยู่ตลอดเวลา:
- **📸 ถ่ายรูปอาหารนับแคลด้วย AI**: ส่งรูปอาหารเข้าแชต $\rightarrow$ Gemini Multimodal วิเคราะห์สัดส่วนอาหาร, ประมาณการแคลอรี และแยกสารอาหารหลัก (Protein, Carbs, Fat) ส่งกลับเป็นการ์ด Interactive Flex Message ทันที
- **🎯 คำนวณพลังงานอัจฉริยะ (BMR / TDEE & Recomposition)**: คำนวณตามสูตร Mifflin-St Jeor ปรับโควตาแคลอรีและเป้าหมายโปรตีนอัตโนมัติตามสัดส่วนร่างกาย
- **🏋️‍♂️ เชื่อมโยงตารางเวทเทรนนิ่ง 4 วัน + เดินชัน**: มีระบบ Checklist บันทึกเวท Day 1-4 (Push, Pull, Lower, Upper) และคำนวณแคลอรีที่เบิร์นตามน้ำหนักตัวจริง นำไปบวกเพิ่มเป็นโควตาอาหารในวันนั้น
- **⚡ Quick-Log Shortcuts**: ปุ่มลัดแตะครั้งเดียวสำหรับอาหารประจำวัน (กล้วย Pre-workout, นม, มัจฉะลาเต้หวาน 0%, มัจฉะมะพร้าว, ถั่วไขมันดี)
- **📈 Historical Statistics & Analytics**: ดูสรุปยอดวันนี้, ย้อนดูของเมื่อวาน, ดึงสถิติความสม่ำเสมอ 7 วัน และประวัติมื้ออาหารย้อนหลัง

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
- **100% Automated Test Coverage**: มีชุดทดสอบครอบคลุมทั้งสูตรคำนวณสรีรวิทยา, Schemas ของ Flex Message, และ REST API endpoints ทั้งหมด **16/16 Passed**
- **Containerized**: มาพร้อม `Dockerfile` (Multi-stage build) และ `docker-compose.yml` พร้อม Deploy ได้ทุก Cloud Provider (Render, Railway, Fly.io, AWS, VPS)

---

## 🏋️ Preset Workout & Nutrition Engine

ระบบถูกปรับแต่ง (Calibrated) ให้สอดคล้องกับสรีระและไลฟ์สไตล์การสร้างกล้ามเนื้อลดไขมัน (Body Recomposition):
- **สัดส่วนร่างกายฐาน**: ชาย | อายุ 22 ปี | สูง 174 ซม. | หนัก 72 กก.
- **BMR**: `1,700 kcal` | **TDEE เฉลี่ย**: `2,400 - 2,550 kcal/วัน`
- **Daily Target**: `1,950 kcal/วัน` (Slight Deficit เพื่อดึงไขมันมาใช้)
- **โปรตีนเป้าหมาย**: `145 g/วัน` (~2.0g ต่อน้ำหนักตัว 1 กก.)

### ตารางเวทเทรนนิ่ง 4 วัน (4-Day Push/Pull/Lower/Upper Split):
| Routine | รายการท่าหลัก | แคลอรีเผาผลาญโดยประมาณ |
|---|---|---|
| **Day 1: Push** | Pec dec fly (40kg), Flat bench (20kg), Incline bench (20kg), Lower chest fly (15kg), Lateral raises (4kg), Triceps (7.5kg) | ~300 kcal |
| **Day 2: Pull** | Lat pull down (35kg), T-bar/Barbell row (17.5kg), One arm row (12kg), Seated row (40kg), Lat pullover (10kg), Biceps (30kg) | ~300 kcal |
| **Day 3: Lower & Core** | Hip adductors (40kg), Legs curl (60kg), Hack squat, Legs press (80kg), Legs extension (60kg), Abdominal crunch (45kg) | ~350 kcal |
| **Day 4: Upper** | Shoulders press (10kg), Lateral raises, Rear delt/Face pull, Pec dec fly (40kg), Cable pullover (15kg), Arms | ~320 kcal |
| **Cardio: เดินชัน** | เดินชันความชัน 10-12% ความเร็ว 4.5-5.0 km/h (40 / 50 / 60 นาที) | ~280 - 420 kcal |

---

## 💬 Command Cheatsheet (คำสั่งใช้งานใน LINE)

| คำสั่ง | ผลลัพธ์ |
|---|---|
| 📸 **ส่งรูปภาพอาหาร** | AI วิเคราะห์ชื่ออาหาร, แคลอรี, โปรตีน/คาร์บ/ไขมัน พร้อมการ์ดกดยืนยันบันทึก |
| `สรุป` / `แคล` / `dashboard` | ดูการ์ด Daily Balance Dashboard พร้อม Progress Bar และสารอาหารสะสมวันนี้ |
| `สถิติ` / `week` / `สัปดาห์นี้` | ดูสรุป 7 วัน: แคลอรีเฉลี่ย, โปรตีนเฉลี่ย, Checklist เวทครบ 4 วันหรือไม่, สรุปเดินชัน |
| `เมื่อวาน` | ดูสรุปยอดและรายการอาหาร/การออกกำลังกายของเมื่อวาน |
| `ประวัติ` / `ประวัติอาหาร` | ดูรายการอาหาร 8 รายการล่าสุดที่บันทึกไว้ในฐานข้อมูล |
| `เวท` / `ตาราง` | เปิดเมนูตารางเวท 4 วัน พร้อมปุ่มกดบันทึกจบวัน |
| `Day 1` ถึง `Day 4` | บันทึกเวทประจำวันทันที พร้อมเพิ่มโควตาแคลอรี |
| `เดินชัน 40` / `50` / `60` | บันทึกการเดินชันพร้อมคำนวณแคลอรีที่เบิร์นตามน้ำหนักตัว |
| `กล้วย` / `นม` | บันทึก Pre-workout snack ทันที |
| `มัจฉะ` / `มัจฉะมะพร้าว` / `ถั่ว` | บันทึกของว่างและเครื่องดื่มทำงานทันที |

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
# หรือ Supabase:
# DATABASE_URL=postgresql://postgres.xxxx:your_password@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres
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
│   │   └── presets.py         # 4-Day workout splits & quick snack presets
│   ├── db/
│   │   ├── database.py        # SQLAlchemy engine & Supabase connection pool
│   │   └── models.py          # Relational ORM models (User, FoodLog, WorkoutLog)
│   ├── services/
│   │   ├── ai_vision.py       # Gemini Multimodal AI vision analysis
│   │   ├── fitness.py         # BMR, TDEE, Deficit & 7-day stats engine
│   │   └── line_handler.py    # LINE Webhook event dispatcher & shortcuts
│   ├── templates/
│   │   └── flex_cards.py      # Premium LINE Flex Message JSON builders
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
