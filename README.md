# LINE Cal

LINE Cal ใช้บันทึกอาหารและการออกกำลังกายผ่าน LINE ส่งรูปหรือพิมพ์ชื่ออาหาร
เพื่อรับค่าประเมิน จากนั้นตรวจและแก้รายการก่อนบันทึก ส่วนโปรแกรมออกกำลังกาย
คาร์ดิโอ สรุปประจำวัน และประวัติ เปิดได้จาก LIFF Web App

## Features

- ประเมินแคลอรีและสารอาหารจากรูปหรือข้อความ โดยใช้ Gemini
- ถามแคลอาหารด้วย `ถาม <อาหาร>` ได้โดยไม่เพิ่มลงประวัติ
- ตรวจและแก้รายการอาหารก่อนบันทึก ยืนยันเพื่อบันทึกหรือยกเลิกได้จากแชท
- ตั้งค่าโปรไฟล์และเป้าหมาย จัดการโปรแกรมเวท และบันทึกเวทหรือคาร์ดิโอในเว็บแอป
- ดูสรุปประจำวันและรายการย้อนหลัง

ตัวเลขแคลอรีเป็นค่าประมาณ ตรวจรายการที่ AI วิเคราะห์ก่อนยืนยันบันทึก

## LINE commands

| ข้อความ | การทำงาน |
| --- | --- |
| ส่งรูปอาหาร | รับรายการให้ตรวจสอบก่อนบันทึก |
| `กิน <อาหาร>` | รับรายการอาหารที่แก้ไข แล้วยืนยันหรือยกเลิกได้ ถ้ากินหลายอย่างให้คั่นด้วย `+` เช่น `กิน ข้าวมันไก่ + น้ำส้ม` |
| `ถาม <อาหาร>` | ดูแคลอรีและสารอาหารโดยประมาณ โดยไม่บันทึก เช่น `ถาม ชาไทย` คำสั่งนี้ใช้ผลประเมินที่เก็บไว้ร่วมกับคำสั่ง `กิน` |
| `สรุป` หรือ `summary` | ดูสรุปอาหารและการออกกำลังกายวันนี้ |
| `เวท` | เปิดรายการโปรแกรมเวทและคาร์ดิโอ |
| `ประวัติ` หรือ `history` | เปิดประวัติในเว็บแอป |
| `โปรไฟล์` หรือ `profile` | เปิดหน้าโปรไฟล์ในเว็บแอป |
| `วิธีใช้` | ดูคำสั่งที่ใช้ได้ ข้อความอื่นจะแสดงคำแนะนำนี้ |

## Local setup

### สิ่งที่ต้องมี

- Python 3.12
- Node.js 22 สำหรับรันทดสอบเว็บแอป
- Docker Compose หากต้องการรันผ่านคอนเทนเนอร์

### ติดตั้งและเริ่มใช้งาน

```bash
git clone https://github.com/KpSuphakorn/line-cal.git
cd line-cal
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

ตอนพัฒนาในเครื่อง ระบบใช้ SQLite เป็นค่าเริ่มต้นและเปิดแอปได้โดยไม่ต้องต่อ
บริการภายนอก หากต้องการทดสอบการส่งข้อความ LINE หรือการประเมินอาหารด้วย Gemini
ให้ใส่คีย์ของบริการนั้นใน `.env` และอย่า commit ไฟล์นี้

รันเซิร์ฟเวอร์สำหรับพัฒนา:

```bash
uvicorn app.main:app --reload --port 8000
```

เปิดเว็บแอปที่ `http://localhost:8000/webapp` เอกสาร API อยู่ที่
`http://localhost:8000/docs`; endpoint ตรวจสถานะคือ `/health` และ `/ready`
การใช้งานแบบยืนยันตัวตนต้องตั้งค่า LINE Login และ LIFF ตามหัวข้อตั้งค่าบริการ

หรือรันด้วย Docker Compose:

```bash
docker-compose up --build
```

### ตั้งค่าบริการ

คัดลอก `.env.example` เป็น `.env` แล้วใส่ค่าที่ต้องใช้:

```dotenv
LINE_CHANNEL_SECRET=...
LINE_CHANNEL_ACCESS_TOKEN=...
GEMINI_API_KEY=...

# ฐานข้อมูลสำหรับพัฒนาในเครื่อง
DATABASE_URL=sqlite:///./line_cal.db

# Production ต้องตั้ง APP_ENV=production, LINE_LOGIN_CHANNEL_ID, LIFF_ID
# และ WEBAPP_BASE_URL ด้วย ดูวิธีตั้งค่าฐานข้อมูลที่ docs/supabase-setup.md
```

ระบบจริงใช้ Supabase/PostgreSQL ให้เก็บรหัสผ่านฐานข้อมูลและ API key ไว้ใน
Secret settings ของแพลตฟอร์มที่ใช้ deploy เว็บแอปตรวจ LINE Login token
กับเซิร์ฟเวอร์ และใช้ตัวตนที่ตรวจสอบแล้วในการเข้าถึงข้อมูล ดูเหตุผลเรื่อง
identity และฐานข้อมูลใน [ADR 0001](docs/adr-0001-storage-identity.md)

วิธีตั้งค่า LIFF และ Rich Menu อยู่ที่
[LINE LIFF and Rich Menu setup](docs/line-rich-menu-setup.md)

## Tests

รันทดสอบฝั่งเซิร์ฟเวอร์:

```bash
pytest -q
```

รันทดสอบเว็บแอป โดยติดตั้งแพ็กเกจจาก `package-lock.json` ก่อน:

```bash
npm ci
npm test
```

GitHub Actions รันทดสอบทั้งสองชุดเมื่อ push หรือเปิด pull request
การทดสอบในเครื่องใช้ค่าทดสอบแยกต่างหาก ไม่ต้องใช้ credential ของระบบจริง

## Deploy to Railway

เมื่อ push ไปที่ `main` GitHub Actions จะรันทดสอบ และ Railway จะเริ่ม deploy
โดยรัน `alembic upgrade head` ก่อนเปิดแอปเวอร์ชันใหม่ ถ้าขั้นตอน migration
ไม่ผ่าน deployment นั้นจะไม่ถูกเปิดใช้งาน

Railway ยัง deploy แยกจากผล GitHub Actions ดังนั้นเทสต์ CI ที่ไม่ผ่าน
ไม่ได้หยุด deployment โดยอัตโนมัติ ตรวจทั้งผล CI และ deployment logs
การรัน Alembic เองใช้เฉพาะตอนตั้งฐานข้อมูลครั้งแรกหรือซ่อมปัญหาที่ตรวจพบแล้ว
รายละเอียดอยู่ใน [Supabase setup](docs/supabase-setup.md)

## License

โปรเจกต์นี้ใช้สัญญาอนุญาต [MIT](LICENSE)
