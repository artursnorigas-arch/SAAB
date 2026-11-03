"""Saab 9-5 vadības moduļu reģistrs (Tech2 "Vadības moduļi" izvēlnes analogs).

Noklusējuma definīcijas atrodas `moduli.json` (pakotnē). Lietotāja papildinājumi
(atrastās adreses, parametru nosaukumi, aktivizēšanas testi) tiek glabāti
darba mapē `moduli_lietotajs.json` un pārraksta noklusējumus.
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

from .kwp import Endpoint, printable

DEFAULT_FILE = Path(__file__).with_name("moduli.json")
USER_FILE = Path("moduli_lietotajs.json")


def _int(v) -> int | None:
    if v is None:
        return None
    return v if isinstance(v, int) else int(str(v), 0)


@dataclass
class Param:
    lid: int
    name: str
    kind: str = "hex"  # hex | ascii | u8 | s8 | u16 | s16 | u32
    scale: float = 1.0
    offset: float = 0.0
    unit: str = ""
    writable: bool = False
    options: dict[str, str] = field(default_factory=dict)  # vērtība(hex) -> nosaukums

    def decode(self, raw: bytes) -> str:
        if self.kind == "ascii":
            return printable(raw)
        fmt = {"u8": ">B", "s8": ">b", "u16": ">H", "s16": ">h", "u32": ">I"}.get(self.kind)
        if fmt and len(raw) >= struct.calcsize(fmt):
            v = struct.unpack(fmt, raw[: struct.calcsize(fmt)])[0]
            if self.options:
                return self.options.get(f"{v:02X}", f"{v} (nezināma vērtība)")
            val = v * self.scale + self.offset
            return f"{val:g} {self.unit}".strip()
        return raw.hex(" ").upper()

    def encode(self, text: str) -> bytes:
        if self.options:
            for k, label in self.options.items():
                if text.strip().lower() in (label.lower(), k.lower()):
                    return bytes.fromhex(k.zfill(2 * max(1, len(k) // 2)))
        if self.kind == "ascii":
            return text.encode("ascii")
        fmt = {"u8": ">B", "s8": ">b", "u16": ">H", "s16": ">h", "u32": ">I"}.get(self.kind)
        if fmt:
            v = round((float(text) - self.offset) / self.scale)
            return struct.pack(fmt, v)
        return bytes.fromhex(text.replace(" ", ""))


@dataclass
class Actuator:
    name: str
    lid: int
    param: int = 0x07
    data: bytes = b""
    duration: float = 3.0
    hint: str = ""


@dataclass
class Module:
    key: str
    name: str
    bus: str
    endpoint: Endpoint | None
    status: str = ""
    params: dict[int, Param] = field(default_factory=dict)
    actuators: list[Actuator] = field(default_factory=list)
    id_options: list[int] = field(default_factory=list)

    @property
    def known(self) -> bool:
        return self.endpoint is not None


def _merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_raw(user_file: Path = USER_FILE) -> dict:
    raw = json.loads(DEFAULT_FILE.read_text(encoding="utf-8"))
    if user_file.exists():
        raw = _merge(raw, json.loads(user_file.read_text(encoding="utf-8")))
    return raw


def load(user_file: Path = USER_FILE) -> dict[str, Module]:
    raw = load_raw(user_file)
    mods = {}
    for key, m in raw.items():
        if key.startswith("_"):
            continue
        ep = None
        if _int(m.get("merkis")) is not None:
            ep = Endpoint(
                target=_int(m["merkis"]),
                init_tx=_int(m.get("init_tx", 0x220)),
                init_rx=_int(m.get("init_rx", 0x238)),
                req=_int(m.get("req", 0x240)),
                resp=_int(m.get("resp", 0x258)),
                ack=_int(m.get("ack", 0x266)),
            )
        params = {}
        for lid_s, p in m.get("parametri", {}).items():
            lid = _int(lid_s)
            params[lid] = Param(
                lid=lid,
                name=p["nosaukums"],
                kind=p.get("tips", "hex"),
                scale=p.get("merogs", 1.0),
                offset=p.get("nobide", 0.0),
                unit=p.get("vieniba", ""),
                writable=p.get("rakstams", False),
                options=p.get("varianti", {}),
            )
        acts = [
            Actuator(
                name=a["nosaukums"],
                lid=_int(a["lid"]),
                param=_int(a.get("parametrs", 0x07)),
                data=bytes.fromhex(a.get("dati", "")),
                duration=a.get("ilgums", 3.0),
                hint=a.get("piezime", ""),
            )
            for a in m.get("aktivizacijas", [])
        ]
        mods[key] = Module(
            key=key,
            name=m["nosaukums"],
            bus=m.get("kopne", "?"),
            endpoint=ep,
            status=m.get("statuss", ""),
            params=params,
            actuators=acts,
            id_options=[_int(x) for x in m.get("identifikacija", [])],
        )
    return mods


def save_user(key: str, patch: dict, user_file: Path = USER_FILE) -> None:
    """Saglabā izmaiņas lietotāja failā (piem. atrastu moduļa adresi vai parametra nosaukumu)."""
    data = json.loads(user_file.read_text(encoding="utf-8")) if user_file.exists() else {}
    data[key] = _merge(data.get(key, {}), patch)
    user_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
