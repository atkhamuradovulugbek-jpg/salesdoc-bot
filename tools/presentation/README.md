# Prezentatsiya generatori (oktyabr-2026 dizayni)

Bir buyruq bilan har oy uchun **xuddi o'sha dizayn, animatsiyalar, logo (4-variant «nur halqasi»),
strelkalar** bilan yangi web-prezentatsiya yasaydi. Natija `webadmin/presentations/<slug>.html` ga
yoziladi va admin panelda `/p/<slug>` havolasida parol bilan ochiladi.

## Ishga tushirish

```bash
# eng yangi ma'lumot — server bazasidan faqat o'qib (railway ssh, mode=ro; serverga hech narsa yozilmaydi)
./venv/bin/python -m tools.presentation build --start 2026-11-01 --end 2026-11-15 \
      --region shahar --slug noyabr-2026 --from-server

# viloyat
./venv/bin/python -m tools.presentation build --start 2026-11-01 --end 2026-11-15 \
      --region viloyat --slug noyabr-2026-viloyat --from-server
```

| Parametr | Ma'nosi |
|---|---|
| `--from-server` / `--db PATH/bot.db` | ma'lumot manbai (bot bazasi Sales Doctor bilan avtomatik sinxron) |
| `--region shahar\|viloyat` | liga (aksiya stavkasi: shahar 5 000 / 6 667, viloyat 4 000 / ≈5 333 — botdagi kabi) |
| `--slug` yoki `--out` | natija fayli; mavjud faylni `--force`'siz bosib yozmaydi |
| `--overrides F.yaml` | qo'lda matnlar (pastga qarang) |
| `--prognoz-days` | `calendar` (standart, oyning haqiqiy ish kunlari) yoki son (masalan 26) |
| `--label` | muqova yorlig'i (standart: `1-YARIM OY`, oy oxirida `OY YAKUNI`) |

So'ng: sahifani ko'rib chiqing → commit → xavfsiz deploy (20:00–22:10 dan tashqari).
Ikki prezentatsiyani solishtirish: `./venv/bin/python -m tools.presentation.validate ESKI.html YANGI.html`.

## Tuzilishi

- `render.py` — model → HTML. `template/` (CSS, JS, fon, logo, ikonkalar) tasdiqlangan `oktyabr-2026.html`
  dan olingan; `render(fromhtml(oktyabr-2026)) == oktyabr-2026` **baytma-bayt** (testda tekshiriladi).
- `compute.py` — bot bazasidan model hisoblaydi (formulalar pastda).
- `fromhtml.py` — HTML → model (validatsiya va test uchun). `validate.py` — katakma-katak solishtirish.
- `config.yaml` — reyting koeffitsiyentlari, aksiya boshlanishi, prognoz kunlari, qisqa ismlar, o'rindiq tarixi.

## Formulalar (asl manba: Cowork sessiyasi, 2026-10-13, oktyabr 1–12 shahar taqdimoti)

Umumiy: **savdo** = `total_after_discount`, status 1,2,3 (yangi+jo'natilgan+yetkazilgan), qaytim AYIRILMAYDI
(asl slayd kabi). **O'tgan oy yakuni** = o'tgan to'liq oy, faqat yetkazilgan (status 3). **Ish kuni** — yakshanba dam.
**Tashrif / buyurtma** — `visits` (visited / has_order). Kunlik reja — `rules.yaml` (shahar 2 000 000, viloyat 2 310 000),
oylik shaxsiy plan — `rules.yaml` (50 / 60 mln).

| Slayd | Ko'rsatkich | Formula |
|---|---|---|
| Muqova | Savdo · prognoz · o'tgan oy | Σ agentlar; prognoz = Σ agent prognozi; % = prognoz ÷ o'tgan oy − 1 |
| 1 Plan | Prognoz | davr savdosi × M ÷ o'tgan ish kunlari (M = oy ish kunlari yoki `--prognoz-days`) |
|  | O'zgarish | prognoz ÷ o'tgan oy − 1; **o'syapti** = ≥ +5% |
|  | Plan % / Holat | prognoz ÷ shaxsiy plan; o'syapti+yopiladi yashil · faqat yopiladi sariq · qolgani qizil |
| 2 Kim qancha | 10 tashrifga buyurtma | buyurtma ÷ tashrif × 10 (yashil ≥5, qizil <4) |
|  | O'rtacha chek | savdo ÷ buyurtma (ming; yashil ≥250, qizil <170); o'tgan oy: yetkazilgan ÷ buyurtma |
|  | Farq | joriy − o'tgan oy (|Δ|<0.3 yoki <10 ming — kulrang) |
| 3 Reyting | Baho (10) | reja min(s ÷ (kunlik reja × kun) ÷ 1.5, 1)×4 + b10 min(b10÷7,1)×2 + aksiya min(o'rtacha÷15,1)×2 + nol max(0, 2 − nol kun); aksiyasiz hafta: (reja+b10+nol)÷8×10 |
|  | Haftalar | davr ichidagi oxirgi 2 ta TUGAGAN hafta (du–sh); to'liq hafta bo'lmasa — davrning o'zi |
|  | Yo'nalish | 2-hafta − 1-hafta ≥ 0.5 ▲ · ≤ −0.5 ▼ · aks holda = ; nol kun = savdo < kunlik reja × 0.8 |
| 4 Aksiya | Aksiya / mukofot | **bot kodi** (`aksiya_jadval`): do'kon-kun sof (summa − qaytim, status 1,2,3) ÷ 300 000 pastga; kunlik mukofot `aj.reward` |
|  | Prognoz | jami × oydagi aksiya ish kunlari ÷ o'tgan aksiya ish kunlari (oktyabr: 24 va 7) |
| 5 Kunma-kun | katak | aksiya / mukofot (ming); 15+ yashil · 10–14 sariq · 8–9 oq · qolgani kulrang |
| 6 Ozgina yetmagan | 250–299 · 8–9/13–14 · aynan 10/15 · 300–330 | do'kon-kun sof 250–299k; kunlar; 300/600/900 + 30k oralig'i ÷ do'kon-kun (≥8% qizil) |
| 7 Xulosa | 4 karta | shablon bo'yicha avtomatik matn (o'sish · aksiya · reyting · ozgina yetmagan) |
| Yakun | «N ish kuni qoldi» | oyning davrdan keyingi ish kunlari |

Yangi agent (o'rindiqda boshlanish sanasi davr ichida): `*` bilan, hisob shu sanadan, prognoz o'z ish kunlari bo'yicha,
o'tgan oy bilan solishtirilmaydi. Davrda umuman savdo/tashrif yo'q agent chiqarilmaydi.

## Qo'lda kiritiladigan narsalar

Hammasi ixtiyoriy — bermasangiz avtomatik matn chiqadi.

1. **XULOSA kartalari va yakuniy matn** — oktyabrda qo'lda yozilgan edi. O'zgartirish: `--overrides`
   (namuna: `overrides.example.yaml`).
2. **Qisqa ismlar / hudud** — `config.yaml → names` (yo'q bo'lsa Sales Doctor'dagi to'liq ism).
3. **O'rindiq tarixi** — bot o'rindiqning faqat HOZIRGI egasini saqlaydi. O'tgan davr uchun yasalayotganda o'rindiq
   keyinroq yana almashgan bo'lsa: `config.yaml → seat_history`.

## Oktyabr 1–12 (shahar) validatsiyasi

`--prognoz-days 26` bilan hozirgi `oktyabr-2026.html` bilan solishtirildi (ma'lumot: 2026-10-17 bazasi):

- **Haftalik reyting** — barcha baholar, strelkalar va tartib **mos** (farq faqat izohdagi «kuniga N aksiya»da 0.1–0.2).
- **Plan / prognoz** — tartib mos; farq 0.1–0.5 mln (Gulshoda −1.4: 7 buyurtma, 1.78 mln, keyinroq to'liq qaytimga o'tgan).
- **Kim qancha sotdi** — sentyabr qiymatlari aynan mos; oktyabr tashrif/buyurtma ~8% kam: asl Excel tashrif hisoboti
  13-oktabrni ham qamragan (bazada 1–13 okt Excel bilan deyarli bir xil: Bahodir 370/212 va 368/211).
- **Aksiya / ozgina yetmagan** — bir necha birlik kam: generator botdagi qoida bilan qaytimni ayiradi
  (asl Excel'da qaytim yo'q edi), keyinroq bekor qilingan buyurtmalar ham chiqib ketgan.
- Asl taqdimotda prognoz «× 26» edi; generator standart holda oyning haqiqiy ish kunlarini oladi (oktyabr = 27,
  bot kartalari bilan bir xil).
