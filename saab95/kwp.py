"""Vispārīgs Saab KWP2000-pār-CAN klients jebkuram 9-5 vadības modulim.

Saab 9-5 diagnostika izmanto "rindu" transporta protokolu:
  init_tx (0x220) -> sesijas sākums: [3F 81 00 <mērķis> 02 40 00 00]
  init_rx (0x238) <- apstiprinājums
  req     (0x240) -> KWP pieprasījums, 6 baitu rindās: [galvene, A1, 6 baiti]
  resp    (0x258) <- KWP atbilde rindās
  ack     (0x266) -> apstiprinājums katrai atbildes rindai

Trionic 7 parametri (mērķis 0x11) ir zināmi no TrionicCANFlasher. Pārējiem
moduļiem mērķa adrese un ID jāatrod ar `saab95 discover` (skat. modules.py).
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from .obd2 import decode_dtc
from .transport import CanFrame, Transport

NRC = {
    0x10: "vispārēja atteikšana",
    0x11: "serviss netiek atbalstīts",
    0x12: "apakšfunkcija netiek atbalstīta / nepareizs formāts",
    0x21: "aizņemts, atkārtojiet",
    0x22: "nosacījumi nav izpildīti (piem. dzinējs darbojas)",
    0x31: "pieprasījums ārpus diapazona",
    0x33: "piekļuve liegta (vajadzīga drošības atslēga)",
    0x35: "nepareiza atslēga",
    0x36: "pārsniegts mēģinājumu skaits",
    0x37: "jānogaida pirms nākamā mēģinājuma",
    0x78: "atbilde gaidāma",
}


class KwpError(Exception):
    def __init__(self, msg: str, nrc: int | None = None):
        super().__init__(msg)
        self.nrc = nrc


@dataclass(frozen=True)
class Endpoint:
    target: int = 0x11
    init_tx: int = 0x220
    init_rx: int = 0x238
    req: int = 0x240
    resp: int = 0x258
    ack: int = 0x266


@dataclass
class Dtc:
    code: str
    status: int

    @property
    def active(self) -> bool:
        return bool(self.status & 0x01) or bool(self.status & 0x40)

    def __str__(self) -> str:
        return f"{self.code} (statuss 0x{self.status:02X})"


def calculate_key(seed: int, method: int) -> int:
    """Trionic 7 drošības atslēgas algoritms (publiski zināms)."""
    key = (seed << 2) & 0xFFFF
    if method == 0:
        key = (key ^ 0x8142) - 0x2356
    elif method == 1:
        key = (key ^ 0x4081) - 0x1F6F
    else:
        raise ValueError("method jābūt 0 vai 1")
    return key & 0xFFFF


def _pad(b) -> bytes:
    b = bytes(b)
    return b + bytes(8 - len(b))


def printable(raw: bytes) -> str:
    s = raw.rstrip(b"\x00 ")
    if s and all(32 <= b < 127 for b in s):
        return s.decode("ascii")
    return raw.hex(" ").upper()


class SaabKwp:
    def __init__(self, tr: Transport, ep: Endpoint = Endpoint(), timeout: float = 1.0):
        self.tr = tr
        self.ep = ep
        self.timeout = timeout
        self.unlocked = False
        self._last = 0.0

    # ---------- transports ----------
    def init_frame(self) -> bytes:
        return bytes([0x3F, 0x81, 0x00, self.ep.target, 0x02, 0x40, 0x00, 0x00])

    def connect(self, retries: int = 3) -> None:
        self.tr.set_rx_filter([self.ep.init_rx])
        for _ in range(retries):
            self.tr.send(CanFrame(self.ep.init_tx, self.init_frame()), expect=1)
            if self.tr.wait_for(self.ep.init_rx, self.timeout):
                self.tr.set_rx_filter([self.ep.resp])
                self._last = time.monotonic()
                return
        raise KwpError(f"Modulis 0x{self.ep.target:02X} neatbild")

    def request(self, payload: bytes) -> bytes:
        buf = bytes([len(payload)]) + bytes(payload)
        rows = [buf[i : i + 6] for i in range(0, len(buf), 6)]
        for i, row in enumerate(rows):
            left = len(rows) - 1 - i
            hdr = left | (0x40 if i == 0 else 0x00)
            self.tr.send(CanFrame(self.ep.req, _pad([hdr, 0xA1, *row])), expect=1 if left == 0 else 0)
        for _ in range(50):
            resp = self._read_response()
            if resp[:1] == b"\x7F" and len(resp) >= 3:
                if resp[2] == 0x78:
                    continue
                raise KwpError(
                    f"Modulis atteica servisu 0x{resp[1]:02X}: {NRC.get(resp[2], f'kods 0x{resp[2]:02X}')}", resp[2]
                )
            if resp[0] != (payload[0] | 0x40):
                raise KwpError(f"Negaidīta atbilde: {resp.hex(' ')}")
            self._last = time.monotonic()
            return resp
        raise KwpError("Modulis pārāk ilgi apstrādā pieprasījumu")

    def _read_response(self) -> bytes:
        data = bytearray()
        length = None
        while True:
            f = self.tr.wait_for(self.ep.resp, self.timeout)
            if f is None:
                raise KwpError("Nav atbildes no moduļa")
            hdr = f.data[0]
            left = hdr & 0x3F
            if hdr & 0x40:
                length = f.data[2]
                data = bytearray(f.data[3:8])
            else:
                data += f.data[2:8]
            self.tr.send(CanFrame(self.ep.ack, _pad([0x40, 0xA1, 0x3F, hdr & 0xBF])), expect=1 if left else 0)
            if left == 0:
                if length is None:
                    raise KwpError("Atbilde bez pirmās rindas")
                return bytes(data[:length])

    def keepalive(self) -> None:
        if time.monotonic() - self._last > 2.0:
            self.request(b"\x3E")

    # ---------- KWP2000 servisi ----------
    def start_session(self, mode: int = 0x85) -> None:
        """0x81 standarta, 0x85 programmēšanas, 0x86 paplašinātā (atkarīgs no moduļa)."""
        self.request(bytes([0x10, mode]))

    def security_access(self) -> int:
        for method in (0, 1):
            r = self.request(bytes([0x27, 0x05]))
            seed = (r[2] << 8) | r[3]
            key = calculate_key(seed, method)
            try:
                self.request(bytes([0x27, 0x06, key >> 8, key & 0xFF]))
                self.unlocked = True
                return method
            except KwpError as e:
                if e.nrc != 0x35:
                    raise
        raise KwpError("Drošības piekļuve neizdevās (algoritms zināms tikai Trionic 7)")

    def read_ecu_id(self, option: int) -> bytes:
        return self.request(bytes([0x1A, option]))[2:]

    def read_local_id(self, lid: int) -> bytes:
        return self.request(bytes([0x21, lid]))[2:]

    def write_local_id(self, lid: int, data: bytes) -> None:
        if not self.unlocked:
            self.security_access()
        self.request(bytes([0x3B, lid, *data]))

    def read_dtcs(self) -> list[Dtc]:
        """readDiagnosticTroubleCodesByStatus – visi kodi visās grupās."""
        r = self.request(bytes([0x18, 0x02, 0xFF, 0x00]))
        n = r[1]
        out = []
        for i in range(n):
            b = r[2 + 3 * i : 5 + 3 * i]
            if len(b) == 3:
                out.append(Dtc(decode_dtc(b[0], b[1]), b[2]))
        return out

    def clear_dtcs(self) -> None:
        self.request(bytes([0x14, 0xFF, 0x00]))

    def io_control(self, lid: int, param: int, data: bytes = b"") -> bytes:
        """inputOutputControlByLocalIdentifier – izpildmehānismu aktivizēšana.

        param: 0x00 atdot vadību ECU, 0x07 īslaicīga iestatīšana (biežākais).
        """
        return self.request(bytes([0x30, lid, param, *data]))[2:]

    def start_routine(self, rid: int, data: bytes = b"") -> bytes:
        return self.request(bytes([0x31, rid, *data]))[2:]

    def read_memory(self, address: int, length: int) -> bytes:
        """Atmiņas lasīšana ar dinamisko identifikatoru 0xF0 (T7 metode)."""
        if not 0 < length <= 0xF0:
            raise ValueError("garums 1..240")
        self.request(bytes([0x2C, 0xF0, 0x03, 0x00, length, (address >> 16) & 0xFF, (address >> 8) & 0xFF, address & 0xFF]))
        return self.read_local_id(0xF0)[:length]
