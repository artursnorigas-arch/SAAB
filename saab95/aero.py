"""Saab 9-5 2.3t Aero (B235R, Trionic 7) – turbo dzinēja pārbaudes un brauciena analīze.

Robežvērtības ir orientējošas, nevis rūpnīcas specifikācija.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

from . import obd2

PRESET = ["rpm", "map", "baro", "iat", "timing", "coolant", "load", "throttle", "stft", "ltft", "voltage"]


def boost_bar(map_kpa: float, baro_kpa: float) -> float:
    """Turbo virsspiediens (bar) = absolūtais kolektora spiediens − atmosfēras spiediens."""
    return (map_kpa - baro_kpa) / 100


@dataclass
class Finding:
    level: str  # OK | UZMANĪBU | PROBLĒMA | INFO
    title: str
    detail: str

    def __str__(self) -> str:
        icon = {"OK": "✓", "UZMANĪBU": "!", "PROBLĒMA": "✗", "INFO": "·"}[self.level]
        return f" {icon} {self.title:<30} {self.detail}"


def health_check(o: obd2.Obd2) -> list[Finding]:
    """Pārbaude tukšgaitā ar sasilušu dzinēju."""
    f: list[Finding] = []

    def rd(name):
        try:
            return o.read_pid(name)
        except Exception:  # noqa: BLE001
            return None

    rpm, cool, stft, ltft = rd("rpm"), rd("coolant"), rd("stft"), rd("ltft")
    map_, baro, volt, iat = rd("map"), rd("baro"), rd("voltage"), rd("iat")

    if not rpm:
        f.append(Finding("UZMANĪBU", "Dzinējs", "nedarbojas – iedarbiniet un ļaujiet sasilt"))
    elif not 650 <= rpm <= 1000:
        f.append(Finding("UZMANĪBU", "Tukšgaitas apgriezieni", f"{rpm:.0f} apgr/min (parasti ~800–900)"))
    else:
        f.append(Finding("OK", "Tukšgaitas apgriezieni", f"{rpm:.0f} apgr/min"))

    if cool is not None:
        if cool < 80:
            f.append(Finding("INFO", "Dzesēšanas šķidrums", f"{cool:.0f} °C – dzinējs nav sasilis, degvielas korekcijas nav ticamas"))
        elif cool > 105:
            f.append(Finding("PROBLĒMA", "Dzesēšanas šķidrums", f"{cool:.0f} °C – pārkaršana? Termostats, ventilators, sūknis"))
        else:
            f.append(Finding("OK", "Dzesēšanas šķidrums", f"{cool:.0f} °C"))

    if stft is not None and ltft is not None:
        total = stft + ltft
        txt = f"īstermiņa {stft:+.1f}%, ilgtermiņa {ltft:+.1f}%, kopā {total:+.1f}%"
        if total > 10:
            f.append(Finding("PROBLĒMA", "Degvielas korekcija (liess)", txt +
                             " – pārbaudiet gaisa noplūdes: PCV sistēma, vakuuma šļūtenes, interkūlera savienojumi, MAF"))
        elif total < -10:
            f.append(Finding("PROBLĒMA", "Degvielas korekcija (bagāts)", txt + " – inžektori, degvielas spiediens, lambda zonde"))
        else:
            f.append(Finding("OK", "Degvielas korekcija", txt))

    if map_ is not None and rpm and rpm < 1100:
        if map_ > 60:
            f.append(Finding("UZMANĪBU", "Vakuums tukšgaitā", f"{map_:.0f} kPa abs. – vājš vakuums: noplūde vai sensors"))
        else:
            f.append(Finding("OK", "Vakuums tukšgaitā", f"{map_:.0f} kPa abs."))
    if baro is not None:
        f.append(Finding("INFO", "Atmosfēras spiediens", f"{baro:.0f} kPa"))

    if volt is not None:
        if rpm and not 13.2 <= volt <= 14.8:
            f.append(Finding("UZMANĪBU", "Uzlādes spriegums", f"{volt:.2f} V (darbojoties ~13,5–14,5 V) – ģenerators/akumulators"))
        else:
            f.append(Finding("OK", "Spriegums", f"{volt:.2f} V"))
    if iat is not None and iat > 60:
        f.append(Finding("UZMANĪBU", "Ieplūdes gaisa temp.", f"{iat:.0f} °C – karsts gaiss tukšgaitā (normāli pēc braukšanas)"))

    try:
        codes = o.read_dtcs()
        f.append(Finding("PROBLĒMA" if codes else "OK", "Kļūdu kodi",
                         ", ".join(f"{c} {obd2.DTC_HINTS.get(c, '')}".strip() for c in codes) or "nav"))
    except Exception as e:  # noqa: BLE001
        f.append(Finding("UZMANĪBU", "Kļūdu kodi", f"neizdevās nolasīt: {e}"))
    return f


def analyze_log(path: str | Path, boost_max: float | None = None) -> list[Finding]:
    """Analizē `live --preset aero --csv` žurnālu."""
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return [Finding("UZMANĪBU", "Žurnāls", "tukšs")]

    def col(name):
        out = []
        for r in rows:
            try:
                v = float(r.get(name, "nan"))
            except ValueError:
                v = math.nan
            out.append(v)
        return out

    def valid(xs):
        return [x for x in xs if not math.isnan(x)]

    f: list[Finding] = [Finding("INFO", "Ieraksti", f"{len(rows)}")]
    rpm, map_, baro, iat, timing = col("rpm"), col("map"), col("baro"), col("iat"), col("timing")
    cool, load, stft, ltft = col("coolant"), col("load"), col("stft"), col("ltft")

    b = valid(baro)
    baro0 = sum(b) / len(b) if b else 101.3
    boosts = [boost_bar(m, baro0) for m in valid(map_)]
    if boosts:
        mx = max(boosts)
        lvl = "PROBLĒMA" if boost_max is not None and mx > boost_max else "INFO"
        f.append(Finding(lvl, "Maks. turbo virsspiediens", f"{mx:.2f} bar"
                         + (f" (robeža {boost_max:.2f})" if boost_max is not None else "")))
        if mx < 0.4 and max(valid(load) or [0]) > 80:
            f.append(Finding("UZMANĪBU", "Turbo spiediens", "zems pie lielas slodzes – noplūde, BPC vārsts, wastegate, turbīna"))

    v_iat = valid(iat)
    if v_iat:
        mx = max(v_iat)
        f.append(Finding("UZMANĪBU" if mx > 60 else "OK", "Maks. ieplūdes gaisa temp.", f"{mx:.0f} °C"
                         + (" – interkūlers/karstuma uzsūkšana" if mx > 60 else "")))

    high = [(t, r) for t, r, m in zip(timing, rpm, map_) if not math.isnan(t) and r > 2500 and m - baro0 > 50]
    if high:
        tmin = min(t for t, _ in high)
        avg = sum(t for t, _ in high) / len(high)
        lvl = "UZMANĪBU" if tmin < 0 else "OK"
        f.append(Finding(lvl, "Apsteidze zem turbo spiediena", f"vid. {avg:.1f}°, min. {tmin:.1f}°"
                         + (" – T7 atvelk apsteidzi: detonācija? Degviela (98), DI kasete, svecītes" if tmin < 0 else "")))
    else:
        f.append(Finding("INFO", "Apsteidze zem slodzes", "nav datu ar >0,5 bar un >2500 apgr/min"))

    v_cool = valid(cool)
    if v_cool and max(v_cool) > 105:
        f.append(Finding("PROBLĒMA", "Maks. dzesēšanas temp.", f"{max(v_cool):.0f} °C"))
    trims = [s + lt for s, lt, c in zip(stft, ltft, cool) if not math.isnan(s + lt) and c >= 80]
    if trims:
        avg = sum(trims) / len(trims)
        lvl = "UZMANĪBU" if abs(avg) > 10 else "OK"
        f.append(Finding(lvl, "Vid. degvielas korekcija (silts)", f"{avg:+.1f}%"))
    return f
