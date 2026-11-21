# Rindu un maksas aprūpes modelis – Latvija

Interaktīva skaitliska realizācija LSB rakstam «Rinda budžetu neietaupa» (2026-11-20). Modelē ambulatoro speciālistu aprūpi:
ārstu laiks → valsts rinda → maksājošie pacienti → maksas cena → akūtā palīdzība → budžets.

**Šis nav prognozes rīks.** Tas parāda, kuri lēmumi stāvokli uzlabo un kuri pasliktina, un cik jutīgs secinājums ir pret pieņēmumiem.

## Palaišana
```bash
cd rinda_modelis
pip install -r requirements.txt
streamlit run app.py        # interaktīvā lietotne
pytest -q tests             # 16 testi: kalibrācija, fiziskie ierobežojumi, raksta teorijas apgalvojumi
python datu_avoti.py        # datu avotu pieejamības pārbaude (vajag internetu)
```

## Faili
| Fails | Saturs |
|---|---|
| `params.py` | **Visi parametri ar avotu, statusu (A/B/C) un pamatojumu**; politikas svirras |
| `model.py` | Modeļa kodols (`calibrate`, `simulate`, `summary`, `sensitivity`) |
| `scenarios.py` | 7 gatavi scenāriji (bāze, samazinājums, tikai tarifs, tikai apjoms, kopā, + admin. slogs, daudzgadu plāns) |
| `app.py` | Streamlit lietotne: svirras, rezultāti, scenāriju salīdzinājums, jutīgums, pieņēmumi, avoti, metodika |
| `datu_avoti.py` | Datu avotu saraksts + Eurostat nolasītājs |

## Datu pieejamība – godīgs stāvoklis
Izstrādes sesijā **nevienu primāro avotu (Eurostat, OECD, CSP, NVD, SPKC, data.gov.lv) nevarēja atvērt**: vides tīkla politika
bloķēja serverus. Pieejama bija tikai tīmekļa meklēšana. Tāpēc:
- **Statuss A (3 parametri):** budžets 1,97 mljrd., ambulatoro speciālistu budžets 379,6 milj., tiešo maksājumu daļa 27–32 %. Atrasts atreferējumos, jāapstiprina primārajos dokumentos.
- **Statuss B (2):** darba dienas vērtība un nodarbināto daļa – kārtas novērtējums no CSP lielumiem.
- **Statuss C (pārējie):** modeļa pieņēmumi. Latvijā publiski nav: svērtais gaidīšanas laiks, vidējais tarifs uz epizodi, maksas vizīšu skaits, ārstu laika sadalījums valsts/privātajā sektorā. Tie ir jāpieprasa NVD/VM (raksts uz to arī norāda).

Pirmā prioritāte datu precizēšanai (pēc jutīguma analīzes): `eta`, `tau0`/`p0` attiecība, `W0m`, `phi0`, `delta`, `g_d`.

## Galvenie pieņēmumi un to pamatojums
Pilns saraksts ar avotiem – `params.py` un lietotnes cilne «Pieņēmumi». Būtiskākie:
1. **Viens agregēts «vidējais specialists»**, jo nav datu pa specialitātēm. Zaudē specialitāšu atšķirības.
2. **Reālās cenas, finansējums bāzē reāli nemainīgs** – atbilst raksta nosacījumam «kamēr finansējums paliek esošajā līmenī».
3. **Bāzes gads ir līdzsvarā** (kalibrācija); novirzi rada tikai vajadzības izaugsme 1,5 %/g., ienākumu 2,5 %/g., fiksēts ārstu skaits (raksts: «ārstu skaits īstermiņā nemainās»).
4. **Ārsta laika elastība `eta` = 0,6.** Biglaiser & Ma (2007) pamato virzienu, nevis lielumu. Visneskaidrākais un svarīgākais pieņēmums.
5. **Rinda stabilizējas ar atstāšanu** (`h_ab`); bez tā rinda modelī aug neierobežoti (konstatēts izstrādē).
6. **Akūtā loka stiprums `delta` = 2 % un `c_ac` = 2500 EUR** ir tīri pieņēmumi. Russell (2009) un Chandra u.c. (2010) liecina, ka ietaupījums sedz tikai daļu izdevumu – tāpēc zems.
7. **Darba zaudējumi** (`ell`, `emp`, `v_day`) ir ilustratīvi; LSB galvenais arguments (darbaspēks), bet Latvijas novērtējuma nav.

## Ko modelis rāda ar noklusētajiem pieņēmumiem (10 gadi)
Šie rezultāti ir atkarīgi no pieņēmumiem, tos jālasa kā mehānismu ilustrāciju:
- **Bāze:** gaidīšana ~4 → ~10,6 mēn., maksājošo daļa 25 → 39 %, maksas cena +39 %, akūtās hospitalizācijas ×4,9 (abi apburtie loki).
- **Tikai tarifs:** ārsti atgriežas, bet kvota ierobežo – rinda nesaīsinās (apstiprina tēzi).
- **Tikai apjoms:** kapacitāte kļūst saistošā jau 1. gadā, kvota paliek neizmantota (apstiprina tēzi).
- **Kopā (+40 % / +15 %) ar admin. sloga samazinājumu:** labākā gaidīšana vidējā termiņā; **bez daudzgadu plāna ieguvums pazūd** ap 5.–8. gadu, jo vajadzība aug un ārstu skaits nē.
- **Samazinājums:** valsts izdevumi krītas, bet tiešie maksājumi un darba zaudējumi aug vairāk (ietaupījums ir šķietams).
- **Neapstiprinās / nianse:** pie noklusētās `eta` tarifa kāpums ir dārgs attiecībā pret ārstu laika pieaugumu; «tikai apjoms» sabiedrisko izmaksu ziņā iznāk lētāks par «kopā» (jo samaksā tikai par faktiski sniegtajiem pakalpojumiem). Tas ir pamats precizēt `eta` un pārbaudīt, vai šis rezultāts noturas.
- Papildu nauda **neatmaksājas** ar akūtās palīdzības ietaupījumu vien (atbilst raksta godīgajai atruna).

## Ierobežojumi
Nav kalibrēts pret vēsturiskām rindu laika rindām; nav specialitāšu un reģionu; neietver primāro aprūpi, zāles un stacionāru; nevienlīdzība pēc ienākumiem nav modelēta.
