# SIRIBOM NAZORAT BOT — HOLAT VA DAVOM ETISH FAYLI

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

## OXIRGI HOLAT (2026-07-14) — JONLI, DRY_RUN, LAUNCH'GA TAYYOR

Bot Railway'da ishlayapti (Hobby plan, uzluksiz). **DRY_RUN=true** — barcha AVTOMATIK hisobot
FAQAT adminga (700216613). 31 test o'tadi. Deploy usuli: **`railway up --ci`** (git push emas;
commitlar lokal, branch `nazorat-bot`). Ikkala bot start_all.py orqali sog' ishlaydi.
Foydalanuvchi BUGUN majlisda agentlarga kodlarni tarqatmoqchi.

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
