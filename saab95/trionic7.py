"""Saab Trionic 7 (benzīna 2.0t/2.3t/Aero ECU) – īpašgadījums no kwp.SaabKwp."""
from __future__ import annotations

from .kwp import NRC, Endpoint, KwpError, SaabKwp, calculate_key, printable  # noqa: F401
from .transport import Transport

T7_ENDPOINT = Endpoint(target=0x11)

KNOWN_LIDS: dict[int, str] = {
    0x90: "VIN (Trionic)",
}

_printable = printable  # atpakaļsaderībai


class Trionic7(SaabKwp):
    def __init__(self, tr: Transport, timeout: float = 1.0):
        super().__init__(tr, T7_ENDPOINT, timeout)

    def identify(self) -> dict[str, str]:
        info = {}
        for lid, name in KNOWN_LIDS.items():
            try:
                info[name] = printable(self.read_local_id(lid))
            except KwpError as e:
                info[name] = f"<{e}>"
        return info
