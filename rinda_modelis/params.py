"""Parametru reģistrs: katram lielumam – vērtība, robežas, avots, statuss un pamatojums.

Statusi:
  V – pārbaudīts primārajā avotā (Eurostat API / NVD atvērtie dati, nolasīts 2026-11-21, skat. datu_atjauninat.py
      un dati/verificeti_dati.json).
  A – atrasts publiskā avotā (meklēšanas rezultāts), bet primārais dokuments šajā sesijā
      netika atvērts, jo tīkla politika bloķēja avotu serverus. Jāapstiprina.
  B – aptuvens novērtējums, balstīts uz zināmiem lieluma rādītājiem (kārtas pārbaude).
  C – modeļa pieņēmums: Latvijā nav publisku datu vai arī lielums ir uzvedības parametrs.
      Rezultātu jutība pret to jāpārbauda (cilne «Jutīgums»).

Visi naudas lielumi ir pastāvīgās cenās (reālie euro), bāzes gads 2026.
"""
from __future__ import annotations

from dataclasses import dataclass, fields

STATUS_TEXT = {
    "V": "V – pārbaudīts primārajā avotā (Eurostat / NVD atvērtie dati)",
    "A": "A – atrasts publiskā avotā, jāapstiprina primārajā dokumentā",
    "B": "B – aptuvens novērtējums (kārtas pārbaude)",
    "C": "C – modeļa pieņēmums",
}


@dataclass(frozen=True)
class Par:
    key: str
    label: str
    unit: str
    default: float
    lo: float
    hi: float
    step: float
    group: str
    status: str
    source: str
    rationale: str
    scale: float = 1.0  # attēlošanai: 100 = rādīt procentos (modelī glabā daļskaitļus)


G_BAZE = "1. Bāzes stāvoklis (2026)"
G_SIST = "2. Sistēmas ārējā dinamika"
G_UZV = "3. Uzvedība (elastības)"
G_AKUTA = "4. Akūtā palīdzība un budžeta loks"
G_EKON = "5. Ekonomiskais ieguvums"

REGISTRY: list[Par] = [
    # ---------------- 1. Bāzes stāvoklis ----------------
    Par("E0", "Ambulatoro speciālistu konsultāciju un izmeklējumu budžets", "milj. EUR", 379.6, 200, 600, 1,
        G_BAZE, "V",
        "Veselības ministrijas paziņojums (publicēts LV portālā 04.12.2025.): 2026. g. budžetā «speciālistu konsultācijām un izmeklējumiem ambulatori – 379,6 milj. eiro». "
        "Laboratorijas izmeklējumiem ir atsevišķa rinda (62,5 milj. EUR), tāpēc šajā summā laboratorijas nav.",
        "Savstarpēja pārbaude: Eurostat SHA 2024 – valsts finansējums VISAI ambulatorajai aprūpei (HC13_23, HF1) 207 EUR uz iedzīvotāju × 1,86 milj. ≈ 386 milj. EUR, t.i. tā pati kārta. "
        "Šī ir summa, kas konkurē par ārstu laiku modeļa kodolā; visas pārējās bāzes vērtības (apjoms, pieprasījums) kalibrētas no tās."),
    Par("B0", "Kopējais valsts veselības budžets", "milj. EUR", 1970, 1500, 2500, 10,
        G_BAZE, "V",
        "Veselības ministrijas paziņojums (LV portāls, 04.12.2025.): «Veselības nozares budžets 2026. gadā būs 1,97 miljardi eiro» (papildus 42,7 milj. EUR).",
        "Savstarpēja pārbaude: Eurostat SHA 2024 valdības shēmas (HF1) 1 140 EUR uz iedzīvotāju × 1,88 milj. ≈ 2,14 mljrd. EUR (plašāka definīcija nekā budžeta nozare). "
        "Vajadzīgs tikai, lai aprēķinātu pacientu tiešo maksājumu daļu no kopējiem izdevumiem."),
    Par("oop_share0", "Pacientu tiešo maksājumu daļa kopējos veselības izdevumos (bāze)", "%", 0.32, 0.20, 0.40, 0.005,
        G_BAZE, "V",
        "Eurostat hlth_sha11_hf, HF3, Latvija: 35,1 % (2019), 31,9 % (2020), 27,0 % (2021, COVID-19 publisko izdevumu kāpums), "
        "30,7 % (2022), 35,5 % (2023), 31,95 % (2024). ES-27: 15,1 % (2024).",
        "Ņemts 2019.–2024. vidējais ≈ 32 %. Latvijas rādītājs ir vairāk nekā divreiz augstāks par ES vidējo. "
        "Šis rādītājs kalibrē «pārējos» tiešos maksājumus (zāles, zobārstniecība), kas modelī ir nemainīgi.",
        scale=100),
    Par("vhi_share0", "Brīvprātīgās apdrošināšanas daļa kopējos izdevumos", "%", 0.05, 0.0, 0.10, 0.005,
        G_BAZE, "V",
        "Eurostat hlth_sha11_hf, HF2, Latvija: 4,8 % (2019) → 5,2 % (2024); ES-27 4,6 %.",
        "Modelī nemainīga; ietekmē tikai OOP daļas aprēķina saucēju. Brīvprātīgā apdrošināšana pieaug (51 → 95 EUR uz iedzīvotāju 2019–2024).",
        scale=100),
    Par("tau0", "Vidējais valsts tarifs par vienu ambulatoro epizodi (konsultācija + izmeklējumi, bez laboratorijas)", "EUR", 61, 20, 120, 1,
        G_BAZE, "B",
        "Atvasināts: 379,6 milj. EUR (VM budžets 2026) / 6,19 milj. epizožu (NVD atvērtie dati 2025. g.: SAVA 9,43 milj. epizožu mīnus 3,24 milj. laboratorijas epizodes, kuras apmaksā no atsevišķas 62,5 milj. EUR rindas) ≈ 61 EUR.",
        "Nosaka kalibrēto apjomu V0 = E0 / τ0 ≈ 6,2 milj. epizožu, kas sakrīt ar NVD faktisko apjomu. Svarīga ir attiecība τ0/p0, nevis absolūtā vērtība. "
        "Atvasinājumā pieņemts, ka 2026. g. budžeta summa un 2025. g. apjoms ir salīdzināmi (apjoms 2023–2025 bijis nemainīgs)."),
    Par("p0", "Vidējā maksas cena par to pašu epizodi privātajā praksē", "EUR", 90, 40, 250, 1,
        G_BAZE, "C",
        "Privāto klīniku cenrāži (konsultācija ~50–90 EUR, izmeklējumi atsevišķi). Nav oficiāla vidējā rādītāja; epizodē ir arī dārgāki izmeklējumi.",
        "Attiecība τ0/p0 ≈ 0,68 nosaka, cik daudz izdevīgāk ārstam ir strādāt par maksu. Tieši šī attiecība (nevis absolūtās cenas) vada ārsta laika sadali – "
        "tas ir otrs svarīgākais nenoteiktais lielums pēc η un tam jāpārbauda ar klīniku cenrāžiem un ārstu ieņēmumu datiem."),
    Par("phi0", "Daļa epizožu, ko pacienti jau šobrīd apmaksā paši (specialisti ambulatori)", "%", 0.25, 0.05, 0.60, 0.01,
        G_BAZE, "C",
        "Nav publiskas statistikas par maksas speciālistu vizītēm. Eurostat SHA (HC13_23, 2024): ambulatorajā aprūpē 49 % izdevumu sedz pacienti paši, 42 % valsts (ES: 20 % / 74 %); šajā grupā ir arī zobārstniecība un ģimenes ārsti.",
        "Kopā ar rindas garumu nosaka sākuma ārstu laika sadali (s0). Ambulatoro izdevumu 49 % OOP daļa ir augšējā robeža šai grupai (modelī 25 % epizožu ≈ 190 milj. EUR no 449 milj. EUR visos ambulatoros OOP). "
        "Pārbaudāms ar klīniku ieņēmumu datiem.", scale=100),
    Par("W0m", "Vidējais gaidīšanas laiks valsts apmaksātai epizodei (bāze)", "mēneši", 4.0, 1, 12, 0.5,
        G_BAZE, "C",
        "NVD rindu dati: ārstniecības iestādes mēneša pārskatos uzrāda rindu dienās (ja >5 darba dienas); "
        "NVD prezentācijā (03.2025.) pacienti min reālas rindas «~5–8 mēneši». Vidēja svērta vērtība nav publicēta; NVD atvērto datu portālā (data.gov.lv) rindu datu kopas nav, rindu dati ir tikai rindapiearsta.lv.",
        "Netieša validācija (Eurostat EU-SILC): neapmierināto vajadzību daļa gaidīšanas saraksta dēļ Latvijā 1,8 % (2021) → 5,1 % (2024), ES 1,4 %; zemākajā ienākumu kvintilī 6,8 %. Reālu rindu svērto vidējo var aprēķināt no NVD mēneša rindu pārskatiem (rindapiearsta.lv/NVD atvērtie dati). "
        "4 mēneši ir piesardzīgi zemāks par pacientu minēto diapazonu."),
    Par("H0", "Ambulatorajā darbā iesaistīto speciālistu ārstu pilnas slodzes ekvivalenti", "PSE", 3000, 1500, 6000, 50,
        G_BAZE, "C",
        "Eurostat hlth_rs_prs2: praktizējošie ārsti LV 6 360 (2024); NVD datos 5 733 ārsti ar valsts apmaksātu sekundārās ambulatorās aprūpes darbu (2025, ieskaitot laboratorijas ārstus un radiologus; galvu skaits, nevis PSE).",
        "Ambulatorā PSE nav publicēta; 3000 ir ~47 % no praktizējošajiem ārstiem. Absolūtais lielums neietekmē relatīvos rezultātus (kapacitāte tiek kalibrēta uz apjomu); svarīga ir tikai "
        "izaugsmes likme g_H."),
    Par("slack0", "Valsts apmaksātās kapacitātes rezerve virs kvotas bāzes gadā", "reizes", 1.05, 1.0, 1.5, 0.01,
        G_BAZE, "C",
        "Kvalitatīvi: NVD norāda, ka rindu galvenais iemesls ir speciālistu un naudas trūkums.",
        "1,00 = kvota un kapacitāte vienlaikus saspringtas; 1,05 = kvota nedaudz stingrāka. Nosaka, kurš ierobežojums "
        "(nauda vai ārsti) kļūst saistošs pirmais – tieši to rakstā aprakstīts kā «puspasākumu» problēma."),
    Par("h_ab", "Gaidošo daļa gadā, kas atstāj valsts rindu bez apkalpošanas (bāze)", "%/gadā", 0.15, 0.0, 0.5, 0.01,
        G_BAZE, "C",
        "Nav publiskas statistikas. Mehānisms: pacients izārstējas pats, vēršas ārzemēs/privāti ārpus modeļa vai pārtrauc gaidīt.",
        "Stabilizē rindu (bez tā rinda modelī aug neierobežoti). Pieņemts, ka atstāšanas intensitāte aug proporcionāli "
        "gaidīšanas laikam. Mazāka vērtība → asāka rindu pasliktināšanās.", scale=100),
    # ---------------- 2. Sistēmas ārējā dinamika ----------------
    Par("g_d", "Medicīniskās vajadzības (nosūtījumu) izaugsme gadā", "%/gadā", 0.01, -0.02, 0.05, 0.0025,
        G_SIST, "B",
        "Sadalīts: (1) iedzīvotāju skaits −1,0 %/g. (1 878 575 → 1 860 565, 2024→2025; Eurostat demo_pjan); "
        "(2) novecošana: 65+ daļa 19,4 % (2015) → 21,9 % (2025); ar pieņēmumu, ka 65+ lieto ~2,5 reizes vairāk pakalpojumu, tas dod ≈ +0,3 %/g. uz iedzīvotāju; "
        "(3) diagnostikas un ārstēšanas intensitāte ≈ +1,5 %/g. (pieņēmums, literatūrā 1–3 %).",
        "Summa ≈ +1 %. Demogrāfija vien vajadzību samazinātu (≈ −0,4 %/g.), tāpēc rindu pieaugums nāk no diagnostikas un ārstēšanas apjoma kāpuma. "
        "Ar g_d = 0 bāzes scenārijs ir stacionārs – tāpēc šis parametrs jāskata jutīguma cilnē. Latvijā 2021.–2024. g. neapmierinātā vajadzība gaidīšanas dēļ pieauga 1,8 → 5,1 %, kas liecina par spiedienu uz rindām.", scale=100),
    Par("g_H", "Ārstu darba laika (PSE) izaugsme gadā", "%/gadā", 0.0, -0.03, 0.03, 0.0025,
        G_SIST, "V",
        "Eurostat hlth_rs_prs2: praktizējošie ārsti LV 6 391 (2022), 6 309 (2023), 6 360 (2024) – praktiski nemainīgi. "
        "(Licencēto ārstu skaits aug 9 536 → 9 952, bet tie nav aktīvi praktizējošie.)",
        "Atbilst rakstā pieņemtajam: «ārstu skaits īstermiņā nemainās». NVD dati rāda, ka ārstu skaits ar valsts apmaksātu SAVA darbu 2023→2025 pieauga 5 407 → 5 733 "
        "(≈ +3 % gadā galvu skaitā), bet apjoms palika nemainīgs – ārsti dala fiksētu apjomu, nevis palielina to.", scale=100),
    Par("g_y", "Iedzīvotāju reālo ienākumu izaugsme gadā", "%/gadā", 0.025, 0.0, 0.06, 0.0025,
        G_SIST, "C",
        "Latvijas reālā ienākumu izaugsme pēdējos gados 2–4 %.",
        "Augoši ienākumi palielina spēju maksāt un tādējādi pastiprina cenu loku.", scale=100),
    Par("g_B", "Ambulatorā budžeta (un apjoma) reālā izaugsme bāzes scenārijā", "%/gadā", 0.0, -0.03, 0.05, 0.0025,
        G_SIST, "V",
        "NVD atvērtie dati (data.gov.lv): valsts apmaksātie SAVA apmeklējumi 9,65 (2023), 9,68 (2024), 9,65 milj. (2025) – apjoms nemainīgs (−0,4 % 2025/2024). Raksts: «kamēr finansējums paliek esošajā līmenī…».",
        "0 = reāli nemainīgs finansējums (nominālais pieaugums = inflācija).", scale=100),
    # ---------------- 3. Uzvedība ----------------
    Par("eta", "Ārsta laika sadales elastība pret valsts/privātā ieņēmuma attiecību", "–", 0.6, 0.1, 1.5, 0.05,
        G_UZV, "C",
        "Kvalitatīvi: Biglaiser & Ma (2007) – jo lielāka atalgojuma starpība, jo vairāk laika privātajā praksē. "
        "Skaitliskas vērtības nav pārnestas uz Latviju.",
        "0,6 nozīmē: ja valsts/privātās ienākuma attiecība pieaug par 10 %, valsts darbam atvēlētais laiks pieaug ~6 %. "
        "Tas ir galvenais nenoteiktības avots – jāskata jutīgums."),
    Par("s_lo", "Valsts darbam atvēlētā laika apakšējā robeža", "%", 0.35, 0.1, 0.7, 0.01,
        G_UZV, "C", "Pieņēmums: daļa ārstu strādā tikai slimnīcā/valsts struktūrās (rezidenti, universitāšu slimnīcas).",
        "Aizsargā modeli no pilnas aizplūšanas uz privāto sektoru.", scale=100),
    Par("s_hi", "Valsts darbam atvēlētā laika augšējā robeža", "%", 0.95, 0.7, 1.0, 0.01,
        G_UZV, "C", "Pieņēmums: vienmēr paliek neliela privātā prakse.",
        "Aizsargā modeli no nereālas pilnīgas pārejas uz valsts darbu.", scale=100),
    Par("t_adj", "Ārstu laika sadales pielāgošanās ilgums", "gadi", 1.0, 0.25, 4.0, 0.25,
        G_UZV, "C", "Līgumu, darba laika un praksēm saistīto lēmumu inerce.",
        "Ātra pielāgošanās nozīmē, ka tarifa kāpums rada efektu ātri; lēna – ka valsts tur pārejas periodu."),
    Par("e_w", "Pacientu pāreja uz maksas pakalpojumu: elastība pret gaidīšanas laiku", "–", 0.5, 0.0, 1.5, 0.05,
        G_UZV, "C",
        "Rindu teorija (Lindsay & Feigenbaum 1984; Iversen 1993): gaidīšanas laiks ir «cena», kas sadala deficītu.",
        "0,5: rinda pieaug par 10 % → maksājošo daļa +5 %."),
    Par("e_p", "Pacientu pāreja uz maksas pakalpojumu: elastība pret relatīvo cenu", "–", 0.5, 0.0, 1.5, 0.05,
        G_UZV, "C",
        "Veselības aprūpes cenu elastība parasti ir zema (|0,1–0,5|); aprūpes pieprasījums ar rindu alternatīvu augstāks.",
        "Jo augstāka, jo vairāk cenu kāpums mazina maksas pieprasījumu un stabilizē cenu loku."),
    Par("xi", "Inducētais pieprasījums: elastība pret gaidīšanas laika samazinājumu", "–", 0.15, 0.0, 0.6, 0.05,
        G_UZV, "C",
        "Martin & Smith (1999): kad pieejamība uzlabojas, pieprasījums pieaug, tāpēc rindas saīsinās lēnāk.",
        "Raksta godīgi norādīts ierobežojums – rinda saīsinās lēnāk, nekā gribētos."),
    Par("lam", "Maksas cenas pielāgošanās ātrums pārprasījumam", "1/gadā", 0.5, 0.1, 2.0, 0.1,
        G_UZV, "C",
        "Cena ātri nepielāgojas: ārstu darba laiks un klīniku kapacitāte ir ierobežota; cenrāži mainās reizi gadā.",
        "Nosaka cenu loka ātrumu. Cena reaģē uz attiecību starp maksas pieprasījumu un maksas kapacitāti."),
    Par("adm0", "Administratīvā sloga daļa valsts apmaksātā darba laikā (bāze)", "%", 0.15, 0.0, 0.4, 0.01,
        G_UZV, "C",
        "Nav izmērīta Latvijā. Citur ārsti ziņo 15–25 % laika uz dokumentāciju.",
        "Administratīvā sloga samazināšana vienlaikus palielina valsts darba kapacitāti un pievilcību.", scale=100),
    # ---------------- 4. Akūtā palīdzība ----------------
    Par("W_safe_m", "Droša gaidīšanas robeža (kā ilgi var gaidīt bez drauda progresēšanai)", "mēneši", 3.0, 1, 6, 0.5,
        G_AKUTA, "C",
        "Klīniskā prakse: plānveida konsultācijai 1–3 mēneši; steidzamiem gadījumiem īsāk. Latvijā nav vienota normatīva visām specialitātēm.",
        "Rakstā ieteiktais «maksimālais gaidīšanas laiks» ir politikas rīks; šeit tas kalpo kā klīniskais slieksnis."),
    Par("delta", "Gaidošo, kas pāri drošajai robežai, gada daļa, kas nonāk slimnīcā ar novēršamu akūtu stāvokli", "%/gadā", 0.02, 0.0, 0.10, 0.005,
        G_AKUTA, "C",
        "Nav Latvijas datu. Netieši: ambulatori jūtīgo stāvokļu (ACSC) hospitalizāciju statistika, NVD/SPKC stacionāro DRG dati.",
        "Svarīgākais budžeta loka parametrs. Literatūra (Russell 2009) norāda, ka novērsto hospitalizāciju ietaupījums sedz tikai daļu izmaksu – "
        "tāpēc noklusējums ir zems.", scale=100),
    Par("c_ac", "Vidējās izmaksas vienam novēršamam akūtam gadījumam", "EUR", 2500, 500, 8000, 100,
        G_AKUTA, "C",
        "NVD DRG bāzes likme × svars; Latvijā tipiska akūta ārstēšanas epizode 1500–4000 EUR.",
        "Aizstājams ar DRG datiem pēc ICD-10 diagnožu grupas (ACSC)."),
    Par("crowd", "Akūtās palīdzības izmaksu izspiešanas efekts uz ambulatoro budžetu", "0–1", 1.0, 0.0, 1.0, 0.1,
        G_AKUTA, "C",
        "Raksts: «Akūtā palīdzība jāapmaksā jebkurā gadījumā, tāpēc tā patērē arvien lielāku daļu naudas, un ambulatorajai aprūpei paliek mazāk.»",
        "1 = visu papildu akūto izdevumu sedz no ambulatorā budžeta (fiksēts kopbudžets); 0 = papildus finansējums."),
    # ---------------- 5. Ekonomiskais ieguvums ----------------
    Par("ell", "Zaudētās darba dienas uz vienu pacientu gadā, ja gaida ilgāk par drošo robežu", "dienas", 1.0, 0.0, 15, 0.5,
        G_EKON, "C",
        "Nav Latvijas novērtējuma. Saistīts ar VSAA slimības lapu statistiku (diagnožu grupās).",
        "LSB galvenais arguments (darbaspēks) – tāpēc to var mainīt. Rezultāts ir ilustratīvs, nevis prognoze."),
    Par("emp", "Nodarbināto daļa gaidošajos", "%", 0.55, 0.2, 0.8, 0.05,
        G_EKON, "B", "CSP: nodarbinātības līmenis 20–64 g. ~77 %, bet gaidošie ir vecāki par vidējo.",
        "Aptuvens; pietiekams kārtas novērtējumam.", scale=100),
    Par("v_day", "Vienas darba dienas vērtība (IKP uz nodarbināto / 250)", "EUR", 180, 80, 400, 10,
        G_EKON, "V", "Eurostat: IKP 41 108 milj. EUR (2024) / nodarbinātie 915 tūkst. (2024) = 44,9 tūkst. EUR gadā → 180 EUR dienā (nama_10_gdp, nama_10_pe).",
        "Vidējais; pacientu faktiskā produktivitāte var atšķirties. Vērtība atbilst pārbaudītajam aprēķinam."),
]

PAR_BY_KEY = {p.key: p for p in REGISTRY}


@dataclass
class Params:
    E0: float = 379.6
    B0: float = 1970
    oop_share0: float = 0.32
    vhi_share0: float = 0.05
    tau0: float = 61
    p0: float = 90
    phi0: float = 0.25
    W0m: float = 4.0
    H0: float = 3000
    slack0: float = 1.05
    h_ab: float = 0.15
    g_d: float = 0.01
    g_H: float = 0.0
    g_y: float = 0.025
    g_B: float = 0.0
    eta: float = 0.6
    s_lo: float = 0.35
    s_hi: float = 0.95
    t_adj: float = 1.0
    e_w: float = 0.5
    e_p: float = 0.5
    xi: float = 0.15
    lam: float = 0.5
    adm0: float = 0.15
    W_safe_m: float = 3.0
    delta: float = 0.02
    c_ac: float = 2500
    crowd: float = 1.0
    ell: float = 1.0
    emp: float = 0.55
    v_day: float = 180


@dataclass
class Policy:
    """Politikas svirras. Izmaiņas pret bāzes (nemainīga reālā) līmeni, ieviešamas pakāpeniski."""
    d_tarifs: float = 0.0     # tarifa maiņa (daļskaitlis; 0,25 = +25 %)
    d_apjoms: float = 0.0     # apmaksātā apjoma (kvotas) maiņa
    admin_red: float = 0.0    # administratīvā sloga samazinājums (daļskaitlis no darba laika)
    ramp_years: float = 3.0   # ieviešanas periods (daudzgadu plāns)
    delay_years: float = 0.0  # kavēšanās līdz ieviešanas sākumam
    tarifs_aug: float = 0.0   # papildu reālā tarifa izaugsme gadā pēc ieviešanas sākuma (daudzgadu plāns)
    apjoms_aug: float = 0.0   # papildu reālā apjoma izaugsme gadā pēc ieviešanas sākuma
    fte_aug: float = 0.0      # papildu ārstu PSE izaugsme gadā (rezidentūras vietas), sākot pēc fte_lag gadiem
    fte_lag: float = 5.0      # kavēšanās no lēmuma līdz jauno speciālistu nonākšanai ambulatorajā darbā
    auto_fund: bool = False   # True = politikas izmaksas tiek segtas ar papildu naudu (ārpus bāzes budžeta)


assert {f.name for f in fields(Params)} == {p.key for p in REGISTRY}, "Params un REGISTRY nesakrīt"
for _p in REGISTRY:
    assert getattr(Params(), _p.key) == _p.default, f"Noklusējuma vērtība nesakrīt: {_p.key}"
