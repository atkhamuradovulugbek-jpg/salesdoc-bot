# SIRIBOM NAZORAT BOT — HOLAT VA DAVOM ETISH FAYLI

> Bu fayl loyihaning to'liq holatini saqlaydi. Chat tozalangach, Claude shu faylni
> o'qib, nima qilinganini tushunib, foydalanuvchidan ruxsat so'rab davom etadi.
> Oxirgi yangilanish: 2026-07-09.

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

1. **jobs.py ga supervayzer 3 jadvalni ulash** — hozir jobs faqat agent kartalari + admin
   svodka yuboradi. Supervayzer jadvallari yozilgan (build.py + cards.py) lekin joblarga
   ulanmagan. DRY_RUN'da adminga ham yuborilsin.
2. **month_end oy yakuni jobini sinash** (reveal + /tasdiqla).
3. **Idempotentlik/xato:** qayta ishga tushsa dublikat yo'q, API yotsa faqat adminga.
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
- Yangi agent (Jumagul o'rniga): birinchi oy "kuzatuv rejimi" (observe_only).

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

**OXIRGI HOLAT:** Barcha kartalar/jadvallar foydalanuvchi bilan ko'rilib tasdiqlashga yaqin.
Bitta agent (Rano) 5 karta + bitta supervayzer (viloyat) 3 jadval to'liq yuborildi.
Keyingi qadam: qolgan ish (8-bo'lim) → deploy → 3 kun DRY_RUN sinov.
