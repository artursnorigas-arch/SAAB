"""Drošās darbības, kas kopīgas komandrindai un Tech2 izvēlnei."""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from .kwp import SaabKwp, printable

BACKUP_DIR = Path("rezerves_kopijas")
CONFIRM_WORD = "APSTIPRINU"

Out = Callable[[str], None]
Confirm = Callable[[str], bool]


def backup(module: str, lid: int, raw: bytes) -> Path:
    BACKUP_DIR.mkdir(exist_ok=True)
    now = datetime.now()
    p = BACKUP_DIR / f"{module}_lid_{lid:02X}_{now:%Y-%m-%d_%H%M%S}.json"
    p.write_text(json.dumps({"modulis": module, "lid": lid, "hex": raw.hex(), "laiks": now.isoformat()}, indent=2),
                 encoding="utf-8")
    return p


def write_with_backup(kwp: SaabKwp, module: str, lid: int, new: bytes, apply: bool,
                      confirm: Confirm, out: Out = print) -> str:
    """Atgriež: 'nemainits' | 'sauss' | 'atcelts' | 'ok' | 'kluda'."""
    old = kwp.read_local_id(lid)
    out(f"{module} identifikators 0x{lid:02X}")
    out(f"  pašreiz: {old.hex(' ').upper()}  ({printable(old)})")
    out(f"  jauns:   {new.hex(' ').upper()}  ({printable(new)})")
    if old == new:
        out("Vērtība jau ir tāda pati – nekas netiek mainīts.")
        return "nemainits"
    if len(old) != len(new):
        out(f"  ! Garums atšķiras ({len(old)} -> {len(new)} baiti).")
    if not apply:
        out("Sausais režīms – nekas nav ierakstīts.")
        return "sauss"
    bpath = backup(module, lid, old)
    out(f"Rezerves kopija: {bpath}")
    if not confirm("Ierakstīšana modulī. Aizdedze ON, dzinējs IZSLĒGTS, akumulators uzlādēts."):
        out("Atcelts.")
        return "atcelts"
    kwp.write_local_id(lid, new)
    check = kwp.read_local_id(lid)
    if check != new:
        out(f"✗ Pārbaude neizdevās! Nolasīts: {check.hex(' ')}. Atjaunojiet no {bpath}")
        return "kluda"
    out("✓ Ierakstīts un pārbaudīts.")
    return "ok"


def actuate(kwp: SaabKwp, lid: int, param: int, data: bytes, duration: float, out: Out = print) -> None:
    """Aktivizē izpildmehānismu un VIENMĒR atdod vadību modulim."""
    try:
        kwp.io_control(lid, param, data)
        out(f"Aktivizēts uz {duration:g} s ...")
        end = time.monotonic() + duration
        while time.monotonic() < end:
            time.sleep(min(0.5, max(0.0, end - time.monotonic())))
            kwp.keepalive()
    finally:
        kwp.io_control(lid, 0x00)
        out("Vadība atdota modulim.")


def scan_lids(kwp: SaabKwp, out: Out = print, skip=(0xF0,)) -> dict[int, bytes]:
    found = {}
    for lid in range(0x100):
        if lid in skip:
            continue
        try:
            raw = kwp.read_local_id(lid)
        except Exception:  # noqa: BLE001 - nelasāmos identifikatorus izlaižam
            continue
        found[lid] = raw
        out(f"  0x{lid:02X}: {printable(raw)}")
    return found
