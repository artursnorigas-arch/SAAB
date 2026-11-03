"""Moduļu meklēšana un CAN kopnes monitors (Tech2 nav, bet bez tā nevar atrast adreses)."""
from __future__ import annotations

import time
from collections import Counter

from .kwp import Endpoint, KwpError, SaabKwp
from .transport import CanFrame, Elm327Transport, Transport


def monitor(tr: Transport, seconds: float) -> list[tuple[float, CanFrame]]:
    """Pasīvi klausās kopni. Ar ELM327 izmanto ATMA."""
    if isinstance(tr, Elm327Transport):
        return [(0.0, f) for f in tr.monitor(seconds)]
    tr.set_rx_filter(None)
    out = []
    t0 = time.monotonic()
    while (now := time.monotonic()) - t0 < seconds:
        f = tr.recv(min(0.1, seconds - (now - t0)))
        if f is not None:
            out.append((time.monotonic() - t0, f))
    return out


def summarize(frames: list[tuple[float, CanFrame]], seconds: float) -> list[dict]:
    cnt = Counter(f.arb_id for _, f in frames)
    last = {f.arb_id: f for _, f in frames}
    return [
        {"id": f"0x{i:03X}", "kadri": n, "hz": round(n / seconds, 1) if seconds else None, "pedejie_dati": last[i].data.hex(" ").upper()}
        for i, n in sorted(cnt.items())
    ]


def discover(tr: Transport, targets=range(0x01, 0x100), base: Endpoint = Endpoint(), timeout: float = 0.2,
             progress=None) -> list[dict]:
    """Sūta sesijas sākuma kadru katrai mērķa adresei un pieraksta, kurš atbild.

    Fona trafiks tiek izslēgts: vispirms 1 s klausāmies, kuri ID jau raida.
    """
    elm = isinstance(tr, Elm327Transport)
    background = set() if elm else {f.arb_id for _, f in monitor(tr, 1.0)}
    tr.set_rx_filter([base.init_rx] if elm else None)
    found = []
    for t in targets:
        if progress:
            progress(t)
        probe = SaabKwp(tr, Endpoint(t, base.init_tx, base.init_rx, base.req, base.resp, base.ack), timeout)
        tr.send(CanFrame(base.init_tx, probe.init_frame()), expect=1)
        answers = []
        deadline = time.monotonic() + timeout
        while (left := deadline - time.monotonic()) > 0:
            f = tr.recv(left)
            if f is None:
                break
            if f.arb_id not in background and f.arb_id != base.init_tx:
                answers.append(f)
        if not answers:
            continue
        entry = {
            "merkis": f"0x{t:02X}",
            "atbildes": [{"id": f"0x{f.arb_id:03X}", "dati": f.data.hex(" ").upper()} for f in answers],
            "kwp": False,
        }
        if any(f.arb_id == base.init_rx for f in answers):
            tr.set_rx_filter([base.resp])
            try:
                probe._last = 0
                probe.request(b"\x3E")
                entry["kwp"] = True
            except KwpError:
                pass
            tr.set_rx_filter([base.init_rx] if elm else None)
        found.append(entry)
    return found
