"""Interaktīva Tech2 stila izvēlne terminālī."""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import actions, aero, discovery, modules, obd2
from .kwp import KwpError, SaabKwp, printable
from .transport import Transport


class Tech2:
    def __init__(self, tr: Transport, input_fn: Callable[[str], str] = input, out: Callable[[str], None] = print,
                 user_file: Path = modules.USER_FILE):
        self.tr = tr
        self.inp = input_fn
        self.out = out
        self.user_file = user_file

    # ---------- palīgi ----------
    def menu(self, title: str, items: list[str], back: str = "Atpakaļ") -> int:
        self.out(f"\n=== {title} ===")
        for i, it in enumerate(items, 1):
            self.out(f"  {i}. {it}")
        self.out(f"  0. {back}")
        while True:
            a = self.inp("> ").strip()
            if a.isdigit() and 0 <= int(a) <= len(items):
                return int(a)
            self.out("Nederīga izvēle.")

    def confirm(self, text: str) -> bool:
        self.out(f"\n⚠  {text}")
        return self.inp(f"Ierakstiet {actions.CONFIRM_WORD}: ").strip() == actions.CONFIRM_WORD

    def _safe(self, fn, *a):
        try:
            return fn(*a)
        except KeyboardInterrupt:
            self.out("Pārtraukts.")
        except Exception as e:  # noqa: BLE001 - izvēlnei jāturpina darboties
            self.out(f"Kļūda: {e}")

    # ---------- galvenā izvēlne ----------
    def run(self) -> None:
        self.out("Saab 9-5 diagnostika – Tech2 režīms")
        while True:
            c = self.menu("Galvenā izvēlne", [
                "Vadības moduļi",
                "OBD-II (dzinējs, standarta dati)",
                "Meklēt moduļus kopnē",
                "CAN kopnes monitors",
            ], back="Iziet")
            if c == 0:
                return
            fn = [None, self.modules_menu, self.obd_menu, self.discover_menu, self.monitor_menu][c]
            self._safe(fn)

    def modules_menu(self) -> None:
        while True:
            mods = list(modules.load(self.user_file).values())
            labels = [f"{m.key:<6} {m.name:<42} {'✓' if m.known else '– ' + m.status}" for m in mods]
            c = self.menu("Vadības moduļi", labels)
            if c == 0:
                return
            m = mods[c - 1]
            if not m.known:
                self.out("Šī moduļa adrese vēl nav zināma. Izmantojiet 'Meklēt moduļus kopnē'.")
                continue
            self._safe(self.module_menu, m)

    def module_menu(self, m: modules.Module) -> None:
        kwp = SaabKwp(self.tr, m.endpoint)
        kwp.connect()
        self.out(f"Savienots ar {m.name}.")
        while True:
            c = self.menu(m.name, [
                "Kļūdu kodi",
                "Dzēst kļūdu kodus",
                "Datu saraksts",
                "Identifikācija",
                "Aktivizēšanas testi",
                "Iestatījumi (rakstīšana)",
                "Skenēt identifikatorus (atklāšana)",
            ])
            if c == 0:
                return
            fn = [None, self.dtc, self.dtc_clear, self.data_list, self.identify, self.actuators, self.settings,
                  self.scan][c]
            self._safe(fn, kwp, m)

    # ---------- moduļa funkcijas ----------
    def dtc(self, kwp: SaabKwp, m) -> None:
        codes = kwp.read_dtcs()
        if not codes:
            self.out("Kļūdu kodu nav.")
        for d in codes:
            hint = obd2.DTC_HINTS.get(d.code, "")
            self.out(f"  {d.code}  {'AKTĪVS ' if d.active else 'vēsturisks'}  st=0x{d.status:02X}  {hint}")

    def dtc_clear(self, kwp: SaabKwp, m) -> None:
        if self.confirm(f"Dzēst visus {m.key} kļūdu kodus?"):
            kwp.clear_dtcs()
            self.out("Izdzēsts.")

    def data_list(self, kwp: SaabKwp, m) -> None:
        if not m.params:
            self.out("Parametri nav definēti. Izmantojiet 'Skenēt identifikatorus'.")
            return
        rounds = self.inp("Cik reizes atjaunot? (Enter = 1): ").strip()
        for _ in range(int(rounds) if rounds.isdigit() else 1):
            self.out(f"\n[{datetime.now():%H:%M:%S}]")
            for p in m.params.values():
                try:
                    self.out(f"  {p.name:<36} {p.decode(kwp.read_local_id(p.lid))}")
                except KwpError as e:
                    self.out(f"  {p.name:<36} <{e}>")
            time.sleep(0.3)

    def identify(self, kwp: SaabKwp, m) -> None:
        for opt in m.id_options or [0x90, 0x91, 0x92, 0x94, 0x95, 0x97, 0x9A]:
            try:
                self.out(f"  1A {opt:02X}: {printable(kwp.read_ecu_id(opt))}")
            except KwpError:
                pass
        for p in m.params.values():
            if p.kind == "ascii":
                try:
                    self.out(f"  {p.name}: {p.decode(kwp.read_local_id(p.lid))}")
                except KwpError:
                    pass

    def actuators(self, kwp: SaabKwp, m) -> None:
        if not m.actuators:
            self.out("Aktivizēšanas testi šim modulim nav definēti (skat. README, 'aktivizacijas').")
            return
        c = self.menu("Aktivizēšanas testi", [a.name for a in m.actuators])
        if c == 0:
            return
        a = m.actuators[c - 1]
        if a.hint:
            self.out(a.hint)
        if self.confirm(f"Aktivizēt '{a.name}' uz {a.duration:g} s?"):
            actions.actuate(kwp, a.lid, a.param, a.data, a.duration, self.out)

    def settings(self, kwp: SaabKwp, m) -> None:
        writable = [p for p in m.params.values() if p.writable]
        if not writable:
            self.out("Rakstāmi parametri nav definēti ('rakstams': true moduli_lietotajs.json).")
            return
        c = self.menu("Iestatījumi", [f"{p.name} = {p.decode(kwp.read_local_id(p.lid))}" for p in writable])
        if c == 0:
            return
        p = writable[c - 1]
        if p.options:
            self.out("Varianti: " + ", ".join(p.options.values()))
        val = self.inp("Jaunā vērtība: ").strip()
        if val:
            actions.write_with_backup(kwp, m.key, p.lid, p.encode(val), True, self.confirm, self.out)

    def scan(self, kwp: SaabKwp, m) -> None:
        self.out("Nolasa 0x00..0xFF (tikai lasīšana)...")
        found = actions.scan_lids(kwp, self.out)
        self.out(f"Atrasti {len(found)}.")
        if found and self.inp("Piešķirt nosaukumus un saglabāt? (j/n): ").strip().lower() == "j":
            patch = {}
            for lid, raw in found.items():
                if lid in m.params:
                    continue
                name = self.inp(f"  0x{lid:02X} [{printable(raw)}] nosaukums (Enter = izlaist): ").strip()
                if name:
                    kind = "ascii" if printable(raw) != raw.hex(" ").upper() else "hex"
                    patch[f"0x{lid:02X}"] = {"nosaukums": name, "tips": kind}
            if patch:
                modules.save_user(m.key, {"parametri": patch}, self.user_file)
                self.out(f"Saglabāts {self.user_file}.")

    # ---------- OBD, meklēšana, monitors ----------
    def obd_menu(self) -> None:
        o = obd2.Obd2(self.tr)
        while True:
            c = self.menu("OBD-II", ["VIN", "Kļūdu kodi", "Dzēst kļūdu kodus", "Reāllaika dati", "Aero veselības pārbaude"])
            if c == 0:
                return
            if c == 1:
                self.out(f"VIN: {o.read_vin()}")
            elif c == 2:
                self.out(", ".join(o.read_dtcs()) or "nav")
            elif c == 3 and self.confirm("Dzēst OBD kļūdu kodus (atiestata gatavības testus)?"):
                o.clear_dtcs()
                self.out("Izdzēsts.")
            elif c == 4:
                sup = o.supported_pids()
                for p in obd2.PIDS.values():
                    if p.pid in sup:
                        self.out(f"  {p.title:<34} {o.read_pid(p.name):>9.1f} {p.unit}")
            elif c == 5:
                for f in aero.health_check(o):
                    self.out(str(f))

    def discover_menu(self) -> None:
        self.out("Sūta sesijas pieprasījumu adresēm 0x01..0xFF. Dzinējs IZSLĒGTS, aizdedze ON.")
        found = discovery.discover(self.tr)
        if not found:
            self.out("Neviens modulis neatbildēja. Mēģiniet citu kopni (--bitrate 47619 I-Bus).")
            return
        for f in found:
            self.out(f"  mērķis {f['merkis']}  KWP={'jā' if f['kwp'] else 'nē'}  atbildes: {f['atbildes']}")
        mods = modules.load(self.user_file)
        for f in found:
            if not f["kwp"]:
                continue
            key = self.inp(f"Kuram modulim pieder {f['merkis']}? ({'/'.join(mods)}, Enter = izlaist): ").strip().upper()
            if key in mods:
                modules.save_user(key, {"merkis": f["merkis"], "statuss": "atrasts"}, self.user_file)
                self.out(f"{key} saglabāts.")

    def monitor_menu(self) -> None:
        s = self.inp("Cik sekundes klausīties? (Enter = 5): ").strip()
        secs = float(s) if s else 5.0
        rows = discovery.summarize(discovery.monitor(self.tr, secs), secs)
        for r in rows:
            self.out(f"  {r['id']}  {r['kadri']:>5}  {r['hz']:>6} Hz  {r['pedejie_dati']}")
        if rows and self.inp("Saglabāt JSON? (j/n): ").strip().lower() == "j":
            p = Path(f"kopne_{datetime.now():%Y-%m-%d_%H%M%S}.json")
            p.write_text(json.dumps(rows, indent=2), encoding="utf-8")
            self.out(f"Saglabāts {p}")
