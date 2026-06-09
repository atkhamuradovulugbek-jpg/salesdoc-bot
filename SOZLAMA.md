# SOZLAMA QO'LLANMASI — SalesDoc Bot

Bu qo'llanma dasturchi bo'lmaganlar uchun. Har qadam oddiy tilda tushuntirilgan.

---

## 1-qadam: Telegram bot yaratish (token olish)

**Token nima?** — Bu botning "paroli". Telegram server shu parol orqali botingizni taniydi.

1. Telegramni oching
2. Qidiruv qatoriga **@BotFather** yozing va shu botga kiring
3. `/newbot` deb yozing va yuboring
4. BotFather: "Botingizga nom bering" deydi → istalgan nom yozing (masalan: `SalesDoc Monitor`)
5. BotFather: "Username bering" deydi → oxiri `bot` bilan tugashi kerak (masalan: `salesdoc_mybot`)
6. BotFather sizga shunday xabar beradi:
   ```
   Done! Use this token to access the HTTP API:
   7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
7. Bu uzun raqam-harf qatorini **nusxalab oling** — bu sizning `TELEGRAM_BOT_TOKEN`ingiz

---

## 2-qadam: O'z Telegram ID'ingizni bilish

**ID nima?** — Telegram'da har bir foydalanuvchining raqamli nomi bor. Bot faqat shu raqamli nomli odamlarga javob beradi.

1. Telegramda **@userinfobot** ni toping
2. `/start` yozing
3. U sizga xabar beradi: `Your ID: 123456789`
4. Bu raqamni yozib qo'ying — `ALLOWED_TELEGRAM_IDS` va `ADMIN_TELEGRAM_IDS` uchun kerak

---

## 3-qadam: Sales Doctor ma'lumotlarini olish

**Bu nima?** — Sales Doctor — siz ishlaydigan savdo tizimi. Botga shu tizimga kirish huquqi beramiz.

Sizga kerakli ma'lumotlar:
- **Domen** — brauzerda Sales Doctor'ni ochadigan manzil (masalan: `https://yourcompany.salesdoc.uz`)
  - Shu manzilni olib, oxiriga `/api/v2` qo'shing: `https://yourcompany.salesdoc.uz/api/v2`
  - Bu — `SALESDOC_BASE_URL`
- **Login** — Sales Doctor'ga kirish uchun foydalanuvchi nomingiz
- **Parol** — Sales Doctor paroli

> Agar bilmasangiz — Sales Doctor support xizmatiga murojaat qiling.

---

## 4-qadam: `.env` faylni to'ldirish

**`.env` fayl nima?** — Bu botning maxfiy ma'lumotlar daftarchi. Faqat siz ko'rasiz, hech kimga yubormaysiz.

**Qanday to'ldirish:**

1. `salesdoc-bot` papkasini oching
2. `.env.example` faylini toping
3. Uni nusxalab (Ctrl+C, keyin Ctrl+V) `.env` deb nomlang (boshida nuqta bor!)
4. `.env` faylini Notepad (yoki boshqa matn muharriri) bilan oching
5. Har qatorni to'ldiring:

```
TELEGRAM_BOT_TOKEN=7123456789:AAHxxxxxxxxxxxxxxxxx
ALLOWED_TELEGRAM_IDS=123456789
ADMIN_TELEGRAM_IDS=123456789
SALESDOC_BASE_URL=https://yourcompany.salesdoc.uz/api/v2
SALESDOC_LOGIN=sizning_loginингиз
SALESDOC_PASSWORD=sizning_parolingiz
DEAD_OUTLET_DAYS=14
DEAD_OUTLET_LOOKBACK_DAYS=90
DEBT_ALERT_THRESHOLD=0
SALES_DROP_ALERT_PERCENT=20
```

> ⚠️ `.env` faylini hech kimga yubormang va GitHub'ga qo'ymang. Bu faylda parollar bor!

---

## 5-qadam: GitHub'ga yuklash

**GitHub nima?** — Bu kodni internet'da saqlash joyi. Railway shu joydan botni oladi.

1. **GitHub akkaunt oching**: [github.com](https://github.com) ga kiring → "Sign up"
2. **Yangi repository (papka) yarating**:
   - "New repository" tugmasini bosing
   - Nom: `salesdoc-bot`
   - "Private" (maxfiy) ni tanlang
   - "Create repository" tugmasini bosing
3. **Kodni yuklash** — GitHub sizga ko'rsatma beradi. Asosiysi:
   - Kompyuterda Git o'rnatilgan bo'lishi kerak ([git-scm.com](https://git-scm.com))
   - `salesdoc-bot` papkasida quyidagi buyruqlarni bajaring (terminal/cmd):
   ```
   git init
   git add .
   git commit -m "first commit"
   git branch -M main
   git remote add origin https://github.com/SIZNING_USERNAME/salesdoc-bot.git
   git push -u origin main
   ```
   > `.env` va `bot.db` fayllari `.gitignore` tufayli yuklanmaydi — parollaringiz xavfsiz!

---

## 6-qadam: Railway'ga joylashtirish (24/7 ishlashi uchun)

**Railway nima?** — Bu internet'dagi server. Botingiz shu yerda doim yoqiq bo'ladi, kompyuteringizni o'chirsa ham.

1. [railway.app](https://railway.app) ga kiring → "Start a New Project"
2. "GitHub" bilan kiring (GitHub akkauntingizni bog'lang)
3. "Deploy from GitHub repo" → `salesdoc-bot` ni tanlang
4. Railway loyihani ko'radi. Chapdan **"Variables"** bo'limiga kiring
5. Har bir o'zgaruvchini qo'shing (`.env` faylidagi har qator):

| Nom | Qiymат |
|-----|--------|
| `TELEGRAM_BOT_TOKEN` | BotFather'dan olgan token |
| `ALLOWED_TELEGRAM_IDS` | Sizning Telegram ID'ingiz |
| `ADMIN_TELEGRAM_IDS` | Sizning Telegram ID'ingiz |
| `SALESDOC_BASE_URL` | `https://yourcompany.salesdoc.uz/api/v2` |
| `SALESDOC_LOGIN` | Login |
| `SALESDOC_PASSWORD` | Parol |
| `DEAD_OUTLET_DAYS` | `14` |
| `DEAD_OUTLET_LOOKBACK_DAYS` | `90` |
| `DEBT_ALERT_THRESHOLD` | `0` |
| `SALES_DROP_ALERT_PERCENT` | `20` |
| `TZ` | `Asia/Tashkent` |

6. "Deploy" tugmasini bosing
7. Railway ekranda yashil chiziq ko'rsatadi — bot ishga tushdi!

---

## 7-qadam: Tekshirish

1. Telegram'da **o'z botingizga** `/start` yozing
2. Tugmalar chiqishi kerak
3. "🔄 Hozir yangilash" tugmasini bosing — "Ma'lumotlar yangilandi!" chiqishi kerak
4. "💰 Kunlik savdo" → "Bugun" ni bosing — savdo ko'rinishi kerak

---

## Muammo bo'lsa

- **Bot javob bermayapti** → Railway'da "Logs" bo'limiga qarang, xato xabari bo'ladi
- **"Sizda ruxsat yo'q"** → `ALLOWED_TELEGRAM_IDS` ga Telegram ID'ingizni qo'shganmisiz?
- **API xatosi** → `SALESDOC_BASE_URL`, login va parolni tekshiring
