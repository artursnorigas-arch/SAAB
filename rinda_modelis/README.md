# Rindu un maksas aprūpes modelis – Latvija

Interaktīva skaitliska realizācija LSB rakstam «Rinda budžetu neietaupa» (2026-11-20). Modelē ambulatoro speciālistu aprūpi:
ārstu laiks → valsts rinda → maksājošie pacienti → maksas cena → akūtā palīdzība → budžets.

**Šis nav prognozes rīks.** Tas parāda, kuri lēmumi stāvokli uzlabo un kuri pasliktina, un cik jutīgs secinājums ir pret pieņēmumiem.

## Palaišana
```bash
cd rinda_modelis
pip install -r requirements.txt
streamlit run app.py          # interaktīvā lietotne
pytest -q tests               # 23 testi: kalibrācija, fiziskie ierobežojumi, raksta tēzes, atbilstība datiem
python datu_atjauninat.py     # no jauna nolasa Eurostat un NVD datus (vajag internetu, ~1 min)
python datu_avoti.py          # avotu pieejamības pārbaude
```

## Faili
| Fails | Saturs |
|---|---|
| `params.py` | **Visi parametri ar avotu, statusu (V/A/B/C) un pamatojumu**; politikas svirras |
| `model.py` | Modeļa kodols (`calibrate`, `simulate`, `summary`, `sensitivity`) |
| `scenarios.py` | 7 gatavi scenāriji |
| `app.py` | Streamlit lietotne: svirras, rezultāti, scenāriji, jutīgums, pieņēmumi, datu pārbaude, avoti, metodika |
| `datu_atjauninat.py` | Nolasa primāros datus → `dati/verificeti_dati.json` |
| `datu_avoti.py` | Avotu saraksts, pārbaudes rezultāti, JSON-stat parseris |

## Datu pieejamība un pārbaude (2026-11-21)
| Avots | Rezultāts |
|---|---|
| **Eurostat API** (hlth_sha11_hf, hlth_sha11_hchf, hlth_rs_prs2, hlth_silc_08, demo_pjan, demo_pjanind, nama_10_gdp/pe) | **Pieejams, izmantots.** Dati līdz 2024. g. |
| **data.gov.lv → NVD** «Ambulatoro apmeklējumu skaits pa aprūpes epizodes veidiem» | **Pieejams, izmantots.** XLSX ārstu līmenī (anonimizēti), 2019–2026; apkopoti tikai agregāti |
| **VM paziņojums par 2026. g. budžetu** (LV portāls, 04.12.2025.) | **Apstiprināts:** 1,97 mljrd.; ambulatorie speciālisti 379,6 milj.; laboratorijas 62,5 milj. (atsevišķa rinda) |
| NVD **gaidīšanas rindu dati** | **Atvērtajos datos nav.** Rindu dati ir tikai rindapiearsta.lv (rezervācijas portāls; nav atļauts) |
| OECD, CSP, SPKC, FM | Atbild, bet nav izmantoti (Eurostat dod to pašu); OECD HTML lapa atgriež 403 |
| VSAA | Nav atļauts vidē (slimības lapu dati nepārbaudīti) |

### Parametru statuss (31 parametrs)
- **V (5) – pārbaudīts:** tiešo maksājumu daļa 32 % (Eurostat 2019–2024 vidēji; 2024: 31,95 %, ES 15,1 %), brīvprātīgā apdrošināšana 5 %, ārstu skaits nemainīgs (6 391 → 6 360, 2022–2024), valsts apjoms nemainīgs (SAVA apmeklējumi 9,65 → 9,68 → 9,65 milj., 2023–2025), darba dienas vērtība 180 EUR (IKP/nodarbinātie). Budžeta lielumi E0 un B0 apstiprināti VM paziņojumā.
- **B (3) – atvasināts:** vidējais tarifs 61 EUR (= 379,6 milj. / 6,19 milj. NVD epizožu bez laboratorijas), vajadzības izaugsme 1 %/g. (iedzīvotāji −1,0 %, novecošana +0,3 %, intensitāte +1,5 % – pēdējā ir pieņēmums), nodarbināto daļa.
- **C (21) – pieņēmumi:** visi uzvedības parametri (elastības), maksas cena (90 EUR), maksājošo daļa (25 %), gaidīšanas laiks bāzē (4 mēn.), akūtā loka stiprums u.c. Šiem Latvijā publisku datu nav; jāpieprasa NVD/VM.

### Datu atradumi, kas apstiprina raksta pamatdomu
- Gaidīšanas saraksta dēļ neapmierinātā vajadzība Latvijā: **1,8 % (2021) → 5,1 % (2024)**, ES 1,4 %; zemākajā ienākumu kvintilī 6,8 %.
- Ambulatorajā aprūpē pacienti paši sedz **49 %** izdevumu (≈ 449 milj. EUR), valsts 42 % (≈ 386 milj. EUR); ES: 20 % / 74 %.
- Valsts apmaksātais apjoms nemainīgs, bet ārstu skaits ar valsts SAVA darbu aug 5 407 → 5 733 (galvu skaitā): vairāk ārstu dala to pašu kvotu.

## Galvenie pieņēmumi (pilns saraksts – `params.py` un cilne «Pieņēmumi»)
1. **Viens agregēts «vidējais specialists»** – nav datu pa specialitātēm.
2. **Reālās cenas, bāzē finansējums un apjoms nemainīgi** – atbilst NVD datiem 2023–2025.
3. **Bāzes gads ir līdzsvarā** (kalibrācija no E0, τ0, W0, φ0); novirzi rada vajadzības izaugsme (1 %/g.), ienākumi (2,5 %/g.).
4. **`eta` = 0,6** (ārsta laika reakcija uz tarifu) – Biglaiser & Ma (2007) pamato virzienu, nevis lielumu. Visneskaidrākais un svarīgākais.
5. **`p0` = 90 EUR un attiecība τ0/p0 = 0,68** – privāto cenu vidējais nav publiski pieejams.
6. **Rinda stabilizējas ar atstāšanu** (`h_ab`); bez tā rinda modelī aug neierobežoti.
7. **Akūtais loks** (`delta` 2 %, `c_ac` 2500 EUR) – tīri pieņēmumi; Russell (2009), Chandra u.c. (2010): ietaupījums sedz tikai daļu izmaksu.
8. **Darba zaudējumi** (`ell`) – ilustratīvi; Latvijas novērtējuma nav.

## Ko modelis rāda ar noklusētajiem pieņēmumiem (10 gadi)
Mehānisma ilustrācija, nevis prognoze. Izmaiņas pret «finansējums nemainīgs» (sabiedriskās izmaksas = valsts + pacienti + darba zaudējumi, uzkrāti, milj. EUR):

| Scenārijs | Gaidīšana beigās | Saistošais | Δ sabiedr. izmaksas |
|---|---|---|---|
| Bāze (nemainīgs finansējums) | 6,3 mēn. (no 4) | kvota | – |
| −10 % tarifs un apjoms | 9,2 | kvota | +370 (ietaupījums budžetā −598, bet pacientu +338 un darba +631) |
| Tikai tarifs +40 % | 5,3 | kvota → ārsti | +1 624 |
| Tikai apjoms +15 % | 5,1 | **ārstu kapacitāte** | **−408** |
| Tarifs + apjoms | 5,0 | ārstu kapacitāte | +1 302 |
| + administratīvais slogs −5 pp | 4,2 | ārstu kapacitāte | +1 207 |
| Daudzgadu plāns (+ ikgadēja izaugsme, jauni ārsti pēc 5 g.) | 3,0 | ārstu kapacitāte | +1 391 |

**Ko tas apstiprina:** bāzē abi loki darbojas (maksājošo daļa 25 → 32 %, maksas cena +20 %); tikai tarifs – kvota ierobežo; tikai apjoms – kvota paliek neizmantota, ārstu kapacitāte ierobežo; samazinājums budžetā rāda ietaupījumu, bet izmaksas pāriet uz pacientiem un darbaspēku; ieguldījums nāk pirms ieguvuma; papildu nauda neatmaksājas ar akūtās palīdzības ietaupījumu vien.

**Ko tas NEapstiprina (svarīgi):** ar šiem pieņēmumiem **«tikai apjoms» ir sabiedriski izdevīgāks nekā «tarifs + apjoms»**. Iemesls: ārstu pāreja uz valsts darbu sašaurina nelielo maksas segmentu (25 % no laika), tāpēc maksas cena kāpj par ~45 % un daļēji izšķīdina tarifa pievilcību; tarifa +40 % maksā ≈ 150 milj. EUR gadā. Tarifa ieguvums kļūst lielāks, ja `eta` ir augsts vai ja ārstu laiks ir jutīgāks pret relatīvo atalgojumu; ar `ell` = 5 dienām kombinētais scenārijs kļūst neitrāls. Tas ir tieši tas, ko jāpārbauda ar NVD/VM datiem par ārstu ieņēmumiem valsts un privātajā sektorā. Raksta tēze par abu ierobežojumu vienlaicīgu risināšanu ir apstiprināta kā *mehānisms*, bet ne kā *izmaksu efektivitātes* secinājums.

## Ierobežojumi
Nav kalibrēts pret vēsturiskām rindu laika rindām (tādu publiski nav); nav specialitāšu un reģionu; neietver primāro aprūpi, zāles un stacionāru; ienākumu nevienlīdzība (zemākajā kvintilī 6,8 % neapmierināti rindas dēļ, augstākajā 2,7 %) nav modelēta; ambulatoro maksas izdevumu 449 milj. EUR Eurostat nesadala specialistiem un zobārstniecībai.
