"""Parametru reģistrs: katram lielumam – vērtība, robežas, avots, statuss un pamatojums.

Statusi:
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
        G_BAZE, "A",
        "2026. gada valsts budžeta sadalījums, pēc LV portāla atreferējuma (lvportals.lv, 04.12.2025.): "
        "«speciālistu konsultācijām un izmeklējumiem ambulatori 379,6 milj. eiro».",
        "Šī ir summa, kas konkurē par ārstu laiku modeļa kodolā. Ja pēc primārā avota (FM «Valsts budžets 2026. gadam», "
        "NVD plāns) skaitlis atšķiras, tas ir jāpārraksta – visas pārējās bāzes vērtības (apjoms, pieprasījums) tiek "
        "kalibrētas no tās."),
    Par("B0", "Kopējais valsts veselības budžets", "milj. EUR", 1970, 1500, 2500, 10,
        G_BAZE, "A",
        "«Veselības nozares budžets 2026. gadā 1,97 miljardi eiro» (lvportals.lv, 04.12.2025.).",
        "Vajadzīgs tikai, lai aprēķinātu pacientu tiešo maksājumu daļu no kopējiem veselības izdevumiem. "
        "Nav identisks ar SHA «valdības shēmu» (HF1) definīciju, tāpēc OOP daļa ir tikai salīdzināma, nevis precīza."),
    Par("oop_share0", "Pacientu tiešo maksājumu daļa kopējos veselības izdevumos (bāze)", "%", 0.30, 0.20, 0.40, 0.005,
        G_BAZE, "A",
        "27 % (2021., WHO/EK valsts veselības profils) līdz 31,9 % (2020., «Sabiedrības veselības pamatnostādnes "
        "2021.–2027.», atsauce FM dokumentā). Eurostat/OECD SHA rindā HF3 jāpārbauda aktuālā vērtība.",
        "Avoti dod 27–32 % atkarībā no gada un definīcijas, tāpēc ņemts vidējais ~30 %. ES vidējais ~15 %. "
        "Šis rādītājs kalibrē «pārējos» tiešos maksājumus (zāles, zobārstniecība), kas modelī ir nemainīgi.",
        scale=100),
    Par("vhi_share0", "Brīvprātīgās apdrošināšanas daļa kopējos izdevumos", "%", 0.04, 0.0, 0.10, 0.005,
        G_BAZE, "C",
        "Eurostat SHA HF2 – jāpārbauda; Latvijā tā ir neliela (vairāki procenti).",
        "Modelī nemainīga; ietekmē tikai OOP daļas aprēķina saucēju.", scale=100),
    Par("tau0", "Vidējais valsts tarifs par vienu ambulatoro epizodi (konsultācija + izmeklējumi)", "EUR", 45, 20, 100, 1,
        G_BAZE, "C",
        "NVD tarifu saraksti ir publiski (MK noteikumi Nr. 555), bet «epizodes» vidējais tarifs jāaprēķina no NVD "
        "apmaksāto pakalpojumu apjomiem un summām.",
        "Nosaka kalibrēto apjomu: V0 = E0 / τ0. Ja τ0 divkāršo, apjoms uz pusi mazāks, bet attiecība starp tarifu un "
        "maksas cenu mainās – tāpēc šis lielums jāaizstāj ar NVD datiem pirmajā kārtā."),
    Par("p0", "Vidējā maksas cena par to pašu epizodi privātajā praksē", "EUR", 70, 30, 200, 1,
        G_BAZE, "C",
        "Privāto klīniku cenrāži (konsultācija ~50–90 EUR, izmeklējumi atsevišķi). Nav oficiāla vidējā rādītāja.",
        "Attiecība p0/τ0 ≈ 1,6 nosaka, cik daudz izdevīgāk ārstam ir strādāt par maksu. Tieši šī attiecība "
        "(nevis absolūtās cenas) vada ārsta laika sadali."),
    Par("phi0", "Daļa epizožu, ko pacienti jau šobrīd apmaksā paši (specialisti ambulatori)", "%", 0.25, 0.05, 0.60, 0.01,
        G_BAZE, "C",
        "Nav publiskas statistikas par maksas speciālistu vizītēm. Netieši: ļoti augsta OOP daļa un rindu garums.",
        "Kopā ar rindas garumu nosaka sākuma ārstu laika sadali (s0). Pārbaudāms ar iedzīvotāju aptauju "
        "(Eurostat EU-SILC neapmierinātās vajadzības) vai klīniku ieņēmumu datiem.", scale=100),
    Par("W0m", "Vidējais gaidīšanas laiks valsts apmaksātai epizodei (bāze)", "mēneši", 4.0, 1, 12, 0.5,
        G_BAZE, "C",
        "NVD rindu dati: ārstniecības iestādes mēneša pārskatos uzrāda rindu dienās (ja >5 darba dienas); "
        "NVD prezentācijā (03.2025.) pacienti min reālas rindas «~5–8 mēneši». Vidēja svērta vērtība nav publicēta.",
        "Reālu rindu svērto vidējo var aprēķināt no NVD mēneša rindu pārskatiem (rindapiearsta.lv/NVD atvērtie dati). "
        "4 mēneši ir piesardzīgi zemāks par pacientu minēto diapazonu."),
    Par("H0", "Ambulatorajā darbā iesaistīto speciālistu ārstu pilnas slodzes ekvivalenti", "PSE", 3000, 1500, 6000, 50,
        G_BAZE, "C",
        "SPKC/Eurostat (hlth_rs_prs2) dod ārstu skaitu pa specialitātēm, nevis ambulatorās PSE.",
        "Absolūtais lielums neietekmē relatīvos rezultātus (kapacitāte tiek kalibrēta uz apjomu); svarīga ir tikai "
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
    Par("g_d", "Medicīniskās vajadzības (nosūtījumu) izaugsme gadā", "%/gadā", 0.015, 0.0, 0.05, 0.0025,
        G_SIST, "C",
        "Iedzīvotāju novecošana (Latvijā 65+ ~ 21–22 %), diagnostikas iespēju paplašināšanās. Literatūrā 1–3 % gadā.",
        "Bez šīs izaugsmes modelis «bez izmaiņām» paliktu stacionārs. Pie 1,5 % realizējas raksta apgalvojums, ka "
        "pie nemainīga finansējuma stāvoklis pakāpeniski pasliktinās. Latvijā iedzīvotāju skaits krītas, tāpēc "
        "neto efekts var būt zemāks – jāpārbauda.", scale=100),
    Par("g_H", "Ārstu darba laika (PSE) izaugsme gadā", "%/gadā", 0.0, -0.03, 0.03, 0.0025,
        G_SIST, "C",
        "Rakstā: «ārstu skaits īstermiņā nemainās». Pensionēšanās un emigrācija kompensē jauno speciālistu pieplūdumu.",
        "Pamatscenārijs 0 – atbilst rakstā pieņemtajai īstermiņa fiksētajai piedāvājuma pusei. Pozitīva vērtība imitē "
        "rezidentūras vietu palielināšanu (ar 5–7 gadu nobīdi).", scale=100),
    Par("g_y", "Iedzīvotāju reālo ienākumu izaugsme gadā", "%/gadā", 0.025, 0.0, 0.06, 0.0025,
        G_SIST, "C",
        "Latvijas reālā ienākumu izaugsme pēdējos gados 2–4 %.",
        "Augoši ienākumi palielina spēju maksāt un tādējādi pastiprina cenu loku.", scale=100),
    Par("g_B", "Ambulatorā budžeta (un apjoma) reālā izaugsme bāzes scenārijā", "%/gadā", 0.0, -0.03, 0.05, 0.0025,
        G_SIST, "C",
        "Raksts: «kamēr finansējums paliek esošajā līmenī…». 2026. gadā papildu summas pārdalītas akūtajai palīdzībai.",
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
        G_EKON, "B", "CSP: IKP ≈ 40–42 mljrd. EUR, nodarbināto ≈ 0,9 milj. → ≈ 45 tūkst. EUR gadā.",
        "Aptuvens; jāaizvieto ar aktuālo CSP IKP un nodarbinātības datiem."),
]

PAR_BY_KEY = {p.key: p for p in REGISTRY}


@dataclass
class Params:
    E0: float = 379.6
    B0: float = 1970
    oop_share0: float = 0.30
    vhi_share0: float = 0.04
    tau0: float = 45
    p0: float = 70
    phi0: float = 0.25
    W0m: float = 4.0
    H0: float = 3000
    slack0: float = 1.05
    h_ab: float = 0.15
    g_d: float = 0.015
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
