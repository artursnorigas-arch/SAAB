"""Datu avotu reģistrs un pieejamības pārbaude.

Palaišana (lokāli, ar piekļuvi internetam):
    python datu_avoti.py            # pārbauda, vai avotu serveri atbild, un mēģina nolasīt Eurostat OOP daļu

SVARĪGI: izstrādes sesijā visi šie serveri bija bloķēti (vides tīkla politika, HTTP 403 uz CONNECT),
tāpēc statuss «pārbaudīts sesijā» visiem ir «NAV». Skripts ir uzrakstīts, bet nav izmēģināts pret dzīviem
serveriem – pirmajā palaišanā jāpārbauda izvade.
"""
from __future__ import annotations

import itertools
import json
import sys
import urllib.parse
import urllib.request

SOURCES = [
    dict(id="eurostat_sha", avots="Eurostat", dati="Veselības izdevumi pa finansēšanas shēmām (SHA): valdība/obligātā HF1, "
         "brīvprātīgā HF2, mājsaimniecību tiešie maksājumi HF3; % no kopējiem izdevumiem; LV un ES",
         kods="hlth_sha11_hf", url="https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/hlth_sha11_hf"
         "?format=JSON&lang=EN&geo=LV&geo=EU27_2020&unit=PC_CHE&icha11_hf=TOT_HF&icha11_hf=HF1&icha11_hf=HF2&icha11_hf=HF3",
         piekluve="REST API (JSON-stat), bez atslēgas", modelim="oop_share0, vhi_share0", pieejams_no_zinasanam="jā (zināms publisks API)"),
    dict(id="eurostat_ārsti", avots="Eurostat", dati="Praktizējošie ārsti pa specialitātēm", kods="hlth_rs_prs2",
         url="https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/hlth_rs_prs2?format=JSON&geo=LV",
         piekluve="REST API", modelim="H0 (netieši; ambulatorās PSE jāaprēķina)", pieejams_no_zinasanam="jā; kods jāapstiprina"),
    dict(id="eurostat_unmet", avots="Eurostat (EU-SILC)", dati="Neapmierinātās medicīniskās vajadzības (rindu/cenas dēļ)",
         kods="hlth_silc_08", url="https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/hlth_silc_08?format=JSON&geo=LV",
         piekluve="REST API", modelim="validācija: phi0, W0m", pieejams_no_zinasanam="jā; kods jāapstiprina"),
    dict(id="oecd", avots="OECD / Eiropas Komisija", dati="Latvijas valsts veselības profils 2025 (izdevumi % IKP, tiešie maksājumi, ārstu skaits)",
         kods="Country Health Profile 2025", url="https://www.oecd.org/en/publications/country-health-profile-2025-country-notes_c0e8b8be-en/latvia_acdd6b03-en.html",
         piekluve="HTML/PDF", modelim="oop_share0 (salīdzinājums), ārstu skaits", pieejams_no_zinasanam="jā (publikācija)"),
    dict(id="csp", avots="Centrālā statistikas pārvalde", dati="Algas (ārsti, veselības nozare), IKP, nodarbinātība, iedzīvotāju vecuma struktūra",
         kods="data.stat.gov.lv (OSP_PUB)", url="https://data.stat.gov.lv/api/v1/lv/OSP_PUB",
         piekluve="PxWeb API (POST ar JSON vaicājumu)", modelim="v_day, emp, g_d (novecošana)", pieejams_no_zinasanam="jā; tabulu kodi jāatrod pārlūkā"),
    dict(id="nvd_apjomi", avots="Nacionālais veselības dienests", dati="Apmaksāto ambulatoro pakalpojumu apjomi un summas pa specialitātēm; "
         "tarifi (MK not. Nr. 555); gada pārskati", kods="vmnvd.gov.lv", url="https://www.vmnvd.gov.lv",
         piekluve="PDF/Excel pārskati; daļa atvērto datu", modelim="E0, tau0, V0 (svarīgākais datu avots)", pieejams_no_zinasanam="daļēji; vajag NVD pieprasījumu"),
    dict(id="nvd_rindas", avots="NVD / ārstniecības iestādes", dati="Gaidīšanas rindu garumi dienās pa pakalpojumiem un iestādēm (mēneša pārskati, "
         "uzrāda, ja >5 darba dienas)", kods="rindu pārskati / rindapiearsta.lv", url="https://www.vmnvd.gov.lv",
         piekluve="Excel/PDF; iespējams atvērtie dati", modelim="W0m (svērtā vidējā), phi0 validācijai", pieejams_no_zinasanam="daļēji; svērtais vidējais nav publicēts"),
    dict(id="data_gov_lv", avots="Latvijas atvērto datu portāls", dati="NVD, SPKC atvērto datu kopas (CKAN API)", kods="data.gov.lv",
         url="https://data.gov.lv/dati/api/3/action/package_search?q=veselība", piekluve="CKAN API", modelim="meklēt rindu, apjomu un ārstu datus",
         pieejams_no_zinasanam="jā; saturs jāpārbauda"),
    dict(id="spkc", avots="Slimību profilakses un kontroles centrs", dati="Veselības aprūpes resursi: ārstu skaits pa specialitātēm un reģioniem; "
         "hospitalizācijas ambulatori jūtīgu stāvokļu dēļ", kods="spkc.gov.lv", url="https://www.spkc.gov.lv",
         piekluve="Excel/PDF", modelim="H0, delta (ACSC hospitalizācijas)", pieejams_no_zinasanam="jā; tabulas jāapstiprina"),
    dict(id="fm_budzets", avots="Finanšu ministrija / Saeima", dati="Likums «Par valsts budžetu 2026.gadam…»; VM budžeta programmu sadalījums",
         kods="fm.gov.lv, likumi.lv", url="https://www.fm.gov.lv", piekluve="PDF", modelim="E0, B0", pieejams_no_zinasanam="jā"),
    dict(id="vsaa", avots="VSAA", dati="Slimības lapu (A) statistika pa diagnožu grupām un ilgumu", kods="vsaa.gov.lv",
         url="https://www.vsaa.gov.lv", piekluve="Excel/PDF", modelim="ell (zaudētās darba dienas)", pieejams_no_zinasanam="jā; diagnožu griezumu var prasīt atsevišķi"),
]


PARBAUDE = {  # rezultāti, pārbaudot 2026-11-21 pēc tam, kad vides tīkla politikā tika atļauti hosti
    "eurostat_sha": "PIEEJAMS un izmantots (REST API). Dimensija ir icha11_hf (nevis hf). Dati līdz 2024. g.",
    "eurostat_ārsti": "PIEEJAMS un izmantots (hlth_rs_prs2: PRACT/PACT/LIC). Dati līdz 2024. g.",
    "eurostat_unmet": "PIEEJAMS un izmantots (hlth_silc_08, reason=WLIST/TXP). Dati līdz 2024. g.",
    "oecd": "SDMX API atbild (200); HTML publikācija atgriež 403. Netika izmantots – Eurostat dod to pašu SHA.",
    "csp": "API sakne atbild (200); tabulu vaicājumi netika izmantoti – IKP/nodarbinātībai izmantots Eurostat. Atvērto datu CSV (VAI020) pieejams.",
    "nvd_apjomi": "PIEEJAMS un izmantots: data.gov.lv → NVD «Ambulatoro apmeklējumu skaits pa aprūpes epizodes veidiem» (XLSX, ārstu līmeņa, 2019–2026). Vietne vmnvd.gov.lv atveras ar parasta pārlūka User-Agent.",
    "nvd_rindas": "NAV pieejams atvērtajos datos: data.gov.lv meklēšana pēc «rinda/gaidīšanas/rindu» neatrod NVD rindu datu kopu. Rindu dati ir tikai rindapiearsta.lv (nav atļauts; rezervācijas portāls).",
    "data_gov_lv": "PIEEJAMS un izmantots (CKAN API). NVD publicē 14 datu kopas, tai skaitā ambulatoro apjomu.",
    "spkc": "Sakne atbild (200); datu tabulas netika izmantotas.",
    "fm_budzets": "Sakne atbild (200). Budžeta skaitļi apstiprināti VM paziņojumā (lvportals.lv, 04.12.2025.).",
    "vsaa": "NAV atļauts šajā vidē (host nav pievienots); slimības lapu dati netika pārbaudīti.",
}


def jsonstat_to_rows(js: dict) -> list[dict]:
    """JSON-stat 2.0 → saraksts ar vārdnīcām {dimensija: kods, 'value': skaitlis}."""
    ids, sizes = js["id"], js["size"]
    cats = []
    for d in ids:
        idx = js["dimension"][d]["category"]["index"]
        if isinstance(idx, dict):
            idx = sorted(idx, key=idx.get)
        cats.append(list(idx))
    values = js["value"]
    rows = []
    for pos, combo in enumerate(itertools.product(*[range(s) for s in sizes])):
        v = values.get(str(pos)) if isinstance(values, dict) else values[pos]
        if v is None:
            continue
        row = {d: cats[i][combo[i]] for i, d in enumerate(ids)}
        row["value"] = v
        rows.append(row)
    return rows


def _get(url: str, timeout: int = 20) -> tuple[int | None, bytes, str]:
    try:
        url = urllib.parse.quote(url, safe=":/?&=%,")
        req = urllib.request.Request(url, headers={"User-Agent": "rinda-modelis/0.1 (data availability check)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), ""
    except Exception as e:  # noqa: BLE001
        return None, b"", f"{type(e).__name__}: {e}"


def check_all() -> list[dict]:
    out = []
    for s in SOURCES:
        status, _, err = _get(s["url"])
        out.append(dict(id=s["id"], avots=s["avots"], http=status, kluda=err))
    return out


def eurostat_oop() -> list[dict]:
    """Latvijas un ES tiešo maksājumu (HF3) un valdības shēmu (HF1) daļa pa gadiem."""
    status, body, err = _get(next(s["url"] for s in SOURCES if s["id"] == "eurostat_sha"))
    if status != 200:
        raise RuntimeError(f"Eurostat nav sasniedzams: {err or status}")
    rows = jsonstat_to_rows(json.loads(body))
    return [r for r in rows if r.get("icha11_hf") in ("HF1", "HF2", "HF3")]


if __name__ == "__main__":
    print("Avotu pieejamība:")
    for r in check_all():
        print(f"  {r['id']:<16} HTTP={r['http']}  {r['kluda']}")
    try:
        for r in sorted(eurostat_oop(), key=lambda x: (x["geo"], x["icha11_hf"], x["time"]))[-30:]:
            print(r)
    except Exception as e:  # noqa: BLE001
        print("Eurostat HF datu nolasīšana neizdevās:", e, file=sys.stderr)
