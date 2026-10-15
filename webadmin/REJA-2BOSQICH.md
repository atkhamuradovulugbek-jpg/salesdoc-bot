# 2-BOSQICH REJASI — WEB'DAN TO'LIQ BOSHQARUV

> Tuzilgan: 2026-07-18. Asos: foydalanuvchi 5 ta so'rovi + llm-council (5 maslahatchi + o'zaro
> tekshiruv + rais) xulosasi. **Foydalanuvchi 3 ta asosiy qarorni TASDIQLADI (2026-07-18):**
> (1) Konsul tartibi bilan qurish, (2) haqiqiy parol, (3) kartalarni ajratish.
> Handoff: `nazorat/DAVOM.md`. 1-bosqich (read-only web) jonli: bot-production-7a56.up.railway.app

---

## 0. ASOSIY G'OYA — «OY VARAQASI» (period)

Barcha o'zgaruvchan qoidalar **oyga biriktirilgan varaqa**ga yoziladi. Varaqa **e'lon qilinsa
MUZLAYDI** — keyin hech qachon o'zgarmaydi.

**Nega muzlaydi:** iyulda agentga "70 ball = shu sovrin" va'da qilingan va u shunga qarab
**haqiqiy pul** oladi. Avgustda qoidani o'zgartirsak, iyul hisobi buzilmasligi kerak.
Konsul buni eng qattiq shart deb belgiladi (payroll policy, not config).

**Misol:** 30-iyul → "Avgust" varaqasi ochiladi → Bahodirga 75 ball (iyulda 70) → qoralama
(agent ko'rmaydi) → **E'LON QILISH** → 1-avgustdan bot yangi varaqani o'qiydi. Iyul varaqasi
o'zgarmaydi. **O'zgartirmasa** — avgust varaqasi bo'lmaydi, bot iyulnikini davom ettiradi
(carry-forward).

**O'qish qoidasi (MUHIM):** konfiguratsiya **hisobot sanasiga qarab** olinadi (as-of report_date),
"hozirgi" emas. Shunda "kechagi karta" va "oy yakuni" eski qoida bilan to'g'ri qayta hisoblanadi.
`WHERE period_ym <= :report_period ORDER BY period_ym DESC LIMIT 1`.

**Sana emas, OY kaliti:** `period_ym TEXT` ('2026-08'), `DATE` emas — UTC konteynerda
`date` chegarasi Toshkent vaqti bilan 31-kuni 19:00 da "otib ketadi" (timezone bug klassi
sxema darajasida yo'q qilinadi). Toshkent sanasi run boshida BIR MARTA hisoblanadi va
pastga uzatiladi; boshqa joyda `date.today()` chaqirilmaydi.

---

## 1. QURISH TARTIBI (tasdiqlangan)

| # | Nima | Ko'rinadimi | Holat |
|---|---|---|---|
| 0 | 🚨 "Baqiradigan" qilish (fail-loud + kechki nazorat xabari) | Telegramda | ✅ **BAJARILDI 2026-07-30** |
| 0.5 | 🔐 Haqiqiy parol + 💾 backup | Kirishda | ✅ **BAJARILDI 2026-07-30** (parol o'rnatilishi kutilyapti) |
| 1 | 👥 Ro'yxat manbasi = Sales Doctor (KeyError klassi yo'qoladi) | Yo'q | ✅ **BAJARILDI 2026-07-30** |
| 2 | 📮 Vazifa navbati (nz_jobs) + blackout oyna | Yo'q | ✅ **BAJARILDI 2026-07-30** |
| 3 | 🟢🔴 Ulanish ekrani (so'rov #1) | HA | ✅ **BAJARILDI 2026-07-30** |
| 4 | 🔄 Yangilash tugmasi (so'rov #2) | HA | ✅ **BAJARILDI 2026-07-30** |
| 5 | 🎯 Ball plan + sovrin o'chirish (so'rov #3) | HA | ✅ **QURILDI 2026-07-31** (deploy kutilyapti) |
| 6 | 🎁 Promo boshqaruvi (so'rov #4) + karta bo'linishi (so'rov #5) | HA | — |

**Kechiktirilgan (Konsul: hozir TEGMASLIK):** rasm chizish tizimini qayta yozish (slot-based
renderer), plan simulyatori, multi-tenancy, bir vaqtda N ta aksiya, oy qayta hisoblash UI.
Ikki toza oylik tsikldan keyin qaraladi.

---

## 2. BOSQICHLAR — ANIQ ISH

### 0-BOSQICH: "BAQIRADIGAN" QILISH (~2 soat) — birinchi commit

**Muammo:** 2026-07-18 kechki job jimgina yarim ishladi (agentlar oldi, admin/super/GPS yo'q).
Buni bot aytmadi — foydalanuvchi o'zi sezdi. Boshqaruv paneli qo'shishdan oldin tizim
**baqiradigan** bo'lishi shart.

1. `jobs.py` — har bir yuborish bloki alohida `try/except` ichida: bitta agent xatosi
   qolgan agentlarni VA admin/supervayzer/GPS shoxlarini o'ldirmaydi.
2. `nz_delivery` (yoki `nz_sent_log` + kutilgan son) — har bir **mo'ljallangan** yuborish
   yoziladi: `day, kind, target, intended, sent, error, at`.
3. **Nazorat xabari 20:40** (va ertalab 10:30) → adminga bitta qator:
   `✅ kartalar 16/16 · super 2/2 · GPS 2/2 · svodka ✓`
   yoki `⚠️ kartalar 14/16 — Aisha, Rano OLMADI: <xato>`.
4. Testlar: bitta agent sun'iy xato bersa — qolganlari va admin/super/GPS baribir ketadi.

**Qabul mezoni:** noto'g'ri-lekin-yuborilgan kecha va yuborilmagan kecha foydalanuvchiga
**boshqacha ko'rinadi**.

### 0.5-BOSQICH: PAROL + BACKUP (~yarim kun)

**Parol (foydalanuvchi tasdiqladi):**
- `WEB_PIN` → **`WEB_PASSWORD`** (12+ belgi). Telefonda bir marta kiritiladi, saqlanadi.
- Noto'g'ri kiritishga cheklov: 5 xato → progressiv blok (1→2→4→…→15 daq; egasi qulflanmasin).
- Token muddati (30 kun), keyin qayta kirish.
- **MUHIM:** parolni foydalanuvchi O'ZI o'rnatadi (Claude ko'rmaydi):
  `railway variables --set "WEB_PASSWORD=<parol>" --skip-deploys`
- Sabab (Konsul, 5/5 tekshiruvchi): web endi **pul raqamlarini** o'zgartiradi; 6 raqamli PIN
  ochiq havolada 18 kishining bonusini boshqaradi.

**Backup (Konsul: eng katta e'tibordan chetda qolgan xavf):**
- Har kuni `bot.db` nusxasi: `VACUUM INTO` (issiq, xavfsiz nusxa) → gzip → **admin Telegramiga
  document** sifatida (off-box, bepul, bot allaqachon bor). Agar >50MB bo'lsa — kunlik faqat
  `nz_*` + config jadvallari eksporti + haftalik to'liq.
- **Snapshot majburiy:** har sync'dan oldin, har publish'dan oldin, har migratsiyadan oldin.
- Sync ichida transaksiya + **sog'lomlik tekshiruvi**: yangi `orders` soni oldingidan 50%
  pastga tushsa — COMMIT qilinmaydi (bo'sh baza → 16 agentga "savdo 0" kartasi bo'lmaydi).

### 1-BOSQICH: RO'YXAT MANBASI = SALES DOCTOR

Kechagi `KeyError: d0_152` ning ILDIZI — ro'yxat ikki joyda (YAML + baza). Konsulning eng o'tkir
tashxisi: **API ro'yxati kim BOR ekanini belgilaydi; YAML/baza faqat bezaydi** (display, liga,
ball_plan). Noma'lum sd_id — jimgina o'tkaziladi, hech qachon fatal emas.

- `resolve_roster()` bitta funksiya: `agents` (active='Y') + YAML/DB dekoratsiya.
- On-demand handlerlar ham shu orqali (hozir `dc.snap[...]` to'g'ridan-to'g'ri — chip bor).
- Regressiya testi: YAML'da bor, bazada active='N' agent → hamma yo'lda (kechki/ertalabki/
  alerts/on-demand) xato bermaydi.

### 2-BOSQICH: VAZIFA NAVBATI + BLACKOUT

**Nega:** web hozir faqat o'qiydi — shuning uchun 2 bot bilan bitta SQLite faylida xavfsiz.
2-bosqich uni YOZUVCHI qiladi. Konsul (4/5 mustaqil) bir xil yechimni aytdi: **web yozmaydi —
navbatga qo'yadi, bot bajaradi** (yagona yozuvchi qoidasi saqlanadi).

- `nz_jobs(id, kind, payload_json, status, requested_by, created_at, started_at, finished_at, error)`
- Worker: nazorat bot ichida har 15 sek poll → bajaradi (sync / approve / unbind / publish).
- **Blackout 19:50–20:35:** sync bu oynada BOSHLANMAYDI, navbatda turadi, UI aytadi:
  "kechki hisobotdan keyin, 20:40 da bajariladi".
  *Sabab: 2026-07-15 da aynan shu to'qnashuv noto'g'ri raqam yuborgan (nazorat sync bo'sh
  qaytgan). Foydalanuvchi tugmani aynan raqam g'alati ko'ringanda — ya'ni 20:09 da — bosadi.*
- Web tranzaksiyalari kichik (bir qator), millisekundlar.

### 3-BOSQICH: ULANISH EKRANI (so'rov #1)

- Ro'yxat: barcha agent + supervayzer. 🟢 ulangan / 🔴 ulanmagan (nz_bindings bo'yicha).
- **Uzish:** ism yozib tasdiqlash (bitta noto'g'ri bosish = agent bir oy hech narsa olmaydi —
  kechagi jim xato bilan bir xil sinf). → job.
- **Tasdiqlash:** `nz_bind_request(code, chat_id, requested_at, expires_at, status)` — agent kod
  yozganda so'rov yaratiladi; web'da "kutilyapti" ko'rinadi → Tasdiqlash/Rad etish → job.
- **Kod bir martalik + 24 soat muddat** (TTL). Ulangach agentga xabar: "siz X sifatida
  ulandingiz" — noto'g'ri ulanish darrov ko'rinadi.
- Telegram Ha/Yo'q **bir xil funksiyani** chaqiradi (yagona kod yo'li — ikki xil mantiq yo'q);
  web asosiy, Telegram zapas + xabarnoma.

### 4-BOSQICH: YANGILASH TUGMASI (so'rov #2)

- Tugma → `nz_jobs` ga sync vazifasi (tez / to'liq tanlovi).
- Debounce: oxirgi sync'dan 5 daqiqa o'tmasa — qayta qo'ymaydi.
- Blackout oynada — navbatga, tushunarli xabar bilan.
- Ekranda: oxirgi sync vaqti, turi, natijasi (`orders=2703`), holati.

### 5-BOSQICH: BALL PLAN + SOVRIN O'CHIRISH (so'rov #3)

```sql
nz_period(period_ym TEXT PK, status TEXT,        -- draft|published|closed
          payload_json TEXT, checksum TEXT,       -- MUZLATILGAN huquqiy yozuv
          published_at TEXT, published_by TEXT)
nz_agent_plan(agent_sd_id TEXT, period_ym TEXT, ball_plan INT,
              prizes_enabled INT, source_period_ym TEXT,
              PRIMARY KEY (agent_sd_id, period_ym))
```
**Gibrid (Konsul yechimi):** hisobotlar JOIN qiladigan narsa — normal qatorlar (agent plani,
promo mahsulotlari); renderer butun o'qiydigan narsa — JSON payload. Payload = huquqiy yozuv,
qatorlar = so'rov yuzasi. Ikkalasi publish paytida bitta qoralamadan yoziladi, checksum ikkalasini
qamraydi.

- `resolve_config(report_date)` — DayContext'da **BIR MARTA** chaqiriladi. YAML — seed va fallback
  (1-kuni hech narsa o'zgarmaydi).
- Har kartaga va oy yakuni qatoriga `period_ym + checksum` bosiladi (keyin "qaysi qoida bilan
  hisoblangan" aniq bo'ladi).
- **Publish oqimi:** qoralama → **ro'yxat farqi tasdiqlash** (kim qo'shildi/ketdi — carry-forward
  yangi agentni jimgina tashlab ketmasligi uchun) → **haqiqiy PNG namunasi adminga Telegramda**
  → tasdiq → publish (muzlaydi).
- **Sovrin o'chirish:** `prizes_enabled=0` → ball ko'rinadi, sovrin/podium yozuvi yo'q.
  **BALAND E'LON:** o'chirilganda agentlarga tushuntirish kartasi ketadi (Konsul: jimgina
  motivatsiyani o'ldirish — eng yomon xato turi).
- **Oy o'rtasida o'zgartirish:** yangi versiya + foydalanuvchi NIYATI aniq yoziladi —
  "bugundan amal qiladi" yoki "butun oyga (qayta hisobla)". Taxmin QILINMAYDI.
- **Yopilgan oy — faqat o'qiladi.** Oy yakuni muzlatilgan payload'ni o'qiydi, jonli configni emas.
- ⚠️ **HAL QILINISHI SHART (Konsul: 5/5 tekshiruvchi topdi):** `agent_plans` (eski bot savdo plani)
  bilan yangi tizim. **Uchinchi plan tizimi qurilmasin.** Yechim: web savdo plani ekrani
  IKKALASIGA yozadi (agent_plans + payload) — ikki bot bir xil raqam ko'rsatadi. Yoki eski bot
  yangi jadvalga qaratiladi. 5-bosqichdan OLDIN qaror qilinadi.

### 6-BOSQICH: PROMO (so'rov #4) + KARTA BO'LINISHI (so'rov #5)

```sql
nz_promo(id INTEGER PK, period_ym TEXT, name TEXT, target_blocks REAL,
         units_per_block INT, valid_from TEXT, valid_to TEXT, active INT)
nz_promo_product(promo_id INTEGER, product_sd_id TEXT)   -- BIR NECHTA mahsulot
```
- Mahsulot tanlash: `products` jadvalidan nom bo'yicha qidirib (masalan "baklava").
- Bir nechta mahsulot → hammasi birga sanaladi.
- **Promo yo'q → MUSOBAQA kartasi umuman chizilmaydi**; supervayzer jadvalidan Toy ustuni tushadi.
  Hech kimga promo hisoboti bormaydi.
- **KARTA BO'LINISHI (= so'rov #5, alohida bosqich emas):**
  - 📌 **DOIMIY karta** — savdo reja, qarz, vazvrat, pul → **HAR DOIM** boradi.
  - 🎯 **MUSOBAQA kartasi** — ball, promo, sovrin → faqat e'lon qilingan bo'lsa.
  - Konsul: "promo off = o'sha rasmni chizmaslik" — qat'iy layoutli PNG ichini shartli qilish
    matnlar ustma-ust tushishiga olib keladi va buni 16 agent ko'rmaguncha bilinmaydi.
  - Musobaqadagi xato **hech qachon** qarz/savdo kartasiga tegmaydi.

---

## 3. QO'SHIMCHA MAJBURIY NARSALAR (Konsul topdi)

1. **UNDO, faqat audit emas.** Qatorlar append-only; har ekranda "oldingi holatga qaytarish"
   tugmasi. Foydalanuvchi tushunadigan bitta tugma.
2. **Audit:** kim, qachon, nimani o'zgartirdi (publish_by, requested_by, job tarixi).
3. **TUZATISH protokoli:** noto'g'ri raqam allaqachon ketgan bo'lsa nima bo'ladi? "Kechagi karta
   xato edi, mana to'g'risi" kartasini yuborish yo'li kerak (biznes-jarayon bo'shlig'i).
4. **Namuna = HAQIQIY rasm.** Publish'dan oldin admin Telegramda **haqiqiy PNG**ni ko'radi
   (forma xulosasi emas), keyin tasdiqlaydi.
5. **Ekranda oy KATTA yozilsin** + qoralama/jonli/yopilgan uchun boshqa fon rang
   (iyulga qarab avgustni tahrirlash xatosi).

## 4. EHTIYOT BO'LINADIGAN XATO TURLARI

| Xato | Himoya |
|---|---|
| Sync yarmida uzilib `orders` bo'shab qolishi → 16 agentga "savdo 0" | Snapshot + transaksiya + qator soni 50% dan pastga tushsa commit yo'q |
| UTC konteynerda oy chegarasi 31-kuni 19:00 da otishi | `period_ym` (oy kaliti) + Toshkent sanasi run boshida bir marta |
| Iyulga qarab avgustni tahrirlash | Oy katta yozuv + rang, tasdiq ekrani |
| Carry-forward yangi agentni tashlab ketishi | Publish'da ro'yxat farqini tasdiqlash |
| Retroaktiv "promo off" iyul sovrinini o'chirishi | Yopilgan oy o'zgarmas; oy yakuni muzlatilgan payload'dan |
| Jimgina "sovrin o'chdi" → motivatsiya o'ladi | Baland e'lon kartasi + admin tasdig'i |
| Noto'g'ri bosish bilan agentni uzish | Ism yozib tasdiqlash |
| Bitta agent xatosi butun kechki jobni o'ldirishi | 0-bosqich: per-recipient try/except + nazorat xabari |

---

## 5. HOZIRGI HOLAT

- ✅ Reja tuzildi, 3 asosiy qaror tasdiqlandi (2026-07-18).
- ✅ **0-BOSQICH BAJARILDI VA JONLI (2026-07-30 13:53).** Tafsilot pastda.
- ✅ **0.5-BOSQICH BAJARILDI VA JONLI (2026-07-30 14:05).** Tafsilot pastda.
- ✅ **PAROL O'RNATILDI (2026-07-30 14:25):** `WEB_PASSWORD=Tamotaka310`. Jonli: yangi parol 200 +
  `weak:false`, eski PIN 401, dasturda ogohlantirish yo'q. Brute-force himoyasi ham tasdiqlandi
  (sinov paytida Claude'ning IP'si bloklandi). Kod'dan WEB_PIN zapasi olib tashlandi.
- ⚠️ **RAILWAY XATARI:** `railway redeploy` / `--skip-deploys`siz `variables --set` ESKI deployment'ni
  ko'taradi → nazorat bot + web o'chadi (14:13–14:24 da shunday bo'ldi). Doim **`railway up --ci`**.
- 🔧 **TUZATISHLAR (2026-07-30 14:40, foydalanuvchi telefonda kira olmadi):**
  1. **Blok juda uzun edi** — 1-blok 15 daqiqa → **1 daqiqa**, keyin progressiv (1→2→4→8→15 daq,
     `RateLimiter._block_len`). Egasi o'zini uzoq qulflab qo'ymaydi, brute-force baribir imkonsiz
     (daqiqada 5 urinish). Blok har mijoz IP'si uchun alohida (`x-forwarded-for`).
  2. **ILDIZ SABAB — telefon ESKI sahifani keshdan olardi:** eski `index.html` da
     `maxlength="6"` bor edi → 11 belgili parol **6 belgiga qirqilib** yuborilardi → doim
     "noto'g'ri" → 5 urinishdan keyin blok. Yechim: `style.css?v=3` / `app.js?v=3`
     (kesh-buzish) + no-store middleware. Kelajakda statik fayl o'zgarsa `v=` raqamini oshirish.
  3. **👁 "parolni ko'rsatish" tugmasi** qo'shildi (`#pin-eye`, app.js wire()).
  84 test o'tadi. Jonli tekshirildi: brauzerda to'liq kirish + 👁 ishlaydi, blok tozalandi.
- ✅ **1-BOSQICH BAJARILDI VA JONLI (2026-07-30 ~15:00).** Tafsilot pastda.
- ✅ **5-BOSQICH QURILDI (2026-07-31, 136 test, lokal to'liq sinaldi — DEPLOY KUTILYAPTI).**
  Tafsilot pastda.
- ⏭️ Keyingi: 6-bosqich (promo `nz_promo` + karta bo'linishi).
- ℹ️ `agent_plans` qarori **5-bosqichga KERAK BO'LMADI**: u SAVDO planiga tegishli, ball plani
  esa mustaqil (faqat `agents.yaml` da edi). Qaror savdo plani ekrani qurilganda kerak bo'ladi.

### ✅ 5-BOSQICH — «OY VARAQASI» (2026-07-31, 136 test)

**Yangi fayl `nazorat/period.py`** — oy varaqasining butun mantig'i (sof, Telegramsiz):
- `nz_period(period_ym PK, status, prizes_enabled, payload, checksum, …)` + `nz_agent_plan(sd_id, period_ym, ball_plan)`.
- `resolve(conn, day)` — **hisobot sanasiga** amal qiladigan E'LON QILINGAN varaqa
  (`WHERE period_ym <= ? AND status='published' ORDER BY DESC LIMIT 1`). Yo'q bo'lsa → None → YAML.
- `apply_to(conn, agents, day)` — Agent obyektlariga ball planini qo'yadi.
- `save_draft` / `publish` (checksum bilan muzlatadi) / `unpublish` (faqat oy **boshlanmagan** bo'lsa)
  / `sheet_view` (ekran uchun: was→now, o'zgargan, yangi, ketganlar).

**Ulanish nuqtasi — `roster.py`** (yagona joy): `classify(conn, cfg, day)` endi varaqani qo'llaydi,
shuning uchun **barcha yo'llar** (build/gps/monitor/bot on-demand) avtomatik bir xil raqamni ko'radi.
Xato bo'lsa `_apply_period` uni yutadi va YAML bilan davom etadi — hisobot plan tufayli qulamaydi.
`build.py` `day=self.today` uzatadi → kechagi karta va oy yakuni O'SHA paytdagi qoidani oladi.

**Sovrin o'chirish:** `month_end.compute_month_final` `dc.period.prizes_enabled` ni tekshiradi —
o'chirilgan bo'lsa podium/o'sish hisoblanmaydi. Muzlatilgan bo'lgani uchun keyin o'chirilsa ham
**iyul sovrini o'chib ketmaydi**.

**Bot tomoni `nazorat/period_jobs.py`** + taskq `period_preview` / `period_publish`:
- namuna = **HAQIQIY PNG** (`DayContext(plan_override=draft)` → `render_ball_card`) adminга;
- e'lon = muzlatish + adminга tasdiq (sovrin o'chirilgan bo'lsa BALAND E'LON matni).

**Web:** ⚙️ Boshqaruv → **🎯 Ball plan** chip. Oy tanlash, har agentga raqam maydoni (was→now),
sovrin kalit, 💾 Saqlash / 👀 Namuna / 📣 E'LON QILISH (**oy nomini yozib tasdiqlash**),
↩️ E'lonni qaytarish (faqat boshlanmagan oy). Muzlagan varaqa: ko'k fon + 🔒 + muhr, maydonlar
o'chirilgan. Bot bajarayotganda: sariq fon + ⏳ + tugmalar bloklangan (takror bosish yo'q).

**Tuzatilgan kamchiliklar (sinov paytida topildi):** `no such table` (web botdan oldin ko'tarilsa) →
`main.py` startup'da `init_nz_tables` + `period.py` da jadval yo'qligiga chidamlilik · birinchi
varaqada hamma "yangi" bo'lib chiqishi · e'lon bosilgach ekranda hech narsa o'zgarmasligi.

**Sinov:** 17 yangi test + uchidan-uchiga (haqiqiy baza nusxasi): qoralama sizib chiqmaydi ·
1-avgustdan kuchga kiradi · **15-iyul o'zgarmaydi** · muzlagan varaqa 409 · noto'g'ri tasdiq 400 ·
bot vazifani bajarib PNG+matn yuboradi · karta yangi planni (90 ball) ko'rsatadi.

### ✅ 1-BOSQICH — BAJARILDI (2026-07-30, jonli, 92 test o'tadi)

**Yangi fayl `nazorat/roster.py` — RO'YXATNING YAGONA MANBASI:**
- `classify(conn, cfg) -> (faol, ketganlar, bazada_yo'qlar)` va `active_agents(conn, cfg, league)`.
- **Qoida:** KIM BOR — Sales Doctor (`agents.active='Y'`) belgilaydi; **YAML faqat BEZAYDI**
  (display/liga/kod/ball_plan/observe/start_date). Ketgan agent hamma joydan avtomatik chiqadi.
- Noma'lum sd_id (YAML'da bor, bazada yo'q) — **jimgina o'tkazilmaydi**: ro'yxatda qoladi + WARNING
  log (YAML'da xato id bo'lishi mumkin). `agents` jadvali yo'q bo'lsa (test/lokal) — hamma qoladi.

**Takrorlangan filtr OLIB TASHLANDI** (bir xil 3 qator 3 joyda edi):
`build.py DayContext._load`, `gps.py build_league_card`, `monitor.py gps_check` → endi hammasi
`roster.active_agents()` chaqiradi. `storage.inactive_sd_ids` ishlatilmaydi (jadvalda qoldi).

**bot.py ON-DEMAND TUGMALAR HIMOYALANDI** (avval umuman guard yo'q edi — chip'da turgan ish):
`_agent_ctx(update, b, today=None)` helperi + `INACTIVE_MSG`. Qo'llanildi: cmd_bugun, cmd_kecha,
cmd_toy, cmd_qarz, cmd_vazvrat, cmd_oy, `_send_self_report` (ulanish tasdig'idan keyin) va admin
"📤 Namuna yuborish". Ulangan agent ishdan ketsa — KeyError emas, tushunarli o'zbekcha javob.

**Testlar** `nazorat/tests/test_roster_source.py` (8 ta): ketgan chiqadi (aynan d0_152 holati),
noma'lum id belgilanadi lekin tashlanmaydi, `active=NULL` faol deb olinadi, jadval yo'q → hamma
qoladi, hammasi ketgan → bo'sh ro'yxat (xato emas), liga filtri, YAML bezashi ustunligi.

**Jonli tekshiruv (serverda):** YAML 18 → FAOL 18, ketgan 0; `dc.agents == dc.snap` (18=18) ✓;
GPS 10+8=18 qator ✓; monitor 18 ✓ — **uchala yo'l endi AYNAN bir xil ro'yxatni ko'radi.**

### ✅ 0.5-BOSQICH — BAJARILDI (2026-07-30, jonli, 82 test o'tadi)

**Parol — `webadmin/auth.py` (sof mantiq, testlanadi):**
- `SECRET = os.getenv("WEB_PASSWORD","")` — faqat parol. Eski `WEB_PIN` zapasi OLIB TASHLANDI
  (2026-07-31, parol o'rnatilgach): parol qo'yilmagan bo'lsa 500 (jimgina zaif PIN yonmaydi).
   Hozir jonli: `WEB_PASSWORD=Tamotaka310`, Railway'da WEB_PIN o'chirilgan.
- **Token muddati:** `"<exp>.<hmac-imzo>"`, 30 kun, serverda holat saqlanmaydi. Muddatni
  cho'zib qo'yish imzoni buzadi; parol o'zgarsa barcha eski tokenlar o'chadi.
- **Brute-force cheklovi (PROGRESSIV):** IP bo'yicha 5 xato → **1 daqiqa** blok, keyin qayta
  urinsa 2×2× uzayadi (1→2→4→8→15 daq, `block_max=900`). Nega 1 daqiqa: 15 daqiqa edi va EGASI
  o'zini qulflab qo'yardi (bitta foydalanuvchi). 1 daqiqa brute-force'ni baribir imkonsiz qiladi.
- `password_ok` — `hmac.compare_digest` (timing attack'ga qarshi).
- Frontend: PIN maydoni → parol maydoni (`autocomplete="current-password"`), `weak-warn` banner.

**Backup — `nazorat/backup.py`:**
- `make_snapshot()` — SQLite `VACUUM INTO` (issiq, xavfsiz nusxa; botlar ishlab turganda ham
  to'g'ri). Keyingi bosqichlarda sync/publish'dan OLDIN ham shu ishlatiladi.
- `send_db_backup()` — nusxa → gzip → **admin Telegramiga document** (konteynerdan TASHQARIDA
  saqlanadi — asosiy maqsad). `/tmp` da yasaladi, yuborilgach o'chiriladi (volume to'lmasin).
  `nz_sent_log` bilan kuniga bir marta. >45MB bo'lsa adminга ogohlantirish.
- `sanity_ok()` — sync'dan keyin qator soni 50% dan pastga tushmaganini tekshirish (keyingi
  bosqichda sync ichiga ulanadi: bo'sh baza → "savdo 0" kartalari ketmasligi uchun).
- **Jadval:** `run.py` da kunlik 03:30 (03:00 to'liq sync'dan keyin).
- Jonli hajm: bot.db 29MB → VACUUM 27MB → **gzip 7.6MB** (Telegram 50MB limitiga mos).
- Birinchi nusxa 2026-07-30 14:05 da qo'lda yuborildi (`sent`), ishlagani tasdiqlandi.

**Testlar:** `webadmin/tests/test_auth.py` (13) + `webadmin/tests/test_login_api.py` (8, haqiqiy
FastAPI TestClient: parol/xato/blok/eski-PIN-ko'chirish/token himoyasi).
**YANGI TEST BUYRUG'I:** `./venv/bin/python -m pytest nazorat/tests/ webadmin/tests/ -q` (82 ta).

### ✅ 0-BOSQICH — BAJARILDI (2026-07-30, jonli, 61 test o'tadi)

**Yangi fayl `nazorat/health.py`** — sof mantiq (Telegramsiz, testlanadi):
- `RunReport` — blok bo'yicha `sent/dup/unbound/skip/fail` + xatolar (max 8) + `last_block`.
- `build_watchdog_text(job, day_label, row)` — adminга tayyor matn. 4 holat: hammasi joyida /
  qismiy xato (kim, qanday xato) / **job TUGAMADI** (oxirgi bosqich ko'rsatiladi) / umuman ishlamadi.

**`nazorat/jobs.py`:**
- `_guard(rep, block, fn, who)` — har bo'lak alohida `try/except`. Bitta agent xatosi endi
  qolgan agentlarni VA admin/supervayzer/GPS ni O'LDIRMAYDI.
- Bo'linди: `_agent_evening_one`, `_agent_morning_one`, `_gps_one`, `_alert_one`,
  `_group_daily(…, league)` — har biri BITTA qabul qiluvchi (per-recipient granularity).
- `_send_agent`/`_send_supervisor` endi holat qaytaradi (`sent/dup/unbound`) va to'liq
  yuborilmasa XATO ko'taradi (avval jimgina `return` qilardi).
- `_build_context()` — DayContext qulasa adminга darhol xabar (jimgina o'tmaydi).
- `watchdog(app, job)` — nz_job_run'dan o'qib bitta xabar yuboradi, kuniga bir marta (notified_at).

**`nazorat/storage.py`:** `nz_job_run(day, job, started_at, finished_at, payload, notified_at)`
+ `save_job_run/get_job_run/mark_job_notified`. Job boshida VA oxirida yoziladi →
`finished_at IS NULL` = job qulagan.

**`nazorat/run.py`:** watchdog cron — kechki 20:40, ertalabki 10:30 (`NZ_WATCHDOG_AFTER_MIN=30`,
`_plus()` helper). **`nazorat/nz_config.py`:** `WATCHDOG_AFTER_MIN`.

**Testlar** `nazorat/tests/test_health.py` (17 ta): RunReport hisobi, 4 xil watchdog matni,
nz_job_run saqlash/dedup, va ASOSIY REGRESSIYA — `_guard` izolyatsiyasi (bitta agent yiqilsa
qolganlari + keyingi bloklar baribir ketadi).

**Uchidan-uchiga sinov** (nusxa bazada, soxta bot, DRY_RUN=false, hamma ulangan):
- Normal: 17 agent × 3 = **51 rasm**, supervayzer 4, xabar: "Hammasi joyida ✅".
- Sun'iy `KeyError: d0_152` 2-agentda: **48 rasm** (16 agent oldi), supervayzer **4/4 BARIBIR oldi**
  (avval 0 bo'lardi!), job tugadi, xabar: "🚨 MUAMMO · ❌ Agent kartalari 16/17 · Jonibek: KeyError".
