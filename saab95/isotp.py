"""Minimāla ISO 15765-2 (ISO-TP) klienta realizācija standarta OBD-II vajadzībām."""
from __future__ import annotations

import time

from .transport import CanFrame, Transport

PAD = 0x00


class IsoTpError(Exception):
    pass


def _pad(b) -> bytes:
    b = bytes(b)
    return b + bytes([PAD]) * (8 - len(b))


def request(tr: Transport, tx_id: int, rx_id: int, payload: bytes, timeout: float = 1.0) -> bytes:
    """Nosūta ISO-TP ziņojumu un atgriež pirmo atbildi no rx_id."""
    tr.set_rx_filter([rx_id])
    _send(tr, tx_id, rx_id, payload, timeout)
    return receive(tr, tx_id, rx_id, timeout)


def _send(tr: Transport, tx_id: int, rx_id: int, payload: bytes, timeout: float) -> None:
    n = len(payload)
    if n <= 7:
        tr.send(CanFrame(tx_id, _pad([n, *payload])), expect=1)
        return
    if n > 4095:
        raise IsoTpError("Ziņojums par garu ISO-TP")
    tr.send(CanFrame(tx_id, _pad([0x10 | (n >> 8), n & 0xFF, *payload[:6]])), expect=1)
    bs, st = _wait_fc(tr, rx_id, timeout)
    idx, sn, sent_in_block = 6, 1, 0
    while idx < n:
        chunk = payload[idx : idx + 7]
        idx += 7
        last = idx >= n
        sent_in_block += 1
        block_end = bs and sent_in_block == bs and not last
        tr.send(CanFrame(tx_id, _pad([0x20 | sn, *chunk])), expect=1 if (last or block_end) else 0)
        sn = (sn + 1) & 0x0F
        if block_end:
            bs, st = _wait_fc(tr, rx_id, timeout)
            sent_in_block = 0
        elif st:
            time.sleep(st / 1000 if st <= 0x7F else 0.0001)


def _wait_fc(tr: Transport, rx_id: int, timeout: float) -> tuple[int, int]:
    while True:
        fc = tr.wait_for(rx_id, timeout, lambda f: f.data and f.data[0] >> 4 == 3)
        if fc is None:
            raise IsoTpError("Netika saņemts Flow Control kadrs")
        status = fc.data[0] & 0x0F
        if status == 0:
            return fc.data[1], fc.data[2]
        if status == 2:
            raise IsoTpError("ECU ziņo par bufera pārpildi (FC overflow)")
        # status 1 = WAIT -> gaidām nākamo FC


def receive(tr: Transport, tx_id: int, rx_id: int, timeout: float = 1.0) -> bytes:
    f = tr.wait_for(rx_id, timeout, lambda f: f.data and f.data[0] >> 4 in (0, 1))
    if f is None:
        raise IsoTpError(f"Nav atbildes no {rx_id:03X}")
    pci = f.data[0] >> 4
    if pci == 0:
        return bytes(f.data[1 : 1 + (f.data[0] & 0x0F)])
    total = ((f.data[0] & 0x0F) << 8) | f.data[1]
    buf = bytearray(f.data[2:8])
    remaining_cf = -(-(total - 6) // 7)
    tr.send(CanFrame(tx_id, _pad([0x30, 0x00, 0x00])), expect=remaining_cf if remaining_cf <= 15 else None)
    sn = 1
    while len(buf) < total:
        cf = tr.wait_for(rx_id, timeout, lambda f: f.data and f.data[0] >> 4 == 2)
        if cf is None:
            raise IsoTpError("Pārtraukts daudzkadru ziņojums")
        if cf.data[0] & 0x0F != sn:
            raise IsoTpError(f"Nepareizs secības numurs {cf.data[0] & 0x0F}, gaidīts {sn}")
        buf += cf.data[1:8]
        sn = (sn + 1) & 0x0F
    return bytes(buf[:total])
