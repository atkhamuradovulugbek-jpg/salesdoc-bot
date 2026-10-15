# SIRIBOM NAZORAT BOT — HOLAT VA DAVOM ETISH FAYLI

> ⚡ **QISQA XULOSA KERAKMI?** → `XULOSA.md` (loyiha ildizida): nima ishlayapti, nima qildik,
> nima buzildi/tuzatildi, nima qolgan — sodda tilda. Bu fayl esa TO'LIQ texnik tarix.

> Bu fayl loyihaning to'liq holatini saqlaydi. Chat tozalangach, Claude shu faylni
> o'qib, nima qilinganini tushunib, foydalanuvchidan ruxsat so'rab davom etadi.
> Oxirgi yangilanish: 2026-07-14.

---

## 0. AGAR SEN CLAUDE BO'LSANG — BIRINCHI O'QI

- Bu — **Siribom Nazorat Bot** loyihasi: konditer distributsiya kompaniyasi (Toshkent)
  savdo agentlari uchun motivatsiya + supervayzer nazorati Telegram-boti.
- Kod: `~/Desktop/salesdoc-bot`, branch **`nazorat-bot`**, paket **`nazorat/`**.
- Foydalanuvchi dasturchi EMAS — o'zbekcha sodda tushuntir, buyruqlarni o'zing bajar.
- HOLAT: kod ~95% tayyor, kartalar/jadvallar foydalanuvchi bilan ko'rilib tuzatilgan.
  **Hali DEPLOY qilinmagan, DRY_RUN sinov boshlanmagan.**
- **DAVOM ETISHDAN OLDIN:** bu faylni to'liq o'qi → foydalanuvchiga qisqa xulosa ber
  ("shu yergacha keldik, keyingi qadam bu") → **ruxsat so'ra** → keyin bajar.
- Bot lokal ishlaydi, `~/Desktop/salesdoc-bot/venv/` bor. Test: `venv/bin/python -m pytest nazorat/tests/`.
- Bash'da PATH kerak: `export PATH="/opt/homebrew/bin:$PATH"`.

---

## 1. LOYIHA NIMA

Kompaniya: konditer/jele/baklava distributsiyasi, Toshkent. **16 savdo agenti**, 2 liga:
**Shahar** (8 agent) va **Viloyat** (8 agent). Har ligada 1 supervayzer.

Bot har kuni SalesDoctor API'dan ma'lumot olib, har agentga shaxsiy motivatsion
hisobot, supervayzerlarga nazorat jadvallari, adminga svodka yuboradi. Maqsad —
savdoni 2x oshirish, agentlarni "har kuni o't yondirish", kuchsizlarni sindirmaslik.

**Ikkita bot bitta bazani ulashadi:**
- Asosiy `salesdoc-bot` (admin monitoringi, allaqachon jonli) — `bot.py`.
- Yangi `nazorat` bot (agentlar+supervayzer) — `nazorat/`.
- Bitta `bot.db` (SQLite, Railway volume `/app/data`), bitta Sales Doctor sync.

**Yangi bot:** [@siribom_nazorat_bot](https://t.me/siribom_nazorat_bot) (id 8602077170).
Token `.env` da (lokal, gitignored) + Railway var `NAZORAT_BOT_TOKEN`. Admin id = 700216613.
Foydalanuvchi botda `/start` bosgan.

---

## 2. TEXNIK TUZILMA (fayllar)

```
nazorat/
  config/rules.yaml     — HAMMA biznes raqamlar (ball shkala, planlar, sovrinlar,
                          toy shkala, kpi %, qarz limit, strike). Kodda raqam yo'q.
  config/agents.yaml    — 16 agent (sd_id, display ism, liga, kod, ball_plan) + 2 supervayzer.
  core/                 — SOF hisob funksiyalari (testlanadi):
    rules.py            — yaml→pydantic yuklash
    workdays.py         — ish kunlari (yakshanba dam, 26-27 kun/oy)
    balls.py            — kunlik/oylik ball
    podium.py           — podium reyting + kunlik reyting
    growth.py           — o'sish sovrini
    toy.py              — Happy Toy bloklar/darajalar
    kpi.py              — komissiya + plan bonus
    forecast.py         — prognoz + "eng foydali harakat"
  data.py               — DB→hisob ko'prigi (savdo, vazvrat, qarz, strike, toy, vizit)
  build.py              — DayContext: barcha agent snapshotlari + karta/jadval dict'lari
  cards.py              — Pillow rasm-kartalar (render_* funksiyalar)
  icons.py              — sodda chiziqli ikonkalar
  storage.py            — nz_ jadvallar (bindings/sent_log/balance_history/month_results/raw_cache)
  nz_config.py          — .env sozlamalari (token, admin, DRY_RUN, vaqtlar)
  bot.py                — Telegram handlerlar (/start kod ulash, /bugun /oy /toy /qarz /vazvrat)
  jobs.py               — 10:00 ertalabki, 20:00 kechki joblar (DRY_RUN→admin, idempotent)
  month_end.py          — oy yakuni reveal + /tasdiqla
  run.py                — APScheduler + polling (nazorat botni ishga tushiradi)
  send_now.py           — qo'lda namuna yuborish (test uchun)
  assets/logo.png       — Siribom logosi (oq fon shaffof qilingan)
  tests/                — 31 test (etalon iyun + ball/podium/kpi/toy/growth/storage)
  DAVOM.md              — SHU FAYL
start_all.py            — launcher: 2 botni 1 konteynerda (asosiy + nazorat) subprocess
Procfile, Dockerfile    — endi `python start_all.py` (asosiy bot ham shu orqali)
```

**Kartalar namunalari:** `~/Desktop/siribom-nazorat-bot/kartalar/` (PNG).

---

## 3. KELISHILGAN BIZNES QOIDALARI (rules.yaml da)

- **Kunlik ball:** kunlik savdo ÷ kunlik reja → 0-79%=0, 80-89%=1, 90-99%=2, 100-149%=3, 150%+=4.
- **Kunlik reja:** Shahar 2 mln, Viloyat 2.31 mln. Yakshanba dam (26-27 kun/oy).
- **Oylik ball plani:** Shahar: Bahodir/Jonibek/Abdulaziz 70, Sherzod/Jasmina/Umarjon 60,
  Xikmatilla/Burhon 50. Viloyat: Rano 80, Aisha/Husniobod/Dildora/Yulduz 70, Usmonbek/Maftuna/Eliza 60.
- **Podium** (liga bo'yicha): plandan oshgan ballar reytingi. 1-o'rin 1.5 mln, 2-o'rin 1 mln,
  3-o'rin 500k. 1-o'rin ketma-ket 2 oy yo'q. Kamida +1 oshgan qatnashadi.
- **O'sish sovrini:** o'tgan oyga nisbatan sof savdo +% eng katta = 700k. Min +10%. Ketma-ket 2 oy yo'q.
- **Happy Toy:** SKU **d0_146** (Kinder Toy zummi), 24 dona/blok. 105 blok=600k, 135=900k, 150=1.2mln.
  Hamma ligaga bir xil shkala, iyuldan. Faqat sotilgan/qaytmagan.
- **KPI komissiya** (oylik savdoga): Shahar 20-29mln=2%, 30-39=3%, 40-49=4%, 50=5%, 60=6%.
  Viloyat 30-39=3%, 40-59=4%, 60=5%, 80=6%. Plan bonus: Shahar 80%=500k/90%=750k/100%=1mln, Viloyat 100%=1mln.
- **Qarz limiti:** Shahar 3 mln, Viloyat 4 mln.
- **Svetofor (foydalanuvchi Excel qoidasi):** <70% qizil, 70-89% sariq, 90%+ yashil.
- **Strike svetofor:** <45% qizil, 45-59% sariq, 60%+ yashil.

**Test etaloni (MAJBURIY, iyun 2026):** Bahodir 75 ball, Rano 80, Usmonbek 19 — o'tadi.

---

## 4. ENG MUHIM TOPILMALAR (foydalanuvchi solishtiruvidan)

### 4a. Vazvrat = 2 xil (SalesDoctor)
- **To'liq vazvrat:** buyurtma status **4** (Возврат) — do'kon butun buyurtmani rad etgan.
  Savdodan tashqarida (status 1,2,3 emas).
- **Qisman vazvrat:** status 3 (Доставлен), `totalReturnsSumma` > 0 — do'kon ba'zi tovarni olmagan.
- **Bot ikkalasini ham sanaydi** (foydalanuvchi qarori).
- **CHIQARILADI:** Обмен (almashtirish — bir xil summaga tovar, yo'qotish yo'q) va
  Возврат с полки (javon vazvrati) — foydalanuvchi "sanamaslik" dedi, va ular getOrder'da
  umuman kelmaydi (faqat "Заказ" turini qaytaradi) → avtomatik chiqarilgan.
- Etalon: Aisha iyul to'liq 406100 + qisman 433600 = 839700 ✓ (foydalanuvchi 406700 = faqat to'liq).

### 4b. Savdo summasi ALLAQACHON SOF
- `totalSummaAfterDiscount` = Сумма после (vazvrat avtomatik ayirilgan).
- Shuning uchun **`returns_reduce_ball: false`** — ballni yana ayirmaymiz (ikki marta ayirish xatosi tuzatildi).
- "Vazvrat ballni kamaytiradi" avtomatik ishlaydi (sof savdo orqali).

### 4c. sync o'zgarishlari
- `get_orders` endi status **[1,2,3,4]** tortadi (4 = to'liq vazvrat; asosiy bot doim IN(1,2,3) filtrlaydi — buzilmaydi).
- `get_visits` endi **oylik** tortadi (month→today) — strike rate barqaror bo'lishi uchun.
- `order_items` ga `returned`, `block`; `orders` ga `total_returns` qo'shildi.

### 4d. STRIKE RATE (2x uchun eng muhim raqam)
- Strike = kirgan do'konning nechtasi oldi = visited=1 vizitning has_order=1 ulushi.
- Konsul (4-llm-council) topdi: savdo hajmi ALDASHI mumkin, strike haqiqatni ko'rsatadi.
- Real strike (o'sish rejasiga mos): Usmonbek 25%, Eliza 30%, Aisha 32%, Rano 51%.

---

## 5. KARTALAR VA JADVALLAR (nima ko'rsatadi)

### Agentga (shaxsiy):
- **KECHQURUN 20:00 — 3 karta:**
  1. **Ball musobaqasi** — bugungi savdo+ball, bugungi savdo bo'yicha O'RIN + kechagiga
     nisbatan katta banner (ko'tarildi yashil/tushdi qizil/o'zgarmadi sariq), oy natijasi/reja,
     "shu sur'atda X ball" katta banner + trayektoriya izohi (rejaga qancha, kuniga qancha kerak).
  2. **Savdo reja** — ish kuni (27/o'tdi/qoldi), reja/bajardingiz/qoldi 3 katak, OYLIK PROGNOZ,
     kunlik kerak + bugungi savdo (svetofor rang), vizitlar.
  3. **Happy Toy** — hozirgi blok, prognoz, rangli progress, OCHIQ/QULF darajalar.
- **ERTALAB 10:00 — 2 karta:**
  4. **Qarz** — 50k+ barcha do'kon raqamli + jami/limit.
  5. **Vazvrat** — kunlik to'liq+qisman do'kon-do'kon (aniq sana), oylik to'liq+qisman+jami.
     **HAR KUNI yuboriladi (2026-07-13 qarori)** — kecha vazvrat bo'lmasa ham "kunlik yo'q" +
     oylik jamini ko'rsatadi (avval faqat kecha vazvrat bo'lganda yuborilardi).
- Buyruqlar: /bugun /oy /toy /qarz /vazvrat /yordam.

### Guruhga:
- Kunlik ballar reytingi (yig'indisiz, oylik yig'indi MAXFIY). Oy yakunida reveal+taqdirlash.

### Supervayzerga (liga bo'yicha, v2'da ulanadi):
- **KECHQURUN:** (1) Oylik — Agent|Strike%|Oy savdo|Prognoz|Ball(b/reja)|Toy, eng yomon strike
  yuqorida, "bugun e'tibor bering". (2) Kunlik — Agent|Bugun savdo|Ball|Toy|Kirdi/Sotdi.
- **ERTALAB:** (3) Qarz-vazvrat — Agent|Qarz|Vazvrat(oy)|Vazv%, eng katta qarz yuqorida.

### Adminga: kechki svodka (barcha agent jadvali + signallar).

---

## 6. DIZAYN (kelishilgan)

- Uslub: **Luxe Dark** (qora fon), Siribom logosi. **3 rang tamoyili:** oq/kulrang matn,
  pushti (brend/ball/KPI), yashil/qizil holat (+ sariq svetofor uchun).
- Plitka (tile) tuzilmasi, ikonkalar, bo'lim sarlavhalari fon-strip bilan.
- **Formal "SIZ"** tilida. "Prognoz" emas → "shu sur'atda davom etsangiz".
- Ismlar `display` (Bahodir, Rano — familiya emas).
- KPI% va O'sish% kunlik kartadan OLIB TASHLANDI (chalkash; o'sish oy o'rtasida noto'g'ri -% chiqaradi,
  faqat oy yakunida to'liq oy bilan hisoblanadi).

---

## 7. NIMA O'XSHADI / O'XSHAMADI (iteratsiyalar)

- ✅ **O'xshadi:** logo, qator ajratgichlar, 3 rang, plitka, formal til, Toy prognoz+qulf,
  qarz to'liq raqamli, vazvrat to'liq+qisman aniq sana bilan, ball kartada o'rin+o'zgarish banner,
  strike rate supervayzerda, "bugun kimga tegish kerak".
- ❌ **O'xshamadi (tuzatildi):** dastlab KPI/o'sish tiles chalkash edi — olib tashlandi;
  ball banner callout qilib yuborilgan edi — eski katta ko'rinishga qaytarildi + izoh;
  svetofor 50/100 edi — 70/90 ga; o'rin o'zgarishi kichik edi — katta banner; vazvrat jami
  do'kon ro'yxati bilan aralashardi — alohida katakka; ismlar familiya chiqardi — display.
- 🔑 **Asosiy tuzatishlar:** vazvrat ikki marta ayirish xatosi; status 4 (to'liq vazvrat);
  Обмен/javon chiqarish; strike rate markazga; supervayzer birlashtirilmadi (foydalanuvchi alohida xohladi).

---

## 8. QOLGAN ISH (deploy'dan oldin, Claude bajaradi)

1. ✅ **BAJARILDI (2026-07-10)** — jobs.py ga supervayzer 3 jadval ulandi: kechki job —
   oylik+kunlik, ertalabki job — qarz-vazvrat (liga bo'yicha, idempotent). DRY_RUN yoki
   supervayzer ulanmagan bo'lsa adminga. storage.chat_for_supervisor() + send_now namunaga
   ham qo'shildi. Commit 90db828.
2. ✅ **BAJARILDI (2026-07-10)** — month_end sinaldi (lokal, iyun 2026): hisob etaloniga mos
   (Bahodir 75/Rano 80/Usmonbek 19), karta to'la ham bo'sh podium ham chiroyli, confirm-oqim
   ishlaydi. run.py (oy 3-kuni 11:00) + /tasdiqla ulangan. **Topilma:** viloyat iyun podiumi
   bo'sh (hech kim rejadan +1 oshmagan — Rano aynan 80) — karta "rejadan oshgan agent yo'q"
   deб ko'rsatadi, o'sish sovrini (Maftuna) saqlanadi. Qoidaga to'g'ri.
3. **Idempotentlik/xato:** qayta ishga tushsa dublikat yo'q (sent_log — supervayzerga ham
   qo'llandi), API yotsa faqat adminga. Deploy'dan keyin jonli tekshiriladi.
4. (Ixtiyoriy) supervayzer buyruq/ulanish — hozircha DRY_RUN'da hammasi adminga.

## 9. DEPLOY + DRY_RUN REJASI

- **1-kun:** Railway Hobby plan (foydalanuvchi); `git push` (branch nazorat-bot → main yoki
  railway up); Railway 2 botni start_all.py orqali ishga tushiradi. **OGOH:** asosiy bot ham
  endi start_all.py orqali — buzilmaganini tekshirish. Bot "ishga tushdi" xabari.
- **1-3 kun:** DRY_RUN=true — hisobotlar 10:00/20:00 faqat adminga. Foydalanuvchi raqamlarni
  SalesDoctor bilan solishtiradi. Xato bo'lsa tuzatiladi.
- **4-kun:** to'g'ri bo'lsa DRY_RUN=false → agentlarga kodlar (TSH-.../TVL-...) tarqatiladi →
  agent /start → shaxsiy hisobot. Guruhga podium ulanadi.

## 10. FOYDALANUVCHIDAN KERAK

1. Railway Hobby plan (trial tugasa bot o'chadi).
2. Guruh chat ID'lari (shahar/viloyat) — podium uchun.
3. Sinov tugagach agentlarga kod tarqatish kuni.
4. (Ochiq savollar) iyun podium 1-o'rin g'olibi kim edi (ketma-ket 2 oy qoidasi uchun);
   har agent aniq qarz limiti (yoki liga standarti); supervayzerlar kimligi.

## 11. V2 (keyingi bosqich, agentlar barqaror ishlagach)

- Supervayzer to'liq ulanishi (2 kod: SPV-TSH-01, SPV-TVL-01).
- Har soatlik GPS "agent do'konga kirdi-kirmadi" nazorati (asosiy botning agent_monitor'ida mexanika bor).
- ✅ **BAJARILDI (2026-07-14) — Yangi agent / o'rindiq almashinuvi (avtomatik):**
  `Agent.start_date` (data.py: AgentSnapshot dfrom shu sanadan chegaralanadi — start_date yo'q
  agentlar O'ZGARISHSIZ). `storage.nz_agent_terms` jadval + `sync_agent_terms` har o'rindiq
  Sales Doctor ismini kuzatadi; ism o'zgarsa → start_date (oxirgi 3+ kunlik tanaffusdan keyingi
  1-savdo) + kuzatuv (1-to'liq oy oxirigacha) belgilanadi, adminга xabar. build.py DayContext
  terms'ni o'qib qo'llaydi (faqat o'qiydi); aniqlash/yozish ertalabki jobda 1 marta. Behruz
  Eshpo'latov (d0_144, Mirzo Ulug'bek, Jumagul o'rniga) yaml'da: display Behruz, observe_only,
  start_date 2026-07-10 (oylik savdo 3.5mln — toza). Auto start_date noto'g'ri bo'lsa admin
  aytadi → yaml'da to'g'rilanadi. 31 test o'tadi.

---

## 12. FOYDALI BUYRUQLAR

```bash
export PATH="/opt/homebrew/bin:$PATH"; cd ~/Desktop/salesdoc-bot
./venv/bin/python -m pytest nazorat/tests/ -q          # testlar (31 o'tishi kerak)
./venv/bin/python -c "import asyncio,logging; logging.basicConfig(level=logging.ERROR); from sync import run_sync; print(asyncio.run(run_sync('m','fast')))"  # sync
./venv/bin/python -m nazorat.send_now                  # namuna adminga yuborish
git log --oneline -15                                  # tarix
```
Railway: `railway status`, `railway logs`, `railway variables`, `railway up`.

---

## ⭐ HOZIRGI TO'LIQ HOLAT (2026-07-17 kech) — ENG YANGI, SHU YERDAN O'QI

Yangi bot Railway'da **jonli** (DRY_RUN=false), ● Online, **44 test o'tadi**. Deploy=`railway up --ci`.
Jonli bazani SSH orqali o'qish mumkin (railway-access memory: `~/.ssh/id_ed25519` + base64 usul).

**ISHLAYOTGAN funksiyalar (hammasi jonli):**
1. **Agentga** (ulangan, kod→admin "Ha"): kechki 20:10 — 3 karta (ball musobaqasi, savdo reja, Toy);
   ertalab 10:00 — qarz/vazvrat. Tugmalar. **20:10 QULFI** — bugungi natija 20:10 gacha berkitilgan.
2. **Supervayzerga** (SPV-TSH-01/TVL-01, ulangan): oylik+kunlik jadval, qarz-vazvrat + **GPS
   kunlik xulosa** (20:10) + **kunduzgi GPS trevoga** (har 20 daq, 45 daq yo'qolsa) — YANGI, ochildi.
3. **Adminга (siz)**: kechki svodka + supervayzer jadvallari nusxasi + GPS xulosa (ikkala liga) +
   HAR GPS trevoga nusxasi (`NZ_ALERTS_TO_SUPERVISORS=1`, `NZ_GPS_TO_SUPERVISORS=1`).
4. **GPS TIZIMI (2026-07-17 qurildi):** kechki jadval (1-vizit/oxirgi/jami/soxta/tez, qizil-sariq
   qatorlar, izoh bloklar) + kunduzgi trevoga (tasdiqlangan matn, 🔴/🟡, tugmalar 📞/ℹ️). Batafsil pastda.
5. **ROSTER (2026-07-17 tuzatildi):** ketgan agent (active='N') avtomatik chiqadi (Eliza d0_152);
   yangi agent ertalab adminга xabar (unknown_active_agents). Gulchehra (d0_147, Sergeli, city,
   observe, ball_plan 50, TSH-SRG-01) qo'shildi. Shahar 10 agent, viloyat 7.
6. **Guruh reyting**: HALI TO'XTATILGAN (GROUP_CITY/REGION_CHAT_ID qo'yilmagan → adminга).

**GPS sozlamalari (nz_config):** NZ_GPS_MISSING_MIN=45 (ikkala liga), RED=90, CHECK_MIN=20,
ESCALATE=30. Env: NZ_GPS_TO_SUPERVISORS=1, NZ_ALERTS_TO_SUPERVISORS=1, DRY_RUN=false.

**KEYINGI KATTA QADAM: ADMIN WEB PROGRAMMA (PWA)** — 1-BOSQICH JONLI (2026-07-18, pastga qarang).

---

## 🌐 ADMIN WEB DASTUR — 1-BOSQICH JONLI (2026-07-18)

**Foydalanuvchi 2026-07-18 "1-bosqichdan (xavfsiz)" ni tanladi → qurildi va JONLI DEPLOY qilindi.**
FAQAT O'QIYDIGAN monitoring PWA. Botlarga TEGMAYDI (bir bayt ham yozmaydi) — 44 test o'tadi.

- **URL:** https://bot-production-7a56.up.railway.app  · **PAROL:** `Tamotaka310` (Railway var
  `WEB_PASSWORD`; eski `WEB_PIN` O'CHIRILDI 2026-07-31). Parolni o'zgartirish:
  `railway variables --set "WEB_PASSWORD=YANGI"` → keyin **`railway up --ci`** (var o'zgargach
  qayta ishga tushishi SHART — `redeploy` EMAS).
- **Kirish qarori (2026-07-18):** PIN (6 xonali) · faqat admin · botlar yonida (shu Railway servisi).
- **Joylashuv:** `webadmin/` paketi (start_all.py 3-jarayon: `uvicorn webadmin.main:app --port $PORT`;
  Railway PORT=8080 berdi, `railway domain --port 8080` bilan domen). requirements: fastapi + uvicorn[standard].
- **Fayllar:** `webadmin/main.py` (FastAPI: PIN→sha256 token, /api/report /stock /agent/{id} /refresh,
  no_cache middleware, StaticFiles oxirida), `webadmin/reportdata.py` (FAQAT SELECT; nazorat
  `DayContext`+`agent_strike`+`agent_returns_month` ni qayta ishlatadi → raqamlar botlar bilan AYNAN bir xil;
  today=Asia/Tashkent UTC+5 fixed; 60s kesh), `webadmin/static/` (index.html/style.css/app.js/manifest.json
  + logo.png/icon-180/192/512, Siribom logosidan Pillow bilan generatsiya). config.py IMPORT QILINMAYDI
  (token env shart emas). db.get_conn (WAL+busy_timeout) — read-only, xavfsiz.
- **Ekranlar (5 tab + agent drill):** 🏠 Bosh (kun surati, kecha bilan farq, oylik+prognoz, signallar) ·
  📊 Savdo (reyting bugun/oy + AKB) · 🎯 Strike (eng past tepada, rangli — 2x uchun eng muhim) ·
  💳 Qarz/Vazvrat (limit% rangli) · 📦 Sklad (tez tugaydigan + ostatka). Drill: savdo reja/ball/strike/
  toy/qarzli do'konlar/vazvrat (nazorat evening_cards + morning_card dict'lari).
- **Jonli tekshirildi:** health 200, PIN 123456→kirdi, noto'g'ri PIN→401, /api/report bugungi real
  ma'lumot (18-iyul 12:00 sync: savdo 13mln, oylik 463mln, 15+2 agent). Ikkala bot ● Online (DRY_RUN=False).
- **TELEFONGA O'RNATISH:** URL'ni Safari(iPhone)/Chrome(Android)'da ochish → Ulashish/menyu →
  "Bosh ekranga qo'shish" → brauzersiz, zoomsiz kassa-uslubida ochiladi.
- **KEYINGI BOSQICHLAR (hali qurilmagan, foydalanuvchi tasdig'i bilan):**
  2-bosqich = BOSHQARUV — savdo/vizit plan qo'yish (agent_plans jadval — oson, xavfsiz yozish);
  ball plan + AGENT QO'SHISH (nazorat `load_agents()` ga qo'shimcha `nz_roster` DB overlay — YAML→baza
  KO'CHIRISH SHART EMAS, faqat 1 funksiya + 1 jadval, orqaga qaytariladi; workflow shuni tavsiya qildi).
  3-bosqich = SOZLAMALAR (rules.yaml overlay — ball shkala/sovrin/chegara).
  **MUHIM write-safety:** WEB-WRITABLE = agent_plans, settings, nz_bindings (sync tegmaydi).
  SYNC-OWNED (YOZMASLIK) = orders/order_items/stock/visits/balances/agents/products/clients/categories.

---

## 🐛 KECHKI JOB KeyError FIX (2026-07-18 kech) — ketgan agent (d0_152)

**Muammo:** 2026-07-18 kechki job (20:10) agent kartalarini yuborgach, ketgan agent **Eliza
(d0_152)** kartasini hisoblashda `KeyError: 'd0_152'` bilan QULADI → admin svodka + supervayzer
jadvallar + GPS xulosa YUBORILMADI (agentlar oldin olib ulgurgan). Ertalabki job omon qolgan
(15:00 to'liq sync Eliza active flag'ini o'zgartirgan; 10:00 da hali faol edi).
**Ildiz:** `inactive_sd_ids` ketgan agentni `snap`/`by_league` dan chiqaradi, LEKIN `dc.agents`
(YAML ro'yxati) da qoldiradi → `for ag in dc.agents: dc.snap[ag.sd_id]` sikllari (evening_job,
morning_job, `_alerts`) KeyError beradi. 17-iyul roster-fix o'sha kuni 22:10 da (evening'dan keyin)
deploy bo'lgani uchun 18-iyul birinchi qurbon.
**Fix (ILDIZ):** `build.py DayContext._load` oxirida `self.agents = [a for a in self.agents if
a.sd_id in self.snap]` — dc.agents endi snap bilan mos, barcha sikllar xavfsiz. Qo'shimcha:
jobs.py evening/morning sikllariga ham `if ag.sd_id not in dc.snap: continue` (belt-and-suspenders).
44 test o'tadi. Jonli dry-run: dc.agents=17=snap, barcha sikl (evening/morning/_alerts) fails=0.
**Yo'qolgan hisobot QAYTA YUBORILDI (foydalanuvchi ruxsati bilan, 20:54):** serverda evening_job
qayta ishga tushirildi (idempotent — agentlar qayta olmadi); admin svodka + supervayzer oylik/kunlik
(ikkala liga) + GPS (admin+supervayzer) yetkazildi (nz_sent_log tasdiqladi).
**QOLDI (task chip):** on-demand bot.py handlerlar (cmd_bugun/oy/toy/qarz/vazvrat, admin namuna) hali
`dc.snap[b["sd_id"]]` to'g'ridan-to'g'ri oladi — bog'langan agent ketib qolsa o'sha agent uchun
KeyError (nightly emas, faqat o'sha tugma). Guard + regressiya testi kerak.

---

## 🚨 FAIL-LOUD (0-BOSQICH) — JONLI 2026-07-30

2-bosqich (web boshqaruv) rejasi tuzildi va **0-bosqich bajarildi**. To'liq reja + bajarilgan ish
tafsiloti: **`webadmin/REJA-2BOSQICH.md`** (llm-council 5 maslahatchi xulosasi asosida).

**Nima o'zgardi:** har yuborish alohida `try/except` (`jobs._guard`) — bitta agent xatosi endi
admin/supervayzer/GPS ni o'ldirmaydi; natija `nz_job_run` ga yoziladi; **watchdog** kechki 20:40 /
ertalabki 10:30 da adminга bitta xabar: `✅ Agent kartalari 17/17 · Supervayzer 4/4 …` yoki
`🚨 MUAMMO · ❌ 16/17 · Jonibek: KeyError` yoki `🚨 TUGAMADI` yoki `🚨 UMUMAN ISHLAMADI`.
Yangi modul `nazorat/health.py` (sof mantiq). 61 test o'tadi. Deploy: `railway up --ci`.

**Foydalanuvchi tasdiqlagan 3 qaror (2026-07-18):** Konsul tartibi bilan qurish · haqiqiy parol
(PIN emas — web endi PUL raqamlarini o'zgartiradi) · kartalarni ajratish (DOIMIY vs MUSOBAQA).

**0.5-BOSQICH HAM BAJARILDI (2026-07-30 14:05, jonli):** `webadmin/auth.py` — uzun parol
(`WEB_PASSWORD`; eski PIN 2026-07-31 O'CHIRILDI), 30 kunlik imzolangan token, 5 xato →
progressiv blok (1→…→15 daq). `nazorat/backup.py` — kunlik 03:30 da `VACUUM INTO`+gzip → **admin Telegramiga**
(29MB → 7.6MB). Birinchi nusxa yuborildi va tasdiqlandi.
**TEST BUYRUG'I O'ZGARDI:** `./venv/bin/python -m pytest nazorat/tests/ webadmin/tests/ -q`

**✅ PAROL O'RNATILDI (2026-07-30 14:25):** `WEB_PASSWORD=Tamotaka310` (foydalanuvchi tanladi va
aytdi). Jonli tekshirildi: yangi parol 200 + `weak:false` (sariq ogohlantirish yo'qoldi), eski PIN
401. Kod'dan WEB_PIN ZAPASI OLIB TASHLANDI (`SECRET = os.getenv("WEB_PASSWORD","")`) — aks holda
parol o'chirilsa zaif PIN jimgina qayta yonardi. Railway'da `WEB_PIN=123456` var'i hali turadi
lekin KOD UNI O'QIMAYDI (o'chirish `variables delete` avtomatik deploy chaqirgani uchun
qoldirildi — keyingi qulay paytda o'chirilsin).

**⚠️⚠️ RAILWAY XATARI — 2026-07-30 da NOSOZLIK KELTIRDI (ESLAB QOL):**
`railway variables --set` (skip-deploys'siz) va `railway redeploy` **ESKI (stale) deployment**ni
ko'taradi → konteynerda `start_all.py` emas, faqat `bot.py` ishga tushdi → **nazorat bot va web
O'CHDI** (14:13–14:24, ~10 daqiqa; o'sha oynada hisobot rejalashtirilmagan edi, yo'qotish yo'q).
Belgilari: loglarda `[launcher]` va `uvicorn` qatorlari YO'Q, faqat bitta bot tokeni polling,
web 502. **TUZATISH VA QOIDA: `railway up --ci`** (manbadan). Env o'zgartirsang: `--skip-deploys`
bilan qo'y → keyin `railway up --ci`. **`railway redeploy` ISHLATMA.** Deploy'dan keyin tekshir:
3 ta `[launcher] ... ishga tushmoqda` + `Uvicorn running` + ikkala bot tokeni polling.

**✅ 1-BOSQICH BAJARILDI (2026-07-30 ~15:00, jonli, 92 test):** yangi `nazorat/roster.py` —
ro'yxatning YAGONA manbasi. Qoida: **kim bor — Sales Doctor** (`agents.active='Y'`), **YAML faqat
bezaydi**. `build.py`/`gps.py`/`monitor.py` dagi takrorlangan 3 qatorli filtr olib tashlandi →
hammasi `roster.active_agents()`. `bot.py` on-demand tugmalar `_agent_ctx` guard + `INACTIVE_MSG`
bilan himoyalandi (ulangan agent ketsa KeyError emas, tushunarli javob). Jonli: YAML 18 → faol 18,
`dc.agents==dc.snap`, GPS 10+8=18, monitor 18 — uchala yo'l bir xil ro'yxatni ko'radi.
**QOIDA (yangi kod yozganda):** agent ro'yxati kerak bo'lsa DOIM `roster.active_agents(conn)`,
`load_agents()` ni to'g'ridan-to'g'ri ISHLATMA (faqat bezash/config uchun).

**✅ 2-3-4 BOSQICHLAR BAJARILDI (2026-07-30 ~16:15, jonli, 119 test):**
- **Vazifa navbati** `nazorat/taskq.py` (`nz_jobs`): web OG'IR ish qilmaydi — navbatga yozadi,
  nazorat boti har 15s bajaradi (yagona yozuvchi). Blackout: HAR IKKI hisobot (10:00+20:10)
  atrofida sync boshlanmaydi (tez=±, to'liq=45 daq oldin). Tashlandiq 'running' vazifa 30 daqda
  tozalanadi (`reap_stale`). Xato bilan tugagan qayta urinishga to'smaydi.
- **Ulanish mantiqi** `nazorat/binding.py` (YAGONA joy): approve/reject/disconnect + resolve_code
  + `nz_bind_request` (kutilayotgan so'rov endi BAZADA, web ko'radi). Telegram tugmasi (on_bind_
  decision/on_unbind) endi shu modulni chaqiradi — ikki xil mantiq yo'q. Kod bir martalik+24soat.
- **Web boshqaruv** `webadmin/control.py` + endpointlar (/api/connections /sync /bind/*). Uzish =
  ism yozib tasdiqlash (server tekshiradi). Boshqaruv tab (⚙️): Ulanish (🟢/🔴, tasdiq/uzish) +
  Yangilash (tez/to'liq, oxirgi sync, vazifa tarixi).
- **Sync xavfsizligi kuchaytirildi (`run.py _sync_then`):** "busy" bo'lsa 6×60s kutadi; ma'lumot
  yangi bo'lsa hisobot davom etadi; `_sync_looks_stale` FAQAT o'z (nazorat) qatorini o'qiydi
  (asosiy botning 0-qatori to'g'ri hisobotni bloklamaydi) — 2026-07-15 nosozligining ildizi.
- **KRITIK BUG topildi (review) va tuzatildi:** on_text da `binding=...` lokal o'zgaruvchisi
  `binding` MODULINI bosib qo'ygan edi → agent kod yozsa AttributeError, ULANISH BUTUNLAY
  ishlamas edi. `bnd` ga o'zgartirildi + symtable static test + on_text regressiya testi.
- **Review:** 4 o'lchov × adversarial verify (43 topilma, 18 tasdiq, 25 rad) — hammasi tuzatildi
  (blackout ertalabga ham, IP oxirgi qiymat, GPS "sababi" 5daq muddat, tugma qulfi, dedupe).

**QOIDA:** yangi kod agent ro'yxati uchun `roster.active_agents(conn)`; ulanish uchun `binding.*`;
web'dan bazaga yozish uchun `taskq.enqueue` (to'g'ridan-to'g'ri emas). Test: `pytest nazorat/tests/
webadmin/tests/` (119).

**KEYINGI:** 5-bosqich = ball plan (oy varaqasi `nz_period` + `nz_agent_plan`, effective-date,
publish=muzlash) + sovrin o'chirish. **OLDIN:** `agent_plans` qarori (eski bot bilan uchinchi plan
tizimi qurmaslik). 6-bosqich = promo (`nz_promo`) + karta bo'linishi (DOIMIY vs MUSOBAQA).

---

## OXIRGI HOLAT (2026-07-14) — 🚀 OCHILDI (DRY_RUN=false, JONLI)

**2026-07-14 ~15:20 (Toshkent): LAUNCH bo'ldi.** Foydalanuvchi bir necha kun sinab, agent
akkauntidan ham tekshirib, admin hisobotlari to'g'ri chiqqanini tasdiqladi → OCHISH buyrug'ini
berdi. `railway variable set DRY_RUN=false --skip-deploys` + `railway up --ci` bilan deploy
qilindi. Log tasdiqladi: "✅ Nazorat bot ishga tushdi. DRY_RUN=False", scheduler (10:00/20:00)
started, ● Online, xato yo'q. **Endi avtomatik hisobot ULANGAN agent/supervayzerlarga boradi**
(admin emas). Bugun 20:00 — birinchi jonli avtomatik kechki hisobot. Ertaga 10:00 — qarz/vazvrat.
31 test o'tadi. Deploy usuli: **`railway up --ci`** (git push emas; commitlar lokal, branch
`nazorat-bot`). Ikkala bot start_all.py orqali sog' ishlaydi.

### 2026-07-15 (~01:00) — "20:00 QULFI" QO'SHILDI (jonli, deploy qilindi)
Foydalanuvchi qarori: bugungi natija (savdo/ball/toy) **20:00 avtomatik hisobotdan OLDIN
ko'rinmasin** — 20:00 "ochilish daqiqasi" qiziqarli bo'lsin. Kunlik savdoni agent Sales
Doctor'da baribir ko'radi; bu bot musobaqa/reyting/qayerga ketyapti uchun. bot.py:
`_today_locked()` (Asia/Tashkent < EVENING_HOUR:EVENING_MINUTE = 20:00) + `LOCKED_MSG`.
- **20:00 gacha berkitilgan** (bosганда 🔒 xabar): 📊 Bugungi natija (cmd_bugun), 🎁 Happy Toy
  (cmd_toy). 📅 Oylik ball (cmd_oy) — bugungi ball qatori yashiriladi, "jami (kechagacha)" +
  "bugungi ball 20:00 da qo'shiladi" izohi.
- **Doim ochiq:** 🕐 Kechagi natija (cmd_kecha), 💳 Qarzlar, ↩️ Vazvratlar, ❓ Yordam.
- **20:00 dan keyin:** hammasi ochiladi (avtomatik kechki hisobot ham shu payt boradi).
- Qulf faqat ON-DEMAND tugmalarга; avtomatik evening_job (jobs.py) o'zgarmadi. 31 test o'tadi.
- Qulf vaqti nz_config `NZ_EVENING_HOUR/MINUTE` dan olinadi (vaqt o'zgarsa qulf ham moslashadi).

### 2026-07-15 (~01:50) — SYNC TO'QNASHUVI TUZATILDI (jonli) 🔧
**Muammo (foydalanuvchi 4 rasm solishtirib topdi):** 14-iyul 20:00 nazorat kartalaridagi savdo
raqamlari asosiy programma (main bot admin kartalari) dan PASTROQ edi (masalan Bahodir nazorat
3 345 800 vs programma 3 433 400; Aisha 2 953 500 vs 4 327 500). Ba'zilarida ball ham kam
(Jasmina 2 vs 3, Abdulaziz 1 vs 2 — chegaradan o'tmagan).
**Aniq sabab (sync_log 14-iyul):** `20:00 nazorat_fast → orders=0` va `20:00 scheduled_fast →
orders=2044`. Asosiy bot va nazorat bot AYNAN 20:00 da bir vaqtda Sales Doctor'ga urildi; nazorat
sync BO'SH qaytdi (kontensiya). Sync guard (#1) bazani nolga tushirmadi — lekin eski 15:00
ma'lumotini qoldirdi; nazorat evening_job o'shani yubordi. Asosiy bot 2044 buyurtmani olib to'g'ri
raqamni yozdi → hozirgi baza programma bilan 100% mos (SSH orqali tekshirildi). Ildiz: `_sync_lock`
= `asyncio.Lock()` faqat BITTA jarayon ichida; ikki bot alohida jarayon (start_all.py) — bir-birini
ko'rmaydi.
**Yechim:** `nz_config.EVENING_MINUTE` 0→**10** (kechki hisobot **20:10** da). Asosiy bot 20:00
sync'ini tugatgach, nazorat yolg'iz (to'qnashuvsiz) sync qiladi → to'g'ri raqam. Qo'shimcha himoya:
nazorat sync 20:10 da yana bo'sh qaytsa ham, bazada asosiy botning 20:00 to'g'ri ma'lumoti turadi
(guard). Reveal/qulf ham EVENING_HOUR:MINUTE'dan → 20:10 (bot.py REVEAL_STR, LOCKED_MSG, cmd_oy,
ulanish xabari config'dan). Morning 10:00 O'ZGARMADI (asosiy botда 10:00 sync yo'q — to'qnashuv yo'q).
31 test o'tadi. **KUZATISH:** bugun (15-iyul) 20:10 birinchi jonli sinov — nazorat==programma
bo'lishini SSH orqali tekshirish kerak.

### 2026-07-17 — GPS KUNLIK XULOSA (1-bosqich QURILDI, jonli; 2-3 bosqich rejada)
Foydalanuvchi bilan uzoq dizayn iteratsiyasi (llm-council ham o'tkazildi — council "GPS emas,
strike rate" dedi, LEKIN foydalanuvchi real tajribasi bilan rad etdi: real-vaqt GPS nazorati
amalda ishlagan, kechki kirdi/sotdi allaqachon bor; muammo — xabar murakkabligi edi).
KELISHILGAN TIZIM: (1) kechki 20:10 GPS jadval-karta + (2) kunduzgi tezkor yo'qolish
trevogalari (matn+tugmalar) + (3) eski bot GPS matnlarini keyin o'chirish.

**1-BOSQICH QURILDI (2026-07-17 kech, deploy qilindi, 36 test o'tadi):**
- `nazorat/gps.py` — fetch_today_visits (jonli API), analyze_visits (1-vizit/oxirgi/jami/
  soxta=gps_visit=0/tez=<60s), severity (red/amber/ok), build_league_card.
- `cards.py render_gps_summary` — tasdiqlangan dizayn: logo, ustunlar 1-VIZIT(soat)/OXIRGI(soat)/
  JAMI(soni)/SOXTA(soni)/TEZ(soni), qizil/sariq qator fonlari, EMOJI IKONKA YO'Q, pastda 2 rangli
  izoh blok (SOXTA VIZIT NIMA? / TEZ VIZIT NIMA?). Muammolilar tepada (sev→susp ulush→jami).
- `jobs.py _gps_summary` — kechki 20:10 jobda, YAKSHANBA O'TKAZIB YUBORILADI, API yotsa adminga
  xabar. **Admin DOIM ikkala ligani oladi. Supervayzerlar FAQAT `NZ_GPS_TO_SUPERVISORS=1`
  bo'lganda** (hozir O'RNATILMAGAN = faqat admin sinovi). Ochish: Railway'da o'sha var=1 + redeploy.
- Chegaralar (gps.py konstantalar): tez<60s; qator qizil = 0 vizit yoki oxirgi<13:30 yoki
  tez≥50% yoki soxta≥60%; sariq = 1-vizit>10:00 / oxirgi<15:30 / soxta≥35% / tez≥25% / jami<8.
- Test yuborildi adminga (17-iyul real ma'lumot): shahar 9, viloyat 8 qator. Kutish: foydalanuvchi
  ko'rib ma'qullasa → NZ_GPS_TO_SUPERVISORS=1.
- 17-iyul REAL topilmalar: Jonibek va Burhon 0 vizit; Umarjon 41 vizit/26 tez/18 soxta;
  Xikmatilla oxirgi 12:37, 20 soxta. Soxta sonlar umuman baland — GPS o'chiq yurish ehtimoli.

**2-BOSQICH QURILDI (2026-07-17 kech, deploy, 39 test o'tadi) — kunduzgi tezkor trevoga:**
- `nazorat/monitor.py` — gps_check har `NZ_GPS_CHECK_MIN` (default 20) daqiqada (run.py
  IntervalTrigger, next_run_time=+3min deploy-restart himoyasi). Ish vaqti 09-17, yakshanba skip.
- Chegaralar: IKKALA LIGA 45 daq sariq (foydalanuvchi viloyatni ham 45 dedi), 90 daq qizil.
  Tushlik ham tutiladi. Sozlamalar nz_config: NZ_GPS_MISSING_MIN/RED_MIN/ESCALATE_MIN/CHECK_MIN.
- `storage.nz_gps_episodes` jadval: epizod = (sd_id, day, last_seen) UNIQUE — har epizod BIR marta
  ogohlantiriladi (spam yo'q), sariq→qizil upgrade'da yana bir marta. week_count (7 kun) =
  "bu hafta X-marta". ack/reason/returned/escalated ustunlar.
- Xabar: 1 agent = batafsil; bir nechta = BITTA jamlangan (eng yomoni tepada, "Eng avval X ga
  qo'ng'iroq qiling"). Har agentga tugma: "📞 <ism> — aloqaga chiqdim" (nzgps:ack:<eid>) va
  "ℹ️ Sababi" (nzgps:why:<eid> — keyingi matn sabab sifatida yoziladi, bot_data nzgps_pending).
  Ack bosilganda o'sha qator tugmalari xabardan olib tashlanadi. eid=0 = namuna tugma (demo).
- Qaytish: agent yangi vizit qilsa → "✅ qaytdi (X vaqt yo'q bo'ldi)" xabari, epizod yopiladi.
- **SINOV REJIMI:** `NZ_ALERTS_TO_SUPERVISORS` o'rnatilmagan (=0) → trevogalar FAQAT adminga,
  "[SINOV]" belgisi bilan. Eskalatsiya (qizil 30 daq javobsiz → admin) faqat jonli rejimda ishlaydi.
- Adminга 3 ta NAMUNA yuborildi (bitta/jamlangan/qaytdi formatlari, demo tugmalar bilan).
- **MATNLAR QAYTA YOZILDI (foydalanuvchi tanbeh berdi — "chunarsiz"):** qisqartma/belgi
  o'rniga TO'LIQ SODDA GAPLAR. Foydalanuvchi chatda so'zma-so'z TASDIQLADI (2026-07-17):
  "🚨 DIQQAT! X do'konlarga kirmay qo'ydi / oxirgi marta "Y" do'konida bo'lgan — u yerdan
  HH:MM da chiqib ketgan / O'shandan beri N daqiqa o'tdi. Shu vaqt ichida birorta ham do'konga
  kirmadi / Bugun jami: N ta do'konga kirgan, S so'm savdo qilgan / ⚠️ Bunday yo'qolish shu
  hafta N-marta bo'ldi / Hozir unga qo'ng'iroq qilib, qayerdaligini so'rang". Tugmalar:
  "📞 Qo'ng'iroq qildim" / "ℹ️ Uzrli sababi bor" (jamlanganda "📞 <ism> — qo'ng'iroq qildim" /
  "ℹ️ Sababi bor"). monitor.py _single_message/_batch_message. Matn o'zgartirishdan OLDIN
  foydalanuvchiga namuna ko'rsatib tasdiqlatish SHART (u shuni talab qiladi).
- **YAKUNIY FORMAT TASDIQLANDI (2026-07-17 kech, "shunday qoldirasan"):** trevoga xabarlariga
  rangli signal (🔴=90+ daq jiddiy, 🟡=45-90 ogohlantirish), qator belgilari (⏰ oxirgi joy,
  🚫 qancha yo'q, 🏪 bugungi hajm, ⚠️ takror, 📞 harakat), jamlanganda har agent orasida
  ➖➖➖ ajratgich, sarlavha 🚨🚨🚨. Sabab so'rovi: "Agent nima sababdan yo'q bo'lganini pastga
  yozib yuboring 👇 / Masalan: "Kasal bo'lib, uyiga ketgan". / Bitta xabar yozsangiz yetarli";
  javob: "✅ Sabab yozib olindi va saqlandi." BU MATNLARNI FOYDALANUVCHI RUXSATISIZ O'ZGARTIRMASLIK.
- **OCHISH (foydalanuvchi 2 bosqichni ham sinab ma'qullagach):** Railway'da
  `NZ_GPS_TO_SUPERVISORS=1` + `NZ_ALERTS_TO_SUPERVISORS=1` + redeploy — bitta qadamda ikkalasi.

**GPS SUPERVAYZERLARGA OCHILDI (2026-07-17 ~22:10):** Railway `NZ_GPS_TO_SUPERVISORS=1` +
`NZ_ALERTS_TO_SUPERVISORS=1`. monitor `_targets` o'zgardi — admin endi HAR trevoga nusxasini
oladi (faqat qizil emas; foydalanuvchi "mengaham kelaversin"). Kechki GPS jadval + kunduzgi
trevoga endi liga supervayzeriga + adminga.

**ROSTER BUG TUZATILDI (2026-07-17 ~22:10) — foydalanuvchi 2 farqni topdi:** yangi bot yaml
ro'yxati (17 agent, ~8-iyulda muzlatilgan) statik; eski bot esa jonli `agents.active='Y'`
o'qiydi. Shu sabab: (1) Eliza d0_152 KETGAN (active='N') lekin yaml'da → yangi bot uni 0 bilan
ko'rsataverardi; (2) Odilova Gulchehra d0_147 (Sergeli) YANGI faol shahar agenti (active='Y',
2.1M bugun), yaml'da YO'Q → yangi botda umuman ko'rinmaydi (na admin, na supervayzer, na GPS).
nz_agent_terms faqat MAVJUD o'rindiq ISM o'zgarishini tutadi — yangi sd_id (d0_147) ni emas.
TUZATISH: `storage.inactive_sd_ids` (active!='Y' yaml agentlar) → build.py DayContext + gps +
monitor ularni CHIQARADI (Eliza avtomatik ketdi, eski botga mos: viloyat 8→7). `storage.
unknown_active_agents` + jobs `_new_agent_alerts` (ertalab) → yaml'da yo'q faol+savdoli agentni
adminга bir marta xabar (Sklad chiqariladi). 44 test. **QOLDI:** Sergeli (d0_147) ni yaml'ga
qo'shish — foydalanuvchidan ball_plan + to'liq/observe + display so'raldi (TAXMIN QILMASLIK).
**GULCHEHRA QO'SHILDI (2026-07-17 ~22:30):** foydalanuvchi qarori — display "Gulchehra", yangi
(observe_only), ball_plan 50 (city oylik plan yaml'da allaqachon 50mln — inherit). agents.yaml:
d0_147, name "Odilova Gulchehra", area Sergeli, league city, code TSH-SRG-01 (Sales Doctor code_1c
BO'SH edi, bot uchun shablon berildi), start_date YO'Q (o'rindiq almashuvi emas, to'liq oy).
Tekshirildi: shahar reyting endi 10 agent, "Gulchehra (yangi) 3 ball 2.1M" 5-o'rin; Eliza viloyatdan
chiqdi (7). 44 test. Kelajakda to'liq ishtirokchi qilish = observe_only olib tashlash + ball_plan
saqlash. Foydalanuvchi tasdiqladi: Eliza butunlay ketgan.

**3-BOSQICH (keyin):** eski bot GPS matnlarini o'chirish (foydalanuvchi ruxsati bilan).

**MUHIM:** avtomatik hisobot faqat BOG'LANGAN (kod → admin "Ha" tasdig'i) agentga boradi;
ulanmagan agent hech narsa olmaydi. Admin: /start → 👥 Ulanganlar → kim ulangani ko'rinadi.
Guruh reyting hali TO'XTATILGAN (GROUP_CITY_CHAT_ID/GROUP_REGION_CHAT_ID Railway var qo'yilmagan →
reyting hozircha adminga tushadi). Xato bo'lsa: kod tuzatish → `railway up`; DRY_RUN'ga qaytarish
kerak bo'lsa: `railway variable set DRY_RUN=true` + `railway up`.

### 2026-07-14 QO'SHILGAN IMKONIYATLAR (hammasi jonli, 31 test o'tadi)
1. **Sync guard (sync.py):** `get_orders` BO'SH qaytsa (API timeout) eski buyurtmalar
   O'CHIRILMAYDI. Avval DELETE→INSERT bo'sh fetch'da savdoni 0 ga tushirardi ("hisobot bo'sh,
   summa yo'q" muammosi). `if order_rows:` guard bilan tuzatildi.
2. **Yangi agent AVTOMATIK (storage.nz_agent_terms):** o'rindiq Sales Doctor ismi o'zgarsa
   aniqlaydi → start_date (oxirgi 3+ kunlik tanaffusdan keyingi 1-savdo) + kuzatuv (1-to'liq oy
   oxirigacha) + adminга xabar (jobs.py `_agent_change_alerts`, ertalabki jobda). `Agent.start_date`
   (data.py: AgentSnapshot dfrom shu sanadan; start_date yo'q agentlar O'ZGARISHSIZ). Behruz
   Eshpo'latov (d0_144, Mirzo Ulug'bek, Jumagul o'rniga) agents.yaml'da: display Behruz,
   observe_only, start_date 2026-07-10. Auto sana noto'g'ri → admin aytadi → yaml'da tuzatiladi.
3. **Ertalabki ADMIN SVODKA olib tashlandi** — admin svodka (savdo jadvali) faqat 20:00.
   Ertalab 10:00: agent qarz/vazvrat + supervayzer qarz-vazvrat jadval.
4. **Ulanish = ADMIN TASDIG'I bilan** (bot.py `on_bind_decision`, `nzbind:`): agent kod yozadi →
   adminга "Ha/Yo'q" tugmasi keladi → tasdiqlasa ulanadi. Taxmin qilingan kod tasdiqsiz o'tmaydi.
   Admin `ADMIN` kodi bilan tasdiqsiz kiradi.
5. **TUGMALAR (matn buyruq o'rniga):** AGENT_KB (📊 Bugungi natija · 🕐 Kechagi natija · 📅 Oylik
   ball · 🎁 Happy Toy · 💳 Qarzlar · ↩️ Vazvratlar · ❓ Yordam). SUPERVISOR_KB (📊 Oylik jadval ·
   📋 Kunlik jadval · 💳 Qarz-vazvrat). `on_text` tugmani funksiyaga yo'naltiradi (BUTTON_HANDLERS,
   SUP_BUTTON_HANDLERS). Agent matn yozsa — "tugmalardan foydalaning". / buyruqlar zapas ishlaydi.
6. **Admin paneli:** `/start` → "👥 Ulanganlar" → har agentga **📤 Namuna yuborish** (agentning
   BOG'LANGAN chatiga kechagi to'liq to'plam; `nzsample:`) + **❌ Uzish** (`nzunbind:`).
   storage.list_bindings/unbind.
7. **Kartalarga izoh** (caption): nima + davr ("📊 Bugungi natija · 1–14 iyul"; "↩️ Vazvratlar ·
   kunlik + oylik"; "💳 Qarzdorliklar · bugungi holat").
8. **Supervayzer to'liq ishlaydi:** SPV-TSH-01/SPV-TVL-01 kod → admin tasdiqlaydi → liga jadvallari
   tugma bilan (cmd_sup_oylik/kunlik/qarz). Yangi (observe) agent supervayzer jadvalida "(yangi)"
   belgisi bilan KO'RINADI (supervisor_monthly/daily/debt endi observe_only'ni chiqarmaydi).
9. **Prezentatsiyalar (2 ta artifact, SOXTA namuna raqamlar — real maxfiy ma'lumot YO'Q):**
   - Agent: https://claude.ai/code/artifact/67cfeafd-1140-4220-892d-47ce5362f6fd
   - Supervayzer: https://claude.ai/code/artifact/5eecee16-a135-4c61-917f-1cddf91d8796
   - Generator skriptlar: scratchpad `gen_agent.py`, `gen_supervisor.py`, `gen_fake_cards.py`
     (soxta "Alisher" agent, qarz <2M, soxta do'kon/ism; haqiqiy logo base64; kodlar xiralashgan).

### KEYINGI QADAM (LAUNCH — majlisdan keyin)
1. ✅ **Raqam tekshirildi** — Husniobod aniq mos; farq faqat jonli savdo o'sishi (20:00 hisobot to'g'ri).
2. ⏸️ **Guruh reytingi HOZIRCHA to'xtatilgan** (guruh ulanmagani uchun reyting adminga keladi).
   Keyin GROUP_CITY_CHAT_ID/GROUP_REGION_CHAT_ID Railway var qo'yiladi.
3. **Kodlar tarqatiladi** — agent code_1C (agents.yaml: TSH-.../TVL-...), supervayzer SPV-TSH-01/SPV-TVL-01.
4. **Agent ulanadi:** @siribom_nazorat_bot → /start → kod → **ADMIN TASDIQLAYDI (Ha)** → tugmalar,
   /bugun bilan sinaydi (DRY_RUN'da ham on-demand ishlaydi).
5. **Hamma ulanib, joyida bo'lsa → OCHISH:** Railway'da **DRY_RUN=false** qilib **`railway up`** →
   agentlar har kuni 10:00/20:00 avtomatik hisobot oladi. (DRY_RUN: nz_config.py'dan o'qiladi,
   Railway variables'da DRY_RUN=true; uni false qilib qayta deploy.)

**Muhim:** hozir hisobotlar adminga. OCHISH = Railway'da DRY_RUN=false + `railway up`. Ochishdan
oldin agentlar DRY_RUN=true holatida ham ulanib /bugun sinay oladi (nazoratni qo'ldan chiqarmaslik).

**Keyingi chatда "DAVOM.md o'qib davom et" desa:** JONLI holat — sinov/ulanish qanday ketyapti
so'ra; agentlar ulanayotган bo'lsa admin tasdiqni kuzat; hammasi joyida bo'lsa DRY_RUN=false ga
tayyorlan. Raqam xatosi bo'lsa tuzat + `railway up`.

**TROUBLESHOOTING (saqlab qo'yilgan):** "hisobot bo'sh / summa 0" → sync guard tuzatgan (#1 yuqorida).
Lokalda takror: `run_sync('m','fast')` → `DayContext(today)` → summalar to'la. Railway sync tekshiruvi:
`railway logs | grep TO'LIQ` ("executed successfully" ko'rinishi kerak).

**JONLI BAZANI TEKSHIRISH (2026-07-15 sozlandi) — "hisobot kimga ketdi?" savoli uchun:**
Railway volume'dagi bot.db'ni SSH orqali o'qish mumkin (sent_log = kim/qachon oldi, bindings =
kim ulangan). Sozlash (bir marta qilingan): SSH kalit `~/.ssh/id_ed25519` yaratilib
`railway ssh keys add` bilan ro'yxatdan o'tkazilgan; `~/.ssh/config`ga `Host ssh.railway.com` +
`StrictHostKeyChecking accept-new`. Query (tirnoq muammosi uchun base64+exec, BITTA arg):
```bash
B64=$(base64 < script.py | tr -d '\n')
railway ssh "python3 -c 'exec(__import__(\"base64\").b64decode(\"$B64\").decode())'"
```
script.py: `sqlite3.connect("/app/data/bot.db")` → `SELECT ... FROM nz_sent_log WHERE day=?` /
`nz_bindings`. MUHIM: `railway ssh` argvni bo'sh joy bilan qo'shib remote `bash -c` ga beradi —
ko'p qatorli yoki tirnoqli payload buziladi; base64 bitta arg ishonchli. Railway log/sent_at =
Asia/Tashkent vaqti.

**LAUNCH KUZATUVI (2026-07-14 20:00, sent_log tasdig'i):** 9 SHAHAR agenti (TSH-*) ULANGAN va
hammasi 20:00 kechki hisobotni oldi (evening -> chat, 20:00:04-09). Shahar supervayzer (SPV-TSH-01)
oylik+kunlik oldi. VILOYAT (TVL-*) agentlari 0/8 ULANMAGAN — kod tarqatib ulash kerak. Viloyat
supervayzer 20:00 dan keyin ulangani uchun 14-iyulni olmadi (bugun oladi). Ertalabki 10:00 (14-iyul)
adminga ketdi (DRY_RUN hali true edi, 15:20 da false qilindi).

---

## 🌐 WEB REJASI (ADMIN PWA) — 2026-07-17 loyiha (HALI QURILMAGAN, foydalanuvchi tasdig'i kutilyapti)

**Foydalanuvchi so'rovi (2026-07-17):** telefon home-screen'iga qo'yiladigan, brauzer paneli
ko'rinmaydigan, ikki marta bosganda zoom bo'lmaydigan (kassa dasturidek) **admin web dastur** —
eski + yangi bot funksiyalaridan kelib chiqib. Web'dan: agent qo'shish, savdo+ball plan qo'yish,
savdo nazorati. Hozircha faqat ADMIN (siz) uchun; botlar parallel ishlayveradi.
**Maket artifact:** https://claude.ai/code/artifact/30502c66-353d-4309-aed3-8aa2ad9bba1d
(scratchpad `web-maket.html`). Reja qurishdan OLDIN tasdiqlanadi.

### TO'LIQ FUNKSIYA INVENTARI (workflow bilan chiqarildi — hammasi web'da bo'lishi kerak)
**ESKI BOT (salesdoc-bot, asosiy — bot.py/reports.py/agent_monitor.py/scheduler.py):**
- Savdo: kunlik/davr savdo (agent reyting + AKB), oylik savdo, TOP-20 tovar.
- Qarz: agentlar jami qarz (egasiz qarz + eski agent qoldig'i bo'limlari; qarz ketgan agentdan
  yangi faol agentga o'tadi — _CLIENT_AGENT_CTE), agent bo'yicha qarzli do'konlar.
- Vizit: agent bo'yicha vizit soni + "0 vizit" ro'yxati.
- Sklad: to'liq ostatka (kategoriya bo'yicha, kritik-birinchi, "necha kun qoldi"), tez tugaydigan
  ≤5 kun (rasm jadval).
- O'lik do'konlar: 7/14/30 kun; agent bo'yicha drill-down (oxirgi zakaz sanasi).
- Avtomatik push: 20:00 kunlik xulosa (savdo vs kecha %, tushish alerti), agent KPI kartochkalari
  (city/region/boshqa), ball jadvali; 03/12/15/20:00 sync xabari.
- GPS monitor (agent_monitor.py): 40 daq, ish vaqti, 😴yo'q/⚡tez/🏃ketma-ket/🚫GPSsiz, MD5 dedup.
- **Agent planlari (MUHIM — allaqachon BAZADA):** `agent_plans` jadval (sales_plan, visit_plan),
  admin buyruq bilan qo'yiladi. Bu YAML EMAS — web darrov yoza oladi.
- Guruh sozlash (/setgroup), qo'lda test yuborish, tez/to'liq sync.
**YANGI BOT (nazorat/):** agent kechki 3 karta (ball/plan/toy, 20:10 qulf), ertalab qarz/vazvrat;
guruh kunlik reyting; supervayzer 3 jadval (strike markazda); admin svodka; GPS kunlik xulosa +
kunduzgi trevoga; ball/podium/growth/toy/KPI; oy yakuni reveal; roster (active-flag/observe/yangi
agent aniqlash); ulanish (kod→admin tasdiq).
**DORMANT (bor lekin ko'rsatilmagan — web'da ochish mumkin):** vazvrat (eski botda hisobot yo'q),
strike rate (yangi botda bor), vizit has_order/order_summa.

### DATA MODEL (web uchun kritik — workflow chiqardi)
- Bitta ulashilgan **bot.db** (SQLite WAL, Railway `/app/data`). Sales Doctor API = FAQAT O'QISH
  (getAgent/getOrder/getVisit/getBalance/getStock/getClient/getProduct...) — QAYTA YOZIB BO'LMAYDI.
- **XAVFSIZ YOZISH (sync tegmaydi):** `agent_plans` (sales/visit plan — TAYYOR writable!),
  app-nomli `settings` kalitlari, `nz_bindings`. YAML fayllar: `agents.yaml` (roster: sd_id/display/
  area/league/code/ball_plan/observe/start_date) + `rules.yaml` (ball shkala/planlar/sovrin/KPI/limit).
- **YOZIB BO'LMAYDI (sync qayta yozadi):** agents/orders/order_items/visits/balances/stock/clients/
  products/categories. Log jadvallar (sync_log, nz_sent_log, nz_balance_history, nz_raw_cache,
  nz_agent_terms) — avtomatik.
- **ARXITEKTURA MUAMMOSI:** roster + ball_plan + business rules FAYLDA (agents.yaml/rules.yaml).
  Web ulardan tahrirlashi uchun → **0-BOSQICH: ularni BAZAGA ko'chirish** (bot bazadan o'qiydi,
  YAML zapas). Bu asosiy tayyorgarlik. `agent_plans` esa allaqachon bazada (oson yutuq).

### ARXITEKTURA (taklif)
- Backend: **FastAPI** (xarajat-bot/sklad-skaner kabi), o'sha bot.db ni o'qiydi + xavfsiz jadvallarga
  yozadi. Frontend: mobil-birinchi web sahifa. **PWA manifest** (display:standalone → brauzersiz;
  apple-mobile-web-app-capable → iPhone; viewport user-scalable=no → zoomsiz; home-screen ikonka).
- Kirish: **PIN** (xarajat-bot PIN 0316 kabi) — TASDIQLANMAGAN.
- Joylashuv: shu Railway loyihasida (botlar yonida) yoki alohida servis — TASDIQLANMAGAN.

### EKRANLAR (maketda 3 tasi): 1.Bosh(kun surati+signal) 2.Agentlar(qo'shish+plan/ball) 3.Savdo
4.GPS 5.Qarz/vazvrat 6.Sozlamalar. Bottom-nav: 🏠👥📊🕵⚙️.

### QURISH BOSQICHLARI
0. **Tayyorgarlik:** roster+rules YAML→baza (web tahrirlashi uchun). 1. **Ko'rish (read-only):**
bosh sahifa + hamma monitoring (tez, darrov foyda). 2. **Boshqaruv:** agent qo'shish/plan/ball/
liga/ketgan. 3. **Sozlamalar:** ball shkala/sovrin/chegara/ulanish.

### ➕/➖
➕ telefondan to'liq boshqaruv (mensiz agent+plan), eski+yangi bir joyda, boy ko'rinish, native his,
botlar parallel. ➖ butun dastur qurish/saqlash, xavfsizlik (PIN shart), YAML→baza tayyorgarlik,
yana bir servis, savdo "jonli emas" (sync 4x/kun).

### ⏳ TASDIQLANMAGAN 3 QAROR (foydalanuvchidan kutilyapti — qurishdan OLDIN):
1. Kirish himoyasi: PIN yetarlimi yoki parol? 2. Faqat admin (siz)mi, keyin supervayzerlargami?
3. Joylashuv: shu Railway loyihasida (botlar yonida)mi? — Javob kelgach 0-bosqichdan boshlanadi.
