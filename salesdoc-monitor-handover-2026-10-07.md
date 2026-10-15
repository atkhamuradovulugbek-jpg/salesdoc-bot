# SALESDOC LOYIHASI — TO'LIQ TOPSHIRISH HUJJATI

**Sana:** 2026-10-07 · **Qamrov:** shu Claude suhbatidagi butun ish tarixi
**Fayl:** `/Users/ulugbek/Desktop/salesdoc-bot/salesdoc-monitor-handover-2026-10-07.md`

Bu hujjat **bitta** faylda saqlaydi: botlar arxitekturasi, biznes qoidalari,
shu suhbatda bajarilgan barcha ishlar (xronologik), hozirgi kod holati,
hal qilinmagan masalalar va yangi chatda davom etish uchun prompt.

> 🔒 **Maxfiy qiymat bu faylda YO'Q** — parol, token, API kalit, baza paroli,
> private key yozilmagan. Faqat *nomi* va *qayerdan olish* ko'rsatilgan.

> 📌 **Manba belgilari:** `[CHAT]` suhbatdan · `[KOD]` kodda tekshirilgan ·
> `[JONLI]` serverda/bazada tekshirilgan · `[AYTILGAN]` foydalanuvchi aytgan,
> men tekshirmadim · `[NOMA'LUM]` aniqlanmagan

---

## 0. Foydalanuvchi bilan ishlash uslubi

| Qoida | Tafsilot |
|---|---|
| IT darajasi | Dasturchi **emas** — IT ni boshidan o'rganyapti |
| Til | **Oddiy o'zbek lotin**, qisqa jumlalar |
| Tushuntirish | Do'kon misoli bilan · **bitta kichik amal** bir vaqtda |
| Natija | **Ko'rinadigan** bo'lsin: rasm yoki ochiladigan fayl |
| Taxmin | **Taqiqlanadi** — noaniq bo'lsa so'rash kerak `[CHAT]` |
| Ruxsat | Har bir o'zgarish uchun **alohida aniq ruxsat** `[CHAT]` |
| Jarayon | 1) yozma qoida → 2) tasdiq → 3) rasm → 4) alohida ruxsat bilan kod `[CHAT]` |

Foydalanuvchi bir necha marta ta'kidladi: *"taxmin qilmaysan, so'raysan"*,
*"bolaga tushuntirganday tushuntir"*, *"xech narsani buzma"*. `[CHAT]`

---

## 1. TIZIM ARXITEKTURASI

### 1.1 Bitta Railway loyihasi, uchta jarayon `[KOD]` `[JONLI]`

Loyiha papkasi: `/Users/ulugbek/Desktop/salesdoc-bot`
Railway loyihasi: **`salesdoc-bot`** → servis **`bot`** → `start_all.py` 3 ta jarayon ochadi:

| # | Jarayon | Nima |
|---|---|---|
| 1 | `bot.py` | **SalesDoc Monitor** — egasi uchun monitoring boti |
| 2 | `nazorat.run` | **Siribom Nazorat** — agentlar/supervayzerlar boti |
| 3 | `uvicorn webadmin.main:app` | Telefon web dasturi (PWA) |

Web manzili: `https://bot-production-7a56.up.railway.app` `[JONLI]`

### 1.2 SalesDoc Monitor `[KOD]`
- **Fayllari:** `bot.py`, `scheduler.py`, `reports.py`, `image_reports.py`
- **Env nomi:** `TELEGRAM_BOT_TOKEN`
- **Kirish:** kod/parol mexanizmi **yo'q** — hech kim ulanmaydi
- **Kimga yuboradi:** egasiga (admin ro'yxati) + bitta guruh (`settings.report_chat_id`)
- **Guruhda kim bor:** faqat egasi; agentlarga hisobotni **o'zi qo'lda** yuboradi `[AYTILGAN]`
- **Ekran nomi:** "SalesDoc Monitor" `[CHAT — foydalanuvchi rasmida]`
- **`@username`:** `[NOMA'LUM]`

### 1.3 Siribom Nazorat (`@siribom_nazorat_bot`) `[KOD]` `[JONLI]`
- **Fayllari:** `nazorat/` (23 modul)
- **Env nomi:** `NAZORAT_BOT_TOKEN`
- **Kirish:** agent/supervayzer **kod bilan** kiradi → admin tasdiqlaydi
- **Rollar:** `agent` · `supervisor` · `debt` · `admin` (`nz_bindings`)
- **Oxirgi o'lchovda ulanganlar:** 18 agent · 2 supervayzer · 2 qarz nazoratchisi `[JONLI]`

### 1.4 xarajat-bot — ALOHIDA LOYIHA, bu ishga aloqasi YO'Q
- `/Users/ulugbek/Desktop/xarajat-bot` · Railway **`zucchini-amazement`** `[JONLI]`
- Shaxsiy kirim/chiqim boti, Google Sheets bilan. Jadval bo'yicha yuborish yo'q.
- ⚠️ Oxirgi tekshiruvda loglarida **takroriy tarmoq xatosi** — ishlamayotganga o'xshaydi.
  **Alohida muammo**, bu suhbatda tuzatilmadi. `[JONLI]`

### 1.5 Ma'lumot manbai `[KOD]`
**Sales Doctor API V2** (faqat o'qiydi) → `sync.py` → SQLite `bot.db`
Server bazasi: `/app/data/bot.db` · Mahalliy nusxa: **17-iyulga tegishli, eski**

---

## 2. BIZNES QOIDALARI

### 2.1 Ball tizimi — HOZIR ISHLAYAPTI `[KOD]`

**Kunlik reja:** shahar **2 000 000** · viloyat **2 310 000** so'm

| Reja bajarildi | Ball |
|---|---|
| 150%+ | 4 |
| 100–149% | 3 |
| 90–99% | 2 |
| 80–89% | 1 |
| <80% | 0 |

- Savdo = sof (vazvrat ayirilgan); to'liq vazvrat (status 4) sanalmaydi
- Oylik ball = ish kunlari ballari yig'indisi; yakshanba dam
- Ball plani har agentga **qo'lda** beriladi

**Sovrinlar (har liga alohida):** podium 1-o'rin 1 500 000 · 2-o'rin 1 000 000 ·
3-o'rin 500 000 (kamida +1 oshgan; teng bo'lsa savdo hal qiladi; 1-o'rin ketma-ket
2 oy berilmaydi) · o'sish sovrini 700 000 (kamida +10%, ketma-ket 2 oy yo'q)

**Happy Toy:** oylik blok darajasiga qarab bonus (`rules.yaml` da) `[KOD]`

**KPI:** komissiya pog'onalari + plan bonusi liga bo'yicha `[KOD]`

**Qarz limiti:** shahar 3 000 000 · viloyat 4 000 000 `[KOD]`

### 2.2 AKSIYA tizimi — TASDIQLANGAN, lekin HALI ULANMAGAN

Ball tizimi o'rniga rejalashtirilgan. **Hozirgi holatda faqat namuna.**

**Birlik (tasdiqlangan 2026-10-07):** `[CHAT]`
> **BIR DO'KONning BIR KUNidagi** (Asia/Tashkent) barcha yaroqli buyurtmalari
> **avval yig'iladi** (qaytim ayirilgandan keyin), **keyin**
> `floor(do'kon_kun_sof_summa / 300 000)` = aksiya soni.

- Har buyurtmani alohida yaxlitlash — **BEKOR QILINGAN**
- Turli do'kon / turli kun **birlashmaydi** · qoldiq ertaga **o'tmaydi**
- Manfiy blok → **0**
- Agent aksiyasi = **do'kon-kun bloklari yig'indisi** (umumiy savdoni floor qilish EMAS)

**Tasdiqlangan misollar (lokal tekshiruvdan o'tgan):** `[CHAT]`

| Holat | Natija |
|---|---|
| bir do'kon/kun 150k + 150k | **1** |
| bir do'kon/kun 400k + 300k + 200k | **3** |
| ikki turli do'kon 150k dan | **0** |
| bir do'kon 200k (1-kun) + 100k (2-kun) | har kuni **0** |
| 900k asl kun − 300k qaytim | **2** |

**Qaysi buyurtmalar:** NEW + SHIPPED/OTGRUZHEN + DELIVERED, har biri **bir marta**
(`status IN (1,2,3)`). Bekor / yaroqsiz / to'liq vazvrat (`status=4`) chiqariladi.
**Qaytim** asl buyurtmadan va **asl savdo kunidan** ayiriladi — ertasi kuni qaytsa
asl kun kamayadi *(mavjud baza qoidasi, yangi siyosat emas)*. `[CHAT]` `[KOD]`

**Mukofot — SHAHAR (o'zgarmaydi):**
```
n < 10  → 0 so'm
n 10–14 → n × 5 000
n 15+   → n × (100 000 ÷ 15)
```

**Mukofot — VILOYAT (YANGI, tasdiqlangan 2026-10-07):**
```
n < 10  → 0 so'm
n 10–14 → n × 4 000
n 15+   → n × (80 000 ÷ 15)
```

⚠️ Aniq kasr bilan ko'paytirilib, **faqat oxirida bir marta** so'mga yaxlitlanadi.
`5333` ni **oldin yaxlitlab ko'paytirmang**. Tekshiruv: `15 → 80 000` ·
`16 → 85 333` · `30 → 160 000`. 4 000 **har aksiya** uchun (do'kon uchun emas).
15+ **qat'iy 80 000 emas**. `[CHAT]`

---

## 3. SHU SUHBATDAGI ISHLAR — XRONOLOGIYA

Hammasi `[CHAT]` + `[KOD]`; deploy holati `[JONLI]` tekshirilgan.

### 3.1 Ball plan — «oy varaqasi» (5-bosqich) ✅ chiqarilgan
**Muammo:** ball plani `agents.yaml` da edi — telefondan o'zgartirib bo'lmasdi,
o'zgartirilsa butun tarix o'zgarardi.

**Yechim:** `nazorat/period.py` + `nz_period` / `nz_agent_plan` jadvallari.
Qoralama tahrirlanadi → **e'lon qilinsa muzlaydi** (checksum). Hisobot **o'z
sanasiga** qarab varaqa oladi, shuning uchun eski oy bonusi o'zgarmaydi.
Ulanish nuqtasi — `roster.py` (yagona joy). Web'da **🎯 Ball plan** ekrani:
oy tanlash, har agentga raqam, 💾 Saqlash · 👀 Namuna (Telegramга haqiqiy PNG) ·
📣 E'LON QILISH (oy nomini yozib tasdiqlash). **136 test.**

### 3.2 O'rindiq almashuvi — ism nomuvofiqligi ✅ chiqarilgan
**Topilgan xato:** hisobotlar yangi agent ismini, Ulanish ekrani va GPS
trevogalari esa **eski** ismni ko'rsatardi. Foydalanuvchi "Behruz"ga ball
qo'ydim deb, aslida **Ibragimova**ga qo'ygan.

**Yechim:** bezash `roster._decorate()` da — bir joyda, hamma uchun.
Qo'shildi: xudud ko'rsatish · 🆕 belgi («27.07 dan · avval Eliza») 6 ta ro'yxatda ·
`seat_changed` / `seat_prev_name` maydonlari. **146 test.**

**Aniqlangan o'rindiqlar:** Shayhontohur (Burhon→Habibulloh→Abdurahimova) ·
Bektemir (Umarjon→Rajabov) · Mirzo Ulugbek (Behruz→Ibragimova) ·
Yangibozor+Parkent (Eliza→Farangiz) · Angren (Usmonbek→Sofiya) `[JONLI]`

### 3.3 Kuzatuv rejimi olib tashlandi ✅ chiqarilgan
Yangi agent avval 1 oy «kuzatuvda» bo'lardi — plan/sovrin qo'llanmasdi.
Foydalanuvchi qarori: **hamma barobar**, yangi agent ham birinchi kunidan
to'liq qatnashadi. `observe_until` bazada qoldi, lekin **o'qilmaydi**.

### 3.4 Yo'qolgan agent topildi ✅ chiqarilgan
**Mamatov Arthur** (`d0_153`) 5-avgustdan savdo qilayotgan, 96 do'kon
biriktirilgan, lekin `agents.yaml` da yo'q → hisobotlarda **umuman ko'rinmagan**.
Qo'shildi: Shahar ligasi, 60 ball, kod `TSH-MRB-01`.

### 3.5 O'sish sovrini uchun alohida kalit ✅ chiqarilgan
Egasi 700 minglik o'sish sovrinini bekor qildi, podium qoldi. `nz_period` ga
`growth_enabled` ustuni qo'shildi (migratsiya bilan), web'da ikkinchi kalit.
**150 test.**

### 3.6 «Tuzatish» imkoni ✅ chiqarilgan
**Muammo:** avgust varaqasi e'lon qilingach muzlab qoldi, xatoni tuzatib
bo'lmasdi. **Yechim:** oy **tugamaguncha** tuzatsa bo'ladi — «✏️ Tuzatish» →
o'zgartirish → qayta e'lon. Avvalgi nusxa `nz_period_history` ga ko'chiriladi.
Oy tugagach muzlaydi. **155 test.**

### 3.7 Test supervayzer kodi ✅ chiqarilgan
`SPV-TVL-02` — egasi supervayzer ekranini o'zi ko'rishi uchun. Avtomatik
jadvallar bu kodga **bormaydi** (`jobs.SUPERVISOR_CODES` faqat asl kodga),
shuning uchun haqiqiy supervayzer uzilmaydi.

### 3.8 «⚡ Hozirgi holat» — tez yangilash ✅ chiqarilgan
**Muammo:** supervayzerlar shikoyat qildi — jadval bosganda eski raqam
ko'rinardi (baza kuniga 6 marta yangilanardi).

**O'lchov (jonli API):** bugungi buyurtmalar **2.1s** · bugungi vizitlar **2.4s** ·
ulanish 0.7s → **~5 soniya**. Taqqos: oylik buyurtma 25s + balans 11s → hozirgi
"tez" sync 2-3 daqiqa. `[JONLI]`

**Qurilgan:** `sync.py` ga `mode="today"` · `nazorat/quick.py` (90 soniya kutish,
blackout, xato yutish) · supervayzer klaviaturasiga tugma · har 30 daqiqada
**jimgina** avtomatik (xabar yubormaydi — egasi talabi) · web ⟳ endi haqiqiy
yangilash so'raydi (`sync_today` vazifasi orqali).

**Jonli sinov:** 3.9 soniyada 113→159 buyurtma (17.9→25.7 mln). 90s kutish
ishladi. **167 test.** `[JONLI]`

⚠️ **Qurish paytida topilgan xavf:** yengil rejim ombor jadvalini
**o'chirib yuborardi** (`DELETE FROM stock` shartsiz edi). `if stock_rows:`
himoyasi qo'yildi.

### 3.9 Qarz nazoratchisi ✅ chiqarilgan
**Muammo:** dastafshiklar agentlar qarzini bilmay mahsulot berishardi.
**Jonli holat:** 19 agentdan **9 tasi limitdan oshgan**, biri 448%. `[JONLI]`

**Egasi qarorlari:** hozirgi limit qolsin · xabar **faqat nazoratchiga** ·
**faqat 100% dan oshganda**.

**Qurilgan:** `nazorat/debtwatch.py` · `nz_debt_state` (bir marta xabar) ·
`sync.py` ga `mode="debt"` (~6s) · yangi rol `debt` + `DEBT_KB` ·
kodlar `QRZ-01` / `QRZ-02` · har soat 09:05–19:05 tekshiruv · **22:00** ikkita
rasm (shahar/viloyat, «BERILMASIN / EHTIYOT / MUMKIN») · «🏪 Qarzli do'konlar»
tugmasi. **178 test.** `[JONLI]`

### 3.10 Sales Doctor paroli — ishlab chiqarish nosozligi (7-avgust) `[JONLI]`
Egasi Sales Doctor parolini almashtirgan → `KeyError: 'userId'` → 20:00 sync
yiqildi → kechki hisobotlar **ketmadi**. Bugungi ma'lumot yarim edi
(19 buyurtma / 5.1 mln, aslida 232 / 41.5 mln).

**Hal qilindi:** egasi `SALESDOC_LOGIN` va `SALESDOC_PASSWORD` ni Railway'da
yangiladi (men **parolni yozmadim** — buyruqni u o'zi bajardi).

⚠️ **Yon ta'sir:** variable o'zgarishi Railway'da avtomatik qayta chiqarishni
boshladi va **ESKI nusxani** tikladi — `/app` ichida `nazorat/` va `webadmin/`
yo'qoldi, faqat eski bot qoldi. `railway up --ci` bilan tiklandi.
Keyin kechki hisobot **qo'lda** ishga tushirildi → 19 agent + 2 supervayzer +
2 guruh + admin oldi, 0 xato. Eski botning kunlik xulosasi va guruh
kartochkalari ham qo'lda yuborildi.

**QOIDA:** variable o'zgartirilsa — **darhol `railway up --ci`**.
`railway redeploy` **ishlatilmaydi**.

### 3.11 Railway obunasi (22-avgust) `[JONLI]` — Gmail auditi
Egasi «Cancel Plan» ni to'lov tugmasi deb bosgan. Keyin to'lovlar 20 va
21-avgustda **o'tmadi**. **22-avgust 12:48** da Railway hammasini to'xtatdi
(«Customer cancelled subscription»). **12:51** da egasi to'ladi → chekda
**Hobby plan 20-avgust – 20-sentabr** bor edi → obuna tiklandi.
Uzilish **~4 daqiqa**, hech narsa yo'qolmadi (10:00 hisoboti 19 agentga ketgan).

⚠️ Karta ikki marta o'tmagani qayd etilgan — kelgusi hisoblarda e'tibor kerak.
**20-sentabrdan keyingi to'lov holati bu suhbatda tekshirilmagan.** `[NOMA'LUM]`

### 3.12 Kechki hisobot kechikishi (20:13) `[JONLI]`
**Tekshirildi:** eski bot 20:00, nazorat boti **20:10**. Job 20:10:29 →
20:14:23 = **234 soniya** (26 rasm + Telegram tezlik cheklovi). **Xato emas.**

**Lekin topildi:** 19 dan **17 agent** oldi. Ulanmaganlar: **Abdulaziz**
(`d0_130`) va **Sofiya** (`d0_140`, Angren). 25-avgustgacha 19 ta olardi,
**26-avgustdan 17 ta**. Uzish buyrug'i yozuvlarda yo'q — sabab `[NOMA'LUM]`.
Kerakli kodlar: `TSH-OLM-01`, `TVL-ANG-01`.

### 3.13 Ball tizimi hujjati `[CHAT]`
Egasi so'raviga ko'ra tashqi AI uchun promt yozildi:
`/Users/ulugbek/Desktop/salesdoc-bot/docs/BALL-TIZIMI-PROMT.txt`

### 3.14 AKSIYA moduli ✅ yozilgan, ❌ ulanmagan
`nazorat/aksiya.py` + `nazorat/config/aksiya.yaml` + `nazorat/tests/test_aksiya.py`
(45 test). O'lchovda butun to'plam **223 test** o'tgan.
Sentabr ma'lumotida tekshirildi: Husniobod eng yaxshi kuni **26** — spetsifikatsiya
bilan **aynan mos**; Bahodir 29 (spetsifikatsiyada 30).

### 3.15 Namuna rasmlar — bir necha marta qayta ishlandi `[CHAT]`
Rad etilgan variantlar va sabablari **5-bo'limda**.

---

## 4. HOZIRGI KOD HOLATI

### 4.1 ⚠️ GIT — eng muhim ogohlantirish `[JONLI]`

**Oxirgi commit: `8e3d207` — 2026-07-14.** Shundan beri **hech narsa commit
qilinmagan**: 49 ta o'zgargan/yangi fayl.

Deploy `railway up --ci` bilan bo'ladi — u **ish papkasini** yuboradi, git'ni emas.
Ya'ni **ishlab chiqarishda turgan kod faqat shu Mac'da bor**. Nusxa yo'q.

**Commit qilinmagan muhim modullar:** `aksiya.py` · `debtwatch.py` · `period.py` ·
`period_jobs.py` · `quick.py` · `roster.py` · `taskq.py` · `gps.py` · `health.py` ·
`monitor.py` · `binding.py` · `backup.py` · butun `webadmin/` · 14 ta test fayli

> Bu **hal qilinmagan xavf**. Foydalanuvchiga aytilgan emas — qaror kerak.

### 4.2 Serverda ISHLAYAPTI (chiqarilgan va tekshirilgan) `[JONLI]`
Ball plan ekrani · o'rindiq ismlari · 🆕 belgisi · kuzatuv o'chirilgani ·
Arthur · o'sish kaliti · tuzatish imkoni · `SPV-TVL-02` · ⚡ Hozirgi holat
(tugma + 30 daqiqalik avtomatik + web ⟳) · qarz nazoratchisi (tugmalar +
soatlik + 22:00) · `sync.py` ning `today` va `debt` rejimlari

### 4.3 `sync.py` — alohida aniqlik (so'ralgan)
| Savol | Javob |
|---|---|
| Manba o'zgarganmi | **HA** — `mode="today"`, `mode="debt"`, `if stock_rows:` himoyasi, `debt` rejimida bo'sh-buyurtma ogohlantirishini bostirish |
| Chiqarilganmi | **HA** — `railway up --ci`, jonli ishlayapti |
| Tasdiqlanganmi | **HA** — foydalanuvchi reja va qarorlarni tasdiqlagan (90s kutish, 30 daq avtomatik, web ⟳; qarz uchun limit/xabar/chegara) |
| Test | O'sha paytda 167 → 178 test o'tgan |
| Commit | **YO'Q** — commit qilinmagan |

### 4.4 Yozilgan, lekin ULANMAGAN
`nazorat/aksiya.py` · `nazorat/config/aksiya.yaml` · `nazorat/tests/test_aksiya.py`

⚠️ **Ular ichida hali ESKI qoida bor:**
- har buyurtmani **alohida** yaxlitlash (`units_for_order`)
- `delivered_status: 3` — **faqat yetkazilgan**
- viloyat: `min_units: 15`, tier faqat `[15, 80000/15]`

Yangi tasdiqlangan qoida (do'kon-kun + status 1,2,3 + viloyat 10/4000) **faqat
vaqtinchalik namuna skriptida**. **Integratsiya tugagan demang.**

---

## 5. NAMUNA RASMLAR (botga ulanmagan)

### 5.1 Tasdiqlangan dizayn
- Alohida 2 rasm: **10 faol shahar / 8 faol viloyat** (original `active='Y'` tanlovi;
  qo'shilib ketgan **sobiq Sherzod yo'q**)
- **To'liq ism VA hudud** — kesilmasin (kerak bo'lsa 2 qator)
- **Ustunlar:** O'rin · Agent va hudud · Bugungi savdo · Aksiya (dona) · Mukofot (so'm)
- **Ranglar:** original savdo ÷ kunlik reja qoidasi (`_ball_for_pct`):
  150%+ apelsin · 100–149 yashil · 90–99 och yashil · 80–89 sariq · <80 pushti.
  **Mukofotga qarab rang EMAS.**
- **Yo'q:** Ball · Rang · JAMI bandi · footer/formula/ogohlantirish/namuna yozuvi ·
  tagdagi bo'sh joy · yangi ikonka
- **Individual agent kartochkasi — O'ZGARMAYDI**

### 5.2 Oxirgi raqamlar (07.10.2026 keshlangan snapshot, yangilik kafolati yo'q)
| Liga | Agent | Savdo | Aksiya | Mukofot |
|---|---|---|---|---|
| Shahar | 10 | 49 689 050 | **95** | **406 667** |
| Viloyat | 8 | 28 050 200 | **56** | **176 000** |

*(Jami summalar rasmda ko'rsatilmaydi.)*

**Viloyat:** Farangiz 11→44 000 · Rano 13→52 000 · Maftuna 10→40 000 ·
Husniobod 10→40 000 · Dildora 5 · Ibrohimbek 4 · Yulduz 3 · Aisha 0 → **0 so'm**

**Shahar farqi:** oraliq namunada 49 981 100, oxirgisida 49 689 050 — farq
**292 050**, Gulshoda 4 379 200 → 4 087 150. ⚠️ Sababi **qaytim deb taxmin
qilingan, tasdiqlanmagan** — fakt demang.

### 5.3 Rad etilgan variantlar (takrorlamang) `[CHAT]`
| Variant | Nega rad etildi |
|---|---|
| Hududsiz ism | Egasi yangi agentlar ismini yodda tutolmaydi |
| Ortiqcha Sherzod | Sobiq agent, original filtrda yo'q |
| Faqat-yetkazilgan | Kechqurun deyarli nol chiqadi (277 dan 2 tasi yetkazilgan) |
| 5-oktabr ma'lumotini "bugun" deb | Egasi bugungi sanani so'ragan |
| Kesilgan sarlavha/ism | O'qilmaydi |
| JAMI va footer | Keraksiz |
| `—` belgisi | Noaniq — «0 so'm» kerak |

---

## 6. TARIX QAMROVI (coverage inventory)

| Mavzu | Manba | Hujjatda | Kamchilik |
|---|---|---|---|
| Ball plan / oy varaqasi | CHAT+KOD | 3.1, 2.1 | to'liq |
| O'rindiq almashuvi | CHAT+JONLI | 3.2 | to'liq |
| Kuzatuv rejimi | CHAT+KOD | 3.3 | to'liq |
| Arthur qo'shilishi | CHAT+JONLI | 3.4 | to'liq |
| O'sish sovrini kaliti | CHAT+KOD | 3.5 | to'liq |
| Tuzatish/reopen | CHAT+KOD | 3.6 | to'liq |
| Test supervayzer kodi | CHAT+JONLI | 3.7 | to'liq |
| Tez yangilash (`today`) | CHAT+KOD+JONLI | 3.8, 4.3 | to'liq |
| Qarz nazorati | CHAT+KOD+JONLI | 3.9 | to'liq |
| Parol nosozligi 7-avg | JONLI | 3.10 | to'liq |
| Railway obunasi 22-avg | JONLI (Gmail) | 3.11 | 20-sent keyingi to'lov **noma'lum** |
| 20:13 kechikish | JONLI | 3.12 | 2 agent uzilish sababi **noma'lum** |
| AKSIYA moduli | CHAT+KOD | 3.14, 4.4 | to'liq |
| Namuna iteratsiyalari | CHAT | 5 | to'liq |
| Happy Toy / KPI tafsiloti | KOD | 2.1 qisqa | batafsil shkala `rules.yaml` da |
| GPS nazorati | KOD | 1.3 qisqa | **batafsil yozilmagan** |
| Oy yakuni / podium hisobi | KOD | 2.1 | batafsil `month_end.py` da |
| Web dastur (5 tab) | KOD | 1.1 qisqa | **batafsil yozilmagan** |

### Yetishmayotgan tarix — ochiq aytaman
- **Bu suhbatdan OLDINGI ish** (bot qurilishi, web 1-bosqich, 2026-iyul–avgust
  boshigacha) menda **yo'q**. U `XULOSA.md`, `nazorat/DAVOM.md` va
  `webadmin/REJA-2BOSQICH.md` da saqlangan — **ularni o'chirmang**.
- Suhbatning **siqilgan (compact) qismlari** bo'lsa, ular menda to'liq emas.
- **Aniq sana/xabar oralig'ini** ko'rsata olmayman — suhbatda vaqt belgilari yo'q.
- Tiklash yo'li: shu uchta hujjat + `git log` + Railway deploy tarixi + Gmail
  (Railway/Stripe xatlari).

---

## 7. HAL QILINMAGAN MASALALAR

| # | Masala | Holat |
|---|---|---|
| 1 | **49 fayl commit qilinmagan**, oxirgi commit 14-iyul | Qaror kerak |
| 2 | 2 agent ulanmagan (Abdulaziz, Sofiya) | Kod berish kerak |
| 3 | AKSIYA yangi qoidasi modulga ko'chirilmagan | Ruxsat kutilyapti |
| 4 | Monitor jadvalidan Ball/Rang olib, Aksiya/Mukofot qo'yish | Ruxsat kutilyapti |
| 5 | Ball tizimini butunlay o'chirish | **Tasdiqlanmagan** |
| 6 | xarajat-bot xato tsiklida | Tegilmagan |
| 7 | Railway to'lovi (karta 2 marta o'tmagan) | Kuzatish kerak |
| 8 | Runtime timezone tasdiqlanmagan | `[NOMA'LUM]` |
| 9 | 6-bosqich: promo + karta bo'linishi | Rejada |

---

## 8. ULANISHLAR — tekshirilgan / aytilgan / noma'lum

### ✅ TEKSHIRILGAN
| Nima | Qanday |
|---|---|
| Kodga kirish | Fayllar o'qildi, testlar ishlatildi |
| Railway serverga kirish | `railway status` · `railway ssh` · `railway logs` |
| Baza o'qish | `/app/data/bot.db`, `mode=ro` |
| Web | `/api/health` → 200 |
| Gmail | Railway/Stripe xatlari o'qildi |
| `xarajat-bot` Railway | `railway status` → `zucchini-amazement` |

### 🗣 FOYDALANUVCHI AYTGAN (tekshirilmagan)
Monitor guruhida faqat o'zi bor · agentlarga hisobotni o'zi yuboradi

### ❓ NOMA'LUM
Monitor `@username` · `report_chat_id` guruhida kimlar · runtime timezone ·
292 050 farqining sababi · 2 agent uzilish sababi · 20-sentabrdan keyingi to'lov

---

## 9. Maxfiy ma'lumot — QAYERDAN olinadi (qiymat YO'Q)

**Env o'zgaruvchi NOMLARI:** `TELEGRAM_BOT_TOKEN` · `NAZORAT_BOT_TOKEN` ·
`SALESDOC_LOGIN` · `SALESDOC_PASSWORD` · `WEB_PASSWORD` · `DATA_DIR` · `DRY_RUN`

**Qayerdan:**
1. **Railway** → loyiha `salesdoc-bot` → servis `bot` → **Variables**
   (CLI: `railway variables`, loyiha papkasida)
2. **Mahalliy:** `/Users/ulugbek/Desktop/salesdoc-bot/.env` — **mavjud**, ichi ochilmadi

⚠️ Variable o'zgartirilsa Railway avtomatik qayta chiqaradi va **eski nusxani
tiklashi mumkin** (3.10 ga qarang). Keyin **darhol `railway up --ci`**.
**`railway redeploy` ISHLATILMAYDI.**

Boshqa credential store qidirilmadi.

---

## 10. Baza — kerakli jadvallar `[KOD]`

`orders`: `sd_id, date, status, agent_sd_id, client_sd_id, total_after_discount, total_returns`
`agents`: `sd_id, code_1c, name, active, updated_at`
`clients`: `sd_id, code_1c, name, primary_agent_sd_id, territory, updated_at`
`order_items` · `balances` · `visits` · `stock` · `sync_log` · `settings` (`report_chat_id`)

**nz_ jadvallari:** `nz_bindings` · `nz_sent_log` · `nz_balance_history` ·
`nz_month_results` · `nz_raw_cache` · `nz_agent_terms` · `nz_jobs` ·
`nz_bind_request` · `nz_job_run` · `nz_period` · `nz_agent_plan` ·
`nz_period_history` · `nz_debt_state` · `nz_gps_episodes`

**Statuslar:** `1` yangi · `2` jarayonda/yo'lda · `3` yetkazilgan · `4` to'liq vazvrat
**`total_after_discount`** — chegirmadan keyingi summa; qisman vazvrat `total_returns` da

---

## 11. Monitor hozir nima yuboradi `[KOD]`

**20:00 — ketma-ket 3 narsa:**
1. Qisqa tasdiq ("🟢 20:00 ✅…"). Sync xato bersa ⚠️ va **qolgan 2 tasi ketmaydi**
2. **Kunlik xulosa (matn):** bugungi savdo + kecha bilan foiz · vizitlar + 0 vizit
   qilganlar ismi · qarzi yuqori agentlar · o'lik do'konlar · bu oy yig'indisi
3. **Rasmlar guruhga:** har agentga individual kartochka + liga bo'yicha umumiy jadval

**Har 40 daqiqa** — agent intizomi (buzilish bo'lsagina xabar)
**03:00 / 12:00 / 15:00** — yangilash, xabar yubormaydi
**Buyruqlar:** `/start` · `/setgroup` · `/cleargroup` · `/version` — **hisobot bermaydi**

**Mavjud umumiy jadval:** O'rin · Agent · Savdo · Rang · Ball
(`_compute_ball_items`: `active='Y'` + `classify_agent`, `date=bugun`, `status IN (1,2,3)`)

---

## 12. Ish tartibi cheklovlari (oxirgi kelishuv) `[CHAT]`

- ✅ Preview **faqat lokal** chiziladi
- ❌ Railway yoki tashqariga **kod / YAML / config / skript eksport qilinmaydi**
  *(bir marta vaqtinchalik nusxa yuborilgan edi — rad etildi va tozalandi)*
- ✅ Serverdan **faqat read-only ma'lumot**
- ⚠️ Mahalliy `bot.db` **17-iyulga tegishli, eski**
- ⚠️ Mac'da DejaVu shrifti yo'q — namuna skripti o'z ichida Arial'ga yo'naltiradi;
  `image_reports.py` o'zgartirilmagan

---

## 13. Keyingi bot o'zgarishi uchun TEST REJASI *(hozir yozilmaydi)*

| # | Nimani tekshiradi |
|---|---|
| 1 | Do'kon-kun yig'indisi: 150k+150k = 1 · 400k+300k+200k = 3 |
| 2 | **300 000 chegarasi:** 299 999→0 · 300 000→1 · 599 999→1 |
| 3 | **Qaytim:** 900k−300k = 2 · asl **kun** kamayishi |
| 4 | **Status o'zgarishi:** NEW→SHIPPED→DELIVERED da **takror sanalmasligi** |
| 5 | **Kun/do'kon ajralishi:** birlashmasligi, qoldiq o'tmasligi |
| 6 | **Tier chegaralari:** shahar 9/10/14/15 · viloyat 9/10/14/15/16/30 |
| 7 | **Faol agentlar:** `active='Y'`, sobiq chiqmasligi, 10/8 soni |
| 8 | Manfiy blok → 0 · bitta do'kon/kunda turli agent |

---

## 14. Fayl manzillari

**Bu hujjat:**
`/Users/ulugbek/Desktop/salesdoc-bot/salesdoc-monitor-handover-2026-10-07.md`

**Assetlar:** `/Users/ulugbek/Desktop/salesdoc-bot/handover-assets/`

| Fayl | Nima |
|---|---|
| `namuna-aksiya-tasdiqlangan-shahar.png` | ✅ Oxirgi tasdiqlangan shahar rasmi |
| `namuna-aksiya-tasdiqlangan-viloyat.png` | ✅ Oxirgi tasdiqlangan viloyat rasmi |
| `kunlik_lokal.py` | Vaqtinchalik namuna skripti (maxfiy qiymat yo'q) |
| `orders-today.psv` · `agents-today.psv` | 07.10.2026 snapshotlari |
| `agent-kartochka.png` | Monitor individual kartochkasi — o'zgarmaydi |
| `ball-jadval-city.png` · `ball-jadval-region.png` | Monitor eski jadvali (rang namunasi) |

**Boshqa muhim hujjatlar — O'CHIRMANG:**
`XULOSA.md` (umumiy holat) · `nazorat/DAVOM.md` (texnik tarix) ·
`webadmin/REJA-2BOSQICH.md` (web bosqichlari) · `docs/BALL-TIZIMI-PROMT.txt`

> `handover-assets/` git'da kuzatilmaydi.

---

## 15. Yangi Claude chat uchun davom ettirish prompti

Quyidagi matnni **to'liq nusxalab** yangi chatga joylashtiring:

```
Men salesdoc-bot loyihasi ustida ishlayapman (Telegram botlar + telefon web
dasturi). Oldingi chat to'lgani uchun yangi chatdan davom etyapmiz.

BIRINCHI QADAM — faqat o'qish va MUHOKAMA. Kod yozish, o'zgartirish,
deploy va Telegramga yuborish YO'Q.

1. Shu faylni to'liq o'qing — butun ish tarixi shunda:
   /Users/ulugbek/Desktop/salesdoc-bot/salesdoc-monitor-handover-2026-10-07.md

2. Keyin kerak bo'lsa ko'rib chiqing:
   - /Users/ulugbek/Desktop/salesdoc-bot/handover-assets/   (tasdiqlangan rasmlar)
   - XULOSA.md, nazorat/DAVOM.md, webadmin/REJA-2BOSQICH.md  (eski tarix)
   - bot.py, scheduler.py, reports.py, image_reports.py      (Monitor)
   - nazorat/ papkasi                                        (Nazorat boti)
   - nazorat/aksiya.py, nazorat/config/aksiya.yaml           (yangi modul)

3. Menga qisqa, oddiy o'zbek tilida ayting:
   - hozir nima ishlayapti va nima hali qilinmagan
   - hal qilinmagan masalalar (ayniqsa commit qilinmagan 49 fayl)
   - keyingi qadam sifatida nimani tavsiya qilasiz

4. Keyin MEN BILAN MUHOKAMA qiling va kutib turing.

MUHIM CHEKLOVLAR:
- Men dasturchi emasman. Oddiy o'zbek lotin, qisqa jumla, do'kon misoli,
  bir vaqtda bitta kichik amal. Natija ko'rinadigan bo'lsin (rasm yoki fayl).
- Taxmin qilmang. Noaniq bo'lsa mendan so'rang.
- HECH QANDAY o'zgarish kiritmang: bot, modul, config, baza, server.
  Deploy yo'q, Telegramga xabar yo'q, botga qo'shish yo'q.
- Men har bir o'zgarish uchun ALOHIDA va ANIQ ruxsat beraman.
  Avtomatik implementatsiya boshlamang.
- Preview kerak bo'lsa faqat lokal chizing. Railway'ga kod/config/skript
  eksport qilmang. Serverdan faqat read-only ma'lumot olish mumkin.
- Parol/token/kalit qiymatlarini hech qayerga yozmang.
- Railway'da variable o'zgartirilsa — darhol `railway up --ci`.
  `railway redeploy` ishlatilmaydi.

Hujjatni o'qib bo'lgach, holatni tushuntiring va mening ko'rsatmamni kuting.
```

---

*Hujjat 2026-10-07 da yozilgan va kengaytirilgan. Bot, modul, config, baza,
server va jarayonlar o'zgartirilmagan. Deploy va Telegram xabari yo'q.*
