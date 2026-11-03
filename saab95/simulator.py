"""Virtuāls Saab 9-5 (Trionic 7 + OBD-II) testēšanai bez mašīnas."""
from __future__ import annotations

import math
import time
from collections import deque

from .transport import CanFrame, Transport
from .trionic7 import calculate_key

SIM_VIN = "YS3EH59G573000000"


def _pad(b) -> bytes:
    b = bytes(b)
    return b + bytes(8 - len(b))


class SimulatedCar(Transport):
    def __init__(self):
        self._out: deque[CanFrame] = deque()
        self._filter: set[int] | None = None
        self._t0 = time.monotonic()
        self.dtcs = [(0x01, 0x71), (0x11, 0x05)]  # P0171, P1105
        # ISO-TP izejošā daudzkadru atbilde, kas gaida FC
        self._pending_cf: list[bytes] = []
        # KWP moduļi: mērķa adrese -> stāvoklis
        self.modules: dict[int, dict] = {
            0x11: {  # Trionic 7
                "lids": {
                    0x90: SIM_VIN.encode(),
                    0x91: b"5380691",
                    0x94: b"EH0X_31L.24E",
                    0x97: b"B235R",
                },
                "dtcs": [(0x01, 0x71, 0x01)],
                "seed": 0x1234,
                "io": {},
            },
            0x28: {  # FIKTĪVS ABS modulis – tikai simulatoram, NAV īstā adrese
                "lids": {0x01: b"SIM-ABS 5.7", 0x10: bytes([0x01])},
                "dtcs": [(0x50, 0x35, 0x41), (0x50, 0x40, 0x00)],
                "seed": 0x0BEE,
                "io": {0x20: "Kreisā priekšējā riteņa vārsts"},
            },
        }
        self.active: int | None = None
        self.t7_session = False
        self.unlocked: set[int] = set()
        self.io_log: list[tuple[int, int, int]] = []
        self.t7_memory = bytes((i * 7 + (i >> 8)) & 0xFF for i in range(0x80000))
        self._dyn_f0: tuple[int, int] | None = None
        self._t7_req = bytearray()
        self._t7_resp_rows: list[bytes] = []
        self.writes: list[tuple[int, bytes]] = []

    # --- Transport ---
    def send(self, frame: CanFrame, expect: int | None = None) -> None:
        if self.debug:
            print(f"TX {frame}")
        if frame.arb_id in (0x7DF, 0x7E0):
            self._obd_frame(frame.data)
        elif frame.arb_id == 0x220:
            target = frame.data[3]
            if target in self.modules:
                self.active = target
                self.t7_session = True
                self._emit(0x238, [0x40, 0xBF, 0x21, 0xC1, 0x00, target, 0x02, 0x58])
        elif frame.arb_id == 0x240 and self.t7_session:
            self._t7_row(frame.data)
        elif frame.arb_id == 0x266 and self.t7_session:
            if self._t7_resp_rows:
                self._out.append(CanFrame(0x258, self._t7_resp_rows.pop(0)))

    def recv(self, timeout: float) -> CanFrame | None:
        while self._out:
            f = self._out.popleft()
            if self._filter is None or f.arb_id in self._filter:
                if self.debug:
                    print(f"RX {f}")
                return f
        return None

    def set_rx_filter(self, arb_ids):
        self._filter = None if arb_ids is None else set(arb_ids)

    def _emit(self, arb, data):
        self._out.append(CanFrame(arb, _pad(data)))

    # --- OBD-II ECU ---
    def _obd_frame(self, d: bytes) -> None:
        pci = d[0] >> 4
        if pci == 3 and self._pending_cf:
            for cf in self._pending_cf:
                self._out.append(CanFrame(0x7E8, cf))
            self._pending_cf = []
            return
        if pci != 0:
            return
        req = d[1 : 1 + (d[0] & 0xF)]
        resp = self._obd_service(req)
        if resp is not None:
            self._isotp_out(resp)

    def _isotp_out(self, resp: bytes) -> None:
        if len(resp) <= 7:
            self._emit(0x7E8, [len(resp), *resp])
            return
        n = len(resp)
        self._emit(0x7E8, [0x10 | (n >> 8), n & 0xFF, *resp[:6]])
        sn, idx = 1, 6
        while idx < n:
            self._pending_cf.append(_pad([0x20 | sn, *resp[idx : idx + 7]]))
            idx += 7
            sn = (sn + 1) & 0xF

    def _obd_service(self, req: bytes) -> bytes | None:
        t = time.monotonic() - self._t0
        rpm = 850 + 400 * (1 + math.sin(t / 3))
        values = {
            0x04: [int(25 + 10 * math.sin(t))],
            0x05: [40 + 89],
            0x06: [130],
            0x07: [124],
            0x0B: [int(35 + 20 * (1 + math.sin(t / 3)))],
            0x0C: list(int(rpm * 4).to_bytes(2, "big")),
            0x0D: [0],
            0x0E: [int((12 + 64) * 2)],
            0x0F: [40 + 22],
            0x10: list(int(450 + 300 * math.sin(t / 3)).to_bytes(2, "big")),
            0x11: [int(255 * 0.12)],
            0x1F: list(int(t).to_bytes(2, "big")),
            0x33: [101],
            0x42: list((14150).to_bytes(2, "big")),
        }
        svc = req[0]
        if svc == 0x01:
            pid = req[1]
            if pid in (0x00, 0x20, 0x40):
                bits = 0
                for p in values:
                    if pid < p <= pid + 32:
                        bits |= 1 << (32 - (p - pid))
                if pid == 0x00:
                    bits |= 1  # atbalsta nākamo diapazonu
                if pid == 0x20:
                    bits |= 1
                return bytes([0x41, pid, *bits.to_bytes(4, "big")])
            if pid in values:
                return bytes([0x41, pid, *values[pid]])
            return bytes([0x7F, 0x01, 0x12])
        if svc in (0x03, 0x07):
            codes = self.dtcs if svc == 0x03 else []
            flat = [b for c in codes for b in c]
            return bytes([svc + 0x40, len(codes), *flat])
        if svc == 0x04:
            self.dtcs = []
            return bytes([0x44])
        if svc == 0x09 and req[1] == 0x02:
            return bytes([0x49, 0x02, 0x01, *SIM_VIN.encode()])
        return bytes([0x7F, svc, 0x11])

    # --- Trionic 7 KWP ---
    def _t7_row(self, d: bytes) -> None:
        hdr = d[0]
        if hdr & 0x40:
            self._t7_req = bytearray(d[2:8])
        else:
            self._t7_req += d[2:8]
        if hdr & 0x3F:
            return
        n = self._t7_req[0]
        resp = self._t7_service(bytes(self._t7_req[1 : 1 + n]))
        buf = bytes([len(resp)]) + resp
        chunks =[buf[:6]] + [buf[i : i + 6] for i in range(6, len(buf), 6)]
        rows = []
        for i, c in enumerate(chunks):
            left = len(chunks) - 1 - i
            h = left | (0x40 if i == 0 else 0) | 0x80
            rows.append(_pad([h, 0xBF, *c]))
        self._out.append(CanFrame(0x258, rows[0]))
        self._t7_resp_rows = rows[1:]

    @property
    def t7_lids(self) -> dict[int, bytes]:
        return self.modules[0x11]["lids"]

    def _t7_service(self, req: bytes) -> bytes:
        m = self.modules[self.active]
        svc = req[0]
        if svc == 0x3E:
            return b"\x7E"
        if svc == 0x10:
            return bytes([0x50, req[1]])
        if svc == 0x27 and req[1] == 0x05:
            return bytes([0x67, 0x05, m["seed"] >> 8, m["seed"] & 0xFF])
        if svc == 0x27 and req[1] == 0x06:
            key = (req[2] << 8) | req[3]
            if key == calculate_key(m["seed"], 0):
                self.unlocked.add(self.active)
                return bytes([0x67, 0x06, 0x34])
            return bytes([0x7F, 0x27, 0x35])
        if svc == 0x1A:
            return bytes([0x5A, req[1], *b"SIM"])
        if svc == 0x18:
            flat = [b for d in m["dtcs"] for b in d]
            return bytes([0x58, len(m["dtcs"]), *flat])
        if svc == 0x14:
            m["dtcs"] = []
            return bytes([0x54, 0xFF, 0x00])
        if svc == 0x30:
            if req[1] not in m["io"]:
                return bytes([0x7F, 0x30, 0x31])
            self.io_log.append((self.active, req[1], req[2]))
            return bytes([0x70, req[1], req[2]])
        if svc == 0x21:
            lid = req[1]
            if lid == 0xF0 and self._dyn_f0 and self.active == 0x11:
                a, n = self._dyn_f0
                return bytes([0x61, 0xF0, *self.t7_memory[a : a + n]])
            if lid in m["lids"]:
                return bytes([0x61, lid, *m["lids"][lid]])
            return bytes([0x7F, 0x21, 0x31])
        if svc == 0x3B:
            if self.active not in self.unlocked:
                return bytes([0x7F, 0x3B, 0x33])
            lid = req[1]
            if lid not in m["lids"]:
                return bytes([0x7F, 0x3B, 0x31])
            m["lids"][lid] = bytes(req[2:])
            self.writes.append((lid, bytes(req[2:])))
            return bytes([0x7B, lid])
        if svc == 0x2C and req[1] == 0xF0:
            n = req[4]
            addr = (req[5] << 16) | (req[6] << 8) | req[7]
            self._dyn_f0 = (addr, n)
            return bytes([0x6C, 0xF0])
        return bytes([0x7F, svc, 0x11])
