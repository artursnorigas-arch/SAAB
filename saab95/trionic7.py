"""Saab Trionic 7 (benzīna 2.0t/2.3t/Aero ECU) – KWP2000 pār Saab CAN.

Protokols (pēc atvērtā koda TrionicCANFlasher / T7Suite apraksta):
  0x220 -> ECU : sesijas sākums (satur KWP startCommunication 0x81)
  0x238 <- ECU : sesijas apstiprinājums
  0x240 -> ECU : KWP pieprasījums, sadalīts 6 baitu "rindās"
  0x258 <- ECU : KWP atbilde, sadalīta rindās
  0x266 -> ECU : apstiprinājums (ACK) katrai saņemtajai rindai

Rindas formāts: [galvene, 0xA1, 6 datu baiti]; galvenes 0x40 bits = pirmā rinda,
apakšējie biti = cik rindu vēl sekos. Pirmās rindas pirmais datu baits = garums.

UZMANĪBU: modulis ir eksperimentāls. Pirms rakstīšanas vienmēr
izveidojiet rezerves kopiju (CLI to dara automātiski).
"""
from __future__ import annotations

import time

from .transport import CanFrame, Transport

INIT_TX, INIT_RX = 0x220, 0x238
REQ_TX, RESP_RX, ACK_TX = 0x240, 0x258, 0x266

INIT_FRAME = bytes([0x3F, 0x81, 0x00, 0x11, 0x02, 0x40, 0x00, 0x00])

NRC = {
    0x10: "vispārēja atteikšana",
    0x11: "serviss netiek atbalstīts",
    0x12: "apakšfunkcija netiek atbalstīta / nepareizs formāts",
    0x21: "aizņemts, atkārtojiet",
    0x22: "nosacījumi nav izpildīti",
    0x31: "pieprasījums ārpus diapazona",
    0x33: "piekļuve liegta (vajadzīga drošības atslēga)",
    0x35: "nepareiza atslēga",
    0x36: "pārsniegts mēģinājumu skaits",
    0x37: "jānogaida pirms nākamā mēģinājuma",
    0x78: "atbilde gaidāma",
}

# Zināmie lokālie identifikatori. Tikai 0x90 (VIN) ir plaši dokumentēts;
# pārējos atrodiet ar `saab95 t7-scan` un pierakstiet šeit.
KNOWN_LIDS: dict[int, str] = {
    0x90: "VIN (Trionic)",
}


class KwpError(Exception):
    def __init__(self, msg: str, nrc: int | None = None):
        super().__init__(msg)
        self.nrc = nrc


def calculate_key(seed: int, method: int) -> int:
    """T7 drošības piekļuves atslēgas aprēķins (publiski zināms algoritms)."""
    key = (seed << 2) & 0xFFFF
    if method == 0:
        key ^= 0x8142
        key -= 0x2356
    elif method == 1:
        key ^= 0x4081
        key -= 0x1F6F
    else:
        raise ValueError("method jābūt 0 vai 1")
    return key & 0xFFFF


def _pad(b) -> bytes:
    b = bytes(b)
    return b + bytes(8 - len(b))


class Trionic7:
    def __init__(self, tr: Transport, timeout: float = 1.0):
        self.tr = tr
        self.timeout = timeout
        self.unlocked = False
        self._last = 0.0

    # --- sesija un rindu protokols ---
    def connect(self) -> None:
        self.tr.set_rx_filter([INIT_RX])
        for _ in range(3):
            self.tr.send(CanFrame(INIT_TX, INIT_FRAME), expect=1)
            if self.tr.wait_for(INIT_RX, self.timeout):
                self.tr.set_rx_filter([RESP_RX])
                self._last = time.monotonic()
                return
        raise KwpError("Trionic 7 neatbild (pārbaudiet aizdedzi, adapteri un 500 kbit/s P-Bus)")

    def request(self, payload: bytes) -> bytes:
        buf = bytes([len(payload)]) + bytes(payload)
        rows = [buf[i : i + 6] for i in range(0, len(buf), 6)]
        for i, row in enumerate(rows):
            left = len(rows) - 1 - i
            hdr = left | (0x40 if i == 0 else 0x00)
            self.tr.send(CanFrame(REQ_TX, _pad([hdr, 0xA1, *row])), expect=1 if left == 0 else 0)
        for _ in range(50):
            resp = self._read_response()
            if resp[:1] == b"\x7F" and len(resp) >= 3:
                if resp[2] == 0x78:
                    continue
                raise KwpError(
                    f"ECU atteica serviss 0x{resp[1]:02X}: {NRC.get(resp[2], 'kods 0x%02X' % resp[2])}", resp[2]
                )
            if resp[0] != (payload[0] | 0x40):
                raise KwpError(f"Negaidīta atbilde: {resp.hex(' ')}")
            self._last = time.monotonic()
            return resp
        raise KwpError("ECU pārāk ilgi apstrādā pieprasījumu")

    def _read_response(self) -> bytes:
        data = bytearray()
        length = None
        while True:
            f = self.tr.wait_for(RESP_RX, self.timeout)
            if f is None:
                raise KwpError("Nav atbildes no Trionic 7")
            hdr = f.data[0]
            left = hdr & 0x3F
            if hdr & 0x40:
                length = f.data[2]
                data = bytearray(f.data[3:8])
            else:
                data += f.data[2:8]
            self.tr.send(CanFrame(ACK_TX, _pad([0x40, 0xA1, 0x3F, hdr & 0xBF])), expect=1 if left else 0)
            if left == 0:
                if length is None:
                    raise KwpError("Atbilde bez pirmās rindas")
                return bytes(data[:length])

    def keepalive(self) -> None:
        if time.monotonic() - self._last > 2.0:
            self.request(b"\x3E")

    # --- KWP2000 servisi ---
    def security_access(self) -> int:
        """Atbloķē ECU rakstīšanai. Atgriež izmantoto metodi."""
        for method in (0, 1):
            r = self.request(bytes([0x27, 0x05]))
            seed = (r[2] << 8) | r[3]
            key = calculate_key(seed, method)
            try:
                self.request(bytes([0x27, 0x06, key >> 8, key & 0xFF]))
                self.unlocked = True
                return method
            except KwpError as e:
                if e.nrc not in (0x35,):
                    raise
        raise KwpError("Drošības piekļuve neizdevās ar abām metodēm")

    def read_local_id(self, lid: int) -> bytes:
        r = self.request(bytes([0x21, lid]))
        return r[2:]

    def write_local_id(self, lid: int, data: bytes) -> None:
        if not self.unlocked:
            self.security_access()
        self.request(bytes([0x3B, lid, *data]))

    def read_memory(self, address: int, length: int) -> bytes:
        """Nolasa atmiņu, definējot dinamisko identifikatoru 0xF0 (T7 metode)."""
        if not 0 < length <= 0xF0:
            raise ValueError("garums 1..240")
        self.request(bytes([0x2C, 0xF0, 0x03, 0x00, length, (address >> 16) & 0xFF, (address >> 8) & 0xFF, address & 0xFF]))
        return self.read_local_id(0xF0)[:length]

    def identify(self) -> dict[str, str]:
        info = {}
        for lid, name in KNOWN_LIDS.items():
            try:
                raw = self.read_local_id(lid)
                info[name] = _printable(raw)
            except KwpError as e:
                info[name] = f"<{e}>"
        return info


def _printable(raw: bytes) -> str:
    if raw and all(32 <= b < 127 for b in raw.rstrip(b"\x00")):
        return raw.rstrip(b"\x00").decode("ascii")
    return raw.hex(" ").upper()
