# 📒 XULOSA — nima qildik, nima qilmoqchimiz

> **Bu fayl nima uchun?** Chat tozalansa ham hech narsa yo'qolmasin. Bu yerda: nima ishlayapti,
> nima qildik, nima buzildi va tuzatildi, nima qolgan — **sodda tilda**.
> Oxirgi yangilanish: **2026-07-31**.
>
> ### ⏭️ KEYINGI SAFAR (chat tozalangach shundan boshlanadi)
> 1. Shu faylni to'liq o'qi → foydalanuvchiga qisqa xulosa ber.
> 2. Batafsil texnik holat: `nazorat/DAVOM.md` + `webadmin/REJA-2BOSQICH.md`.
> 3. **5-bosqich (ball plan) QURILDI** — deploy qilinganmi tekshir (`railway up --ci`).
>    Keyingi ish — **6-bosqich: promo + karta bo'linishi**.
> 4. Foydalanuvchi dasturchi EMAS: ichki mexanikani tushuntirма, faqat **ko'rinadigan natijani**
>    ko'rsat, misol bilan; ruxsatsiz ish qilma.

---

## 1. HOZIR NIMA ISHLAYAPTI (3 ta narsa)

Hammasi **Railway** degan internet serverda, 24 soat, bir joyda turadi:

| # | Nima | Kim ishlatadi | Holat |
|---|---|---|---|
| 1 | **Eski bot** (salesdoc-bot) | Siz — savdo/qarz/sklad hisobotlari | ✅ ishlayapti |
| 2 | **Nazorat bot** (@siribom_nazorat_bot) | 18 agent + 2 supervayzer + siz | ✅ ishlayapti |
| 3 | **Web dastur** (telefon) | Faqat siz | ✅ ishlayapti |

**Web dastur havolasi:** https://bot-production-7a56.up.railway.app
**Parol:** `Tamotaka310` *(faqat parol; eski PIN o'chirildi)*
*(Telefonда ochib → "Bosh ekranga qo'shish" → brauzersiz ilova bo'lib ochiladi)*

**Ulanish holati (2026-07-31):** 15 ulangan (13 agent + 2 supervayzer), 5 agent ulanmagan
(Farangiz, Gulchehra, Habibulloh, Ibragimova, Rajabov). Ular kod olib ulanishi kerak.

**Bot har kuni o'zi nima qiladi:**
- **10:00** — agentlarga qarz va vazvrat kartalari
- **20:10** — agentlarga 3 karta (ball musobaqasi, savdo reja, Happy Toy), supervayzerlarga jadvallar, sizga svodka + GPS xulosa
- **Kun bo'yi (har 20 daq)** — agent yo'qolsa GPS trevogasi (tugmali: 📞 / ℹ️)
- **20:40 va 10:30** — sizga nazorat xabari: "hammasi ketdimi yoki yo'qmi" ✅
- **03:30** — bazaning zaxira nusxasi Telegramingizga ✅

---

## 2. BU SUHBATDA NIMA QILDIK (ketma-ket)

### 2.1. Web dastur qurildi (1-bosqich) ✅
Telefon uchun dastur — faqat **ko'rish** (hech narsa o'zgartirmaydi):
🏠 Bosh · 📊 Savdo · 🎯 Strike · 💳 Qarz/Vazvrat · 📦 Sklad
Har agentga bosilsa — to'liq kartasi (savdo reja, ball, Toy, qarzli do'konlar, vazvrat).
**Raqamlar botlar bilan aynan bir xil** (botning o'z hisob kodini qayta ishlatadi).

### 2.2. Katta nosozlik topildi va tuzatildi 🚨
**Muammo:** 18-iyul kechqurun hisobot **yarim** ketdi — agentlar oldi, lekin **siz, supervayzerlar va GPS xulosa olmadingiz**. Bot bu haqda hech narsa demadi — siz o'zingiz sezdingiz.
**Sabab:** ishdan ketgan agent (Eliza) ustida bot "qoqilib" qulab tushgan.
**Qilingan ish:** tuzatildi, yo'qolgan hisobotlar o'sha kuni qayta yuborildi.

### 2.3. Konsul (5 maslahatchi) bilan reja tuzildi 🏛️
Siz 5 ta katta so'rov aytdingiz (ulanish ekrani, yangilash tugmasi, ball plan, promo, oylik reja).
Buni **5 mustaqil maslahatchi** tahlil qildi. Ular bir ovozdan aytdi:
> "Boshqaruv tugmalarini berishdan **oldin** tizimni ishonchli qilish kerak."
Reja `webadmin/REJA-2BOSQICH.md` da. **Siz 3 qarorni tasdiqladingiz:** Konsul tartibi · haqiqiy parol · kartalarni ajratish.

### 2.4. Poydevor + ekranlar qurildi (0 → 4 bosqich) ✅

| Bosqich | Nima qilindi | Siz ko'rasizmi | Holat |
|---|---|---|---|
| **0** | Tizim "baqiradigan" bo'ldi — har kecha 20:40 / ertalab 10:30 da sizga nazorat xabari | Telegramda | ✅ **ishlaydi (tasdiqlandi)** |
| **0.5** | Haqiqiy parol + kunlik baza nusxasi Telegramga | Kirishda | ✅ **ishlaydi (tasdiqlandi)** |
| **1** | Agent ro'yxati bitta manbaga keltirildi — "Eliza xatosi" turi butunlay yo'q | Yo'q | ✅ |
| **2** | Tugmalar xavfsiz ishlashi uchun "navbat" tizimi | Yo'q | ✅ |
| **3** | 🟢🔴 **Ulanish ekrani** | **HA** | ✅ |
| **4** | 🔄 **Yangilash tugmasi** | **HA** | ✅ |

### 2.5. Yangi "⚙️ Boshqaruv" ekrani (siz so'ragan) ✅
- **👥 Ulanish:** yashil=ulangan / qizil=ulanmagan · kod ko'rinadi · **Uzish** (ism yozib tasdiqlash) · agent kod yuborsa **Tasdiqlash/Rad etish**
- **🔄 Yangilash:** tez (2-3 daq) yoki to'liq (10-15 daq) · oxirgi yangilash vaqti
- **Muhim:** tugma bosilganda dastur **o'zi bazaga tegmaydi** — botga vazifa beradi. Kechki/ertalabki hisobot vaqtida yangilash **avtomatik kutadi**.

---

## 3. NIMA BUZILDI VA QANDAY TUZATILDI (ochiq ro'yxat)

| Nima bo'ldi | Natija | Holat |
|---|---|---|
| Kechki hisobot yarim ketdi (ketgan agent sababli) | Siz/super/GPS olmadi | ✅ tuzatildi + qayta yuborildi |
| `railway redeploy` eski nusxani tiklab, **nazorat bot va web o'chib qoldi** | ~10 daqiqa uzilish | ✅ tuzatildi. **QOIDA: `redeploy` ishlatilmaydi, faqat `railway up --ci`** |
| Parol o'rnatgach dastur qayta ishga tushishi kerakligini bilmaganman | Sizga noto'g'ri aytdim | ✅ to'g'irladim, ochiq aytdim |
| **Kritik:** kodda xato bo'lib, **agent kod yuborsa ulanish umuman ishlamas edi** | Telefoningizga **chiqmadi** — deploy'dan oldin topildi | ✅ tuzatildi + maxsus sinov qo'yildi |
| Yana 17 ta kichik xato (tekshiruvda topildi) | Chiqmadi | ✅ hammasi tuzatildi |
| Parolni 5 marta xato kiritsa 15 daqiqa blok — **o'zingizni qulflab qo'ydingiz** | Kira olmay qoldingiz | ✅ 1 daqiqaga tushirildi (qayta urinsangiz asta uzayadi) |
| Men sizga juda ko'p texnik gap yozdim | Tushunmadingiz | ✅ endi faqat natijani ko'rsataman |
| **Ekranlarda ESKI agent ismlari turgan** — Ulanish, GPS trevogasi, ball plan. Siz "Behruz"ga ball qo'ydim deb, aslida **Ibragimovaga** qo'ygansiz | 4 o'rindiqda noto'g'ri ism | ✅ tuzatildi — ism endi **bitta joydan** keladi, hamma ekran bir xil ko'rsatadi |
| ⟳ tugmasi ball plan ekranini yangilamasdi — kompyuterdagi ish telefonda ko'rinmasdi | Chalkashlik | ✅ tuzatildi |
| Kuzatuvdagi agentga plan qo'ysangiz kartasida ko'rinmasligi aytilmagandi | "Qo'ydim, chiqmadi" | ✅ endi sariq yozuv bilan ochiq aytiladi |

---

## 4. NIMA QOLGAN (kelgusi ishlar)

### 4.1. Siz so'ragan, hali QURILMAGAN
| # | Nima | Izoh |
|---|---|---|
| ~~5~~ | ~~🎯 Ball plan qo'yish~~ | ✅ **QURILDI 2026-07-31** (7-bo'limga qarang) |
| **6** | 🎁 **Promo boshqaruvi** — Toy o'rniga boshqa mahsulot (baklava va h.k.), bir nechta mahsulot, muddat, yoki butunlay o'chirish. O'chirilsa — promo hisoboti **hech kimga bormaydi** | Keyingi ish |
| — | 📇 **Karta bo'linishi** — DOIMIY karta (savdo/qarz/vazvrat, har doim) va MUSOBAQA kartasi (ball+promo, faqat e'lon qilinganda) | 6 bilan birga |

### 4.1a. O'RINDIQ ALMASHUVI — hozirgi holat (2026-07-31)
Ekranlarda endi **haqiqiy agent** ismi, xududi va «🆕 sanadan · avval kim edi» ko'rinadi:

| Xudud | Hozir ishlaydi | Qachondan | Avval |
|---|---|---|---|
| Shayhontohur | **Habibulloh** | 01.07 | Burhon |
| Bektemir | **Rajabov** | 13.07 | Umarjon |
| Mirzo Ulugbek | **Ibragimova** | 24.07 | Behruz |
| Yangibozor+Parkent | **Farangiz** | 27.07 | Eliza |

Beshalasi + Gulchehra **kuzatuv rejimida 31.08 gacha** — ularga ball plani qo'ysangiz
saqlanadi, lekin **kartasida ko'rinmaydi** (1-sentabrdan ko'rinadi). Ekranda ochiq yozilgan.

### 4.2. Kichik ishlar
- 5 ulanmagan agentga kod berib ulash (Farangiz, Gulchehra, Habibulloh, Ibragimova, Rajabov)
- Eski botdagi GPS matnlarini o'chirish (sizning ruxsatingiz bilan)
- Guruh reytingini guruhlarga ulash (hozir sizga keladi) — guruh ID kerak

### 4.3. Hal qilinishi kerak bo'lgan savol (SAVDO plani ekrani qurilganda)
**Savdo plani ikki joyda:** eski bot bir joydan, yangi bot boshqa joydan o'qiydi.
Hal qilmasak — uchinchi tizim paydo bo'ladi va raqamlar chalkashadi.
*(Taklif: web plan yozganda ikkalasiga ham yozsin — ikki bot bir xil raqam ko'rsatadi.)*
**Muhim:** bu savol **ball planiga tegishli emas** — ball plani mustaqil edi, shuning uchun
5-bosqich shu savolsiz qurildi. Savol faqat **savdo plani** ekrani qurilganda hal qilinadi.

---

## 5. «OY VARAQASI» — 5-bosqich ✅ QURILDI (2026-07-31)

Siz so'ragan "01.08 dan yangi ball" **tayyor**. Dasturda: **⚙️ Boshqaruv → 🎯 Ball plan**

1. Yuqoridan **oyni tanlaysiz** (masalan "Avgust 2026")
2. Bahodirga **75** yozasiz (iyulda 70 edi) → qatorda `70 → 75` chiqadi, tepada "1 o'zgardi"
3. **💾 Saqlash** — bu hali **qoralama**, agentlar ko'rmaydi
4. **👀 Namuna** — bot sizga Telegramда **haqiqiy kartani** ko'rsatadi ("mana shunday ko'rinadi")
5. **📣 E'LON QILISH** → oy nomini yozib tasdiqlaysiz ("Avgust") → varaqa **muhrlanadi** 🔒
6. **1-avgustdan** agentlarga yangi ball ko'rinadi
7. **Iyul varaqasi muzlab qoladi** — iyul bonuslari keyin ham to'g'ri hisoblanadi

**Sovrinlar — ikkita alohida kalit:**
- 🏆 **Podium** (1.5 / 1 / 0.5 mln, har liga alohida)
- 📈 **O'sish sovrini** (700 ming)

Ikkalasi mustaqil, eski oylarga **ta'sir qilmaydi**.

**✏️ TUZATISH — xato qilsangiz (2026-08-06 qo'shildi).**
E'lon qilingan varaqani **oy tugamaguncha** to'g'rilash mumkin:
«✏️ Tuzatish» → o'zgartirasiz → **qayta E'LON QILISH** (majburiy!).
Avvalgi nusxa tarixga yoziladi (qachon nima e'lon qilingani yo'qolmaydi).
**Oy tugagandan keyin muzlaydi** — o'sha oy bonusi shu raqamlar bilan hisoblangan.

⚠️ Tuzatishga ochilgan paytda **o'sha oy uchun e'lon qilingan reja YO'Q** —
shuning uchun bot sizga eslatma yuboradi, qayta e'lon qilishni unutmang.

**👁 Kuzatuv rejimi OLIB TASHLANDI (2026-08-06):** yangi agent ham birinchi kunidanoq
ball planini ko'radi va sovrinda qatnashadi.

**Agar hech narsa qilmasangiz** — avvalgi plan o'z-o'zidan davom etadi. Hech narsa buzilmaydi.

Xuddi shunday promo ham bo'ladi (6-bosqich): `01.08 dan Toy o'rniga Baklava` yoki `promo yo'q`.

---

## 6. QAYERDA NIMA TURADI

| Narsa | Joy |
|---|---|
| Kod (kompyuteringizda) | `~/Desktop/salesdoc-bot` |
| Botlar + web (internetda) | Railway → loyiha `salesdoc-bot` → servis `bot` |
| Baza (hamma ma'lumot) | Railway ichida `/app/data/bot.db` + kunlik nusxa Telegramingizda |
| Agent ro'yxati/planlar | `nazorat/config/agents.yaml` va `rules.yaml` |
| Web dastur kodi | `webadmin/` |
| Parol (server seyfida) | Railway o'zgaruvchisi `WEB_PASSWORD` |

**Yangilash (deploy) buyrug'i** — faqat shu (`redeploy` EMAS):
```bash
export PATH="/opt/homebrew/bin:$PATH"; cd ~/Desktop/salesdoc-bot && railway up --ci
```

**Tekshirish (119 ta sinov):**
```bash
export PATH="/opt/homebrew/bin:$PATH"; cd ~/Desktop/salesdoc-bot && ./venv/bin/python -m pytest nazorat/tests/ webadmin/tests/ -q
```

---

## 7. QISQA JAVOB: "o'xshadimi?"

**✅ O'xshaganlar (jonli tasdiqlandi):** web dastur dizayni va raqamlari · strike ekrani ·
agent kartasi · ulanish ekrani (yashil/qizil) · **nazorat xabari (30-31 iyul: "Hammasi joyida ✅")** ·
**kunlik baza nusxasi (keldi)** · **GPS trevoga (tugmalari bilan keldi)** · Konsul rejasi.

**❌ O'xshamaganlari (va tuzatilgani):** juda ko'p texnik tushuntirish (endi yo'q) · parol qulfi
15 daqiqa (1 daqiqaga) · `redeploy` bilan botlarni o'chirib qo'yganim (endi ishlatilmaydi) ·
ulanishни buzadigan kritik xato (deploy'dan oldin topildi).

**⏳ Hali sinalmagan:** web'dan ulanishni **Tasdiqlash** (haqiqiy yangi agent kelганda) ·
web'dan **Yangilash** tugmasi (haqiqiy bosishда).

---

## 8. HOLAT
Uchala dastur ● Online · **136 test o'tadi** · nazorat/backup/GPS tasdiqlandi.
**5-bosqich (ball plan) qurildi va lokal to'liq sinaldi — serverga chiqarilishi kutilyapti.**
Chiqarilgach: `railway up --ci` (redeploy EMAS). **Keyingi: 6-bosqich (promo + karta bo'linishi).**
