"""Nolasa modeļa kalibrācijai vajadzīgos datus no primārajiem avotiem un saglabā `dati/verificeti_dati.json`.

    python datu_atjauninat.py          # vajag internetu (Eurostat, data.gov.lv); NVD lejupielāde ~16 MB gadā

Katrs ieraksts satur vērtību, gadu, avotu un URL. Lietotne (cilne «Datu pārbaude») rāda šo failu un salīdzina
ar modeļa noklusējuma pieņēmumiem. Ārstu identifikatori NVD datnēs netiek saglabāti – tikai agregāti.
"""
from __future__ import annotations

import collections
import datetime as dt
import io
import json
import os
import urllib.parse
import urllib.request

import pandas as pd

from datu_avoti import _get, jsonstat_to_rows

EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
NVD_PACKAGE = "https://data.gov.lv/dati/api/3/action/package_show?id=ambulatoro-apmeklejumu-skaits-pa-aprupes-epizodes-veidiem"
OUT = os.path.join(os.path.dirname(__file__), "dati", "verificeti_dati.json")
UA = "Mozilla/5.0 (X11; Linux x86_64) Chrome/124"


def _eurostat(ds: str, params: str) -> list[dict]:
    status, body, err = _get(f"{EUROSTAT}{ds}?format=JSON&lang=EN&{params}", 90)
    if status != 200:
        raise RuntimeError(f"{ds}: {err or status}")
    return jsonstat_to_rows(json.loads(body))


def _series(rows: list[dict], key_fields: tuple[str, ...]) -> dict:
    out: dict = collections.defaultdict(dict)
    for r in rows:
        out["|".join(r[k] for k in key_fields)][r["time"]] = r["value"]
    return {k: dict(sorted(v.items())) for k, v in out.items()}


def eurostat_block() -> dict:
    yrs = "&".join(f"time={y}" for y in range(2019, 2026))
    d = {}
    for unit in ("PC_CHE", "PC_GDP", "EUR_HAB"):
        rows = _eurostat("hlth_sha11_hf", f"geo=LV&geo=EU27_2020&unit={unit}&icha11_hf=TOT_HF&icha11_hf=HF1&icha11_hf=HF2&icha11_hf=HF3&{yrs}")
        d[f"sha_hf_{unit}"] = _series(rows, ("geo", "icha11_hf"))
    rows = _eurostat("hlth_sha11_hchf", f"geo=LV&geo=EU27_2020&unit=EUR_HAB&icha11_hc=HC13_23&icha11_hc=HC11_21&icha11_hc=TOT_HC&{yrs}")
    d["sha_hc_hf_EUR_HAB"] = _series(rows, ("geo", "icha11_hc", "icha11_hf"))
    rows = _eurostat("demo_pjan", "geo=LV&sex=T&age=TOTAL&age=Y_GE65&" + "&".join(f"time={y}" for y in (2015, 2020, 2023, 2024, 2025)))
    d["iedzivotaji"] = _series(rows, ("age",))
    rows = _eurostat("demo_pjanind", "geo=LV&indic_de=PC_Y65_MAX&time=2015&time=2020&time=2024&time=2025")
    d["dala_65plus_pc"] = _series(rows, ("indic_de",))
    rows = _eurostat("nama_10_gdp", "geo=LV&na_item=B1GQ&unit=CP_MEUR&time=2023&time=2024")
    d["ikp_meur"] = _series(rows, ("geo",))
    rows = _eurostat("nama_10_pe", "geo=LV&na_item=EMP_DC&unit=THS_PER&time=2023&time=2024")
    d["nodarbinati_tuks"] = _series(rows, ("geo",))
    rows = _eurostat("hlth_rs_prs2", "geo=LV&med_spec=PHYS&unit=NR&time=2022&time=2023&time=2024")
    d["arsti_nr"] = _series(rows, ("wstatus",))
    rows = _eurostat("hlth_silc_08", "geo=LV&geo=EU27_2020&age=Y_GE16&sex=T&quant_inc=TOTAL&quant_inc=QU1&quant_inc=QU5&reason=WLIST&reason=TXP&reason=TXP_TFAR_WLIST&"
                     + "&".join(f"time={y}" for y in range(2021, 2025)))
    d["unmet_pc"] = _series(rows, ("geo", "quant_inc", "reason"))
    return d


def nvd_year(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        raw = r.read()
    df = pd.read_excel(io.BytesIO(raw))
    df.columns = [str(c).strip() for c in df.columns]
    pv = "Specialitātes precizējums -PVA/SAVA pazīme"
    doc = "Ārsta identifikators (pakalpojuma sniedzēja)"
    s = df[df[pv] == "S"]
    lab = s["Specialitātes nosaukums"].str.lower().str.contains("laborator")
    return dict(sava_epizodes_bez_laboratorijas=int(s[~lab]["Epizožu skaits"].sum()),
                sava_laboratorijas_epizodes=int(s[lab]["Epizožu skaits"].sum()),
                sava_epizodes=int(s["Epizožu skaits"].sum()), sava_apmeklejumi=int(s["Apmeklējumu skaits"].sum()),
                sava_arstu_skaits_unikali=int(s[doc].nunique()), sava_iestades=int(s["Ārstniecības iestādes kods (pakalpojuma sniedzēja)"].nunique()),
                pva_epizodes=int(df[df[pv] == "P"]["Epizožu skaits"].sum()), pva_apmeklejumi=int(df[df[pv] == "P"]["Apmeklējumu skaits"].sum()))


def nvd_block(years=(2023, 2024, 2025)) -> dict:
    status, body, err = _get(NVD_PACKAGE, 60)
    if status != 200:
        raise RuntimeError(f"data.gov.lv: {err or status}")
    res = json.loads(body)["result"]["resources"]
    out = {}
    for y in years:
        cand = [r for r in res if r["name"].startswith((f"{y}_12", f"{y}12")) or f"{y}12" in r["url"] or f"{y}_12" in r["url"]]
        if not cand:
            continue
        out[str(y)] = nvd_year(cand[-1]["url"]) | {"avots_url": cand[-1]["url"]}
    return out


def main():
    data = dict(atjaunots=dt.date.today().isoformat(), eurostat=eurostat_block())
    try:
        data["nvd_ambulatorie"] = nvd_block()
    except Exception as e:  # noqa: BLE001
        data["nvd_kluda"] = str(e)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("Saglabāts:", OUT)


if __name__ == "__main__":
    main()
