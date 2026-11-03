"""Standarta OBD-II / EOBD (ISO 15765-4, CAN 11-bit, 500 kbit/s).

Trionic 7 dzinēja ECU atbild uz 0x7E0 (fiziskā) / 0x7DF (funkcionālā adrese),
atbildes nāk no 0x7E8.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import isotp
from .transport import Transport

FUNC_ID = 0x7DF
ECU_TX = 0x7E0
ECU_RX = 0x7E8


class ObdError(Exception):
    pass


@dataclass(frozen=True)
class Pid:
    pid: int
    name: str
    title: str
    unit: str
    nbytes: int
    decode: Callable[[bytes], float]


def _u16(d: bytes) -> int:
    return (d[0] << 8) | d[1]


PIDS: dict[str, Pid] = {
    p.name: p
    for p in [
        Pid(0x04, "load", "Dzinēja slodze", "%", 1, lambda d: d[0] * 100 / 255),
        Pid(0x05, "coolant", "Dzesēšanas šķidruma temp.", "°C", 1, lambda d: d[0] - 40),
        Pid(0x06, "stft", "Īstermiņa degvielas korekcija", "%", 1, lambda d: (d[0] - 128) * 100 / 128),
        Pid(0x07, "ltft", "Ilgtermiņa degvielas korekcija", "%", 1, lambda d: (d[0] - 128) * 100 / 128),
        Pid(0x0B, "map", "Ieplūdes kolektora spiediens", "kPa", 1, lambda d: d[0]),
        Pid(0x0C, "rpm", "Apgriezieni", "apgr/min", 2, lambda d: _u16(d) / 4),
        Pid(0x0D, "speed", "Ātrums", "km/h", 1, lambda d: d[0]),
        Pid(0x0E, "timing", "Aizdedzes apsteidze", "°", 1, lambda d: d[0] / 2 - 64),
        Pid(0x0F, "iat", "Ieplūdes gaisa temp.", "°C", 1, lambda d: d[0] - 40),
        Pid(0x10, "maf", "Gaisa plūsma (MAF)", "g/s", 2, lambda d: _u16(d) / 100),
        Pid(0x11, "throttle", "Droseles stāvoklis", "%", 1, lambda d: d[0] * 100 / 255),
        Pid(0x1F, "runtime", "Laiks kopš iedarbināšanas", "s", 2, lambda d: _u16(d)),
        Pid(0x21, "mil_dist", "Nobraukts ar ieslēgtu MIL", "km", 2, lambda d: _u16(d)),
        Pid(0x2F, "fuel", "Degvielas līmenis", "%", 1, lambda d: d[0] * 100 / 255),
        Pid(0x33, "baro", "Atmosfēras spiediens", "kPa", 1, lambda d: d[0]),
        Pid(0x42, "voltage", "Vadības moduļa spriegums", "V", 2, lambda d: _u16(d) / 1000),
        Pid(0x46, "ambient", "Āra gaisa temp.", "°C", 1, lambda d: d[0] - 40),
    ]
}
PIDS_BY_NUM = {p.pid: p for p in PIDS.values()}


def decode_dtc(b1: int, b2: int) -> str:
    letter = "PCBU"[b1 >> 6]
    return f"{letter}{(b1 >> 4) & 0x3}{b1 & 0xF:X}{b2 >> 4:X}{b2 & 0xF:X}"


# Biežākie Saab specifiskie kodi (T7). Pilnu sarakstu skat. Saab servisa dokumentācijā.
DTC_HINTS = {
    "P0105": "MAP sensors",
    "P0171": "Maisījums par liesu",
    "P0172": "Maisījums par bagātu",
    "P0300": "Izlaidumi (vairāki cilindri)",
    "P0420": "Katalizatora efektivitāte zema",
    "P1105": "Atmosfēras spiediena sensors (Saab)",
    "P1110": "Turbo spiediena vārsts (BPC) (Saab)",
    "P1115": "Turbo spiediena regulēšana (Saab)",
    "P1130": "Lambda zondes signāls (Saab)",
    "P1321": "Aizdedzes kasete (DI) – detonācijas signāls (Saab)",
    "P1334": "Aizdedzes kasete (DI) – sinhronizācija (Saab)",
}


class Obd2:
    def __init__(self, tr: Transport, timeout: float = 1.0):
        self.tr = tr
        self.timeout = timeout

    def _req(self, payload: bytes) -> bytes:
        for _ in range(10):
            resp = isotp.request(self.tr, ECU_TX, ECU_RX, payload, self.timeout)
            if resp[:1] == b"\x7F":
                if len(resp) >= 3 and resp[2] == 0x78:
                    continue  # response pending
                raise ObdError(f"Negatīva atbilde: {resp.hex(' ')}")
            if resp[0] != payload[0] + 0x40:
                raise ObdError(f"Negaidīta atbilde: {resp.hex(' ')}")
            return resp
        raise ObdError("ECU pārāk ilgi apstrādā pieprasījumu")

    def supported_pids(self) -> set[int]:
        result: set[int] = set()
        base = 0x00
        while base <= 0xA0:
            try:
                r = self._req(bytes([0x01, base]))
            except (ObdError, isotp.IsoTpError):
                break
            bits = int.from_bytes(r[2:6], "big")
            for i in range(32):
                if bits & (1 << (31 - i)):
                    result.add(base + i + 1)
            if not bits & 1:
                break
            base += 0x20
        return result

    def read_pid(self, name: str) -> float:
        p = PIDS[name]
        r = self._req(bytes([0x01, p.pid]))
        if r[1] != p.pid:
            raise ObdError("Atbilde neatbilst pieprasītajam PID")
        return p.decode(r[2 : 2 + p.nbytes])

    def read_dtcs(self, pending: bool = False) -> list[str]:
        r = self._req(bytes([0x07 if pending else 0x03]))
        data = r[2:]  # CAN: r[1] = kodu skaits
        codes = []
        for i in range(0, len(data) - 1, 2):
            if data[i] or data[i + 1]:
                codes.append(decode_dtc(data[i], data[i + 1]))
        return codes

    def clear_dtcs(self) -> None:
        self._req(bytes([0x04]))

    def read_vin(self) -> str:
        r = self._req(bytes([0x09, 0x02]))
        return r[3:].decode("ascii", errors="replace").strip("\x00 ")
