"""CAN transporta slānis: kopīgs interfeiss ELM327 un python-can adapteriem.

Visi augstākie slāņi (ISO-TP, OBD-II, Trionic 7) strādā ar "neapstrādātiem"
CAN kadriem (ID + līdz 8 baitiem), tāpēc adapteri var brīvi mainīt.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class CanFrame:
    arb_id: int
    data: bytes

    def __str__(self) -> str:
        return f"{self.arb_id:03X} [{len(self.data)}] {self.data.hex(' ').upper()}"


class TransportError(Exception):
    pass


class Transport(ABC):
    """Neapstrādātu CAN kadru sūtīšana/saņemšana."""

    debug: bool = False

    @abstractmethod
    def send(self, frame: CanFrame, expect: int | None = None) -> None:
        """Nosūta kadru.

        expect – cik atbildes kadru gaidīt (0 = nevienu, None = nezināms).
        python-can to ignorē; ELM327 izmanto, lai negaidītu lieki.
        """

    @abstractmethod
    def recv(self, timeout: float) -> CanFrame | None:
        """Atgriež nākamo kadru, kas atbilst filtram, vai None."""

    @abstractmethod
    def set_rx_filter(self, arb_ids: list[int] | None) -> None:
        """Ierobežo saņemamos kadrus līdz norādītajiem ID (None = visi)."""

    def close(self) -> None:  # pragma: no cover - noklusējumā nav ko darīt
        pass

    def wait_for(self, arb_id: int, timeout: float, predicate=None) -> CanFrame | None:
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                return None
            f = self.recv(left)
            if f is None:
                return None
            if f.arb_id == arb_id and (predicate is None or predicate(f)):
                return f

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class PythonCanTransport(Transport):
    """Jebkurš python-can atbalstīts adapteris.

    Piemēri: interface="slcan" (Lawicel CANUSB, CANable), "kvaser", "pcan",
    "socketcan" (Linux, channel="can0"), "vector".
    Saab 9-5 P-Bus (dzinēja kopne) = 500 kbit/s.
    """

    def __init__(self, interface: str, channel: str, bitrate: int = 500_000, **kwargs):
        import can  # noqa: PLC0415 - neobligāta atkarība

        self._can = can
        self.bus = can.Bus(interface=interface, channel=channel, bitrate=bitrate, **kwargs)

    def send(self, frame: CanFrame, expect: int | None = None) -> None:
        if self.debug:
            print(f"TX {frame}")
        msg = self._can.Message(arbitration_id=frame.arb_id, data=frame.data, is_extended_id=False)
        self.bus.send(msg)

    def recv(self, timeout: float) -> CanFrame | None:
        msg = self.bus.recv(timeout)
        if msg is None:
            return None
        f = CanFrame(msg.arbitration_id, bytes(msg.data))
        if self.debug:
            print(f"RX {f}")
        return f

    def set_rx_filter(self, arb_ids: list[int] | None) -> None:
        if arb_ids is None:
            self.bus.set_filters(None)
        else:
            self.bus.set_filters([{"can_id": i, "can_mask": 0x7FF, "extended": False} for i in arb_ids])
        # Iztukšojam buferi no vecajiem kadriem
        while self.bus.recv(0) is not None:
            pass

    def close(self) -> None:
        self.bus.shutdown()


class Elm327Transport(Transport):
    """ELM327 (vai saderīgs, piem. OBDLink SX/MX+) neapstrādātā CAN režīmā.

    ELM327 nevar pasīvi klausīties kopni – atbildes tiek nolasītas tikai pēc
    kadra nosūtīšanas. Pieprasījuma/atbildes diagnostikai ar to pietiek.
    """

    def __init__(self, port: str, baudrate: int = 38400, protocol: str = "6", timeout: float = 3.0):
        import serial  # noqa: PLC0415 - neobligāta atkarība

        self.ser = serial.Serial(port, baudrate, timeout=timeout)
        self._queue: deque[CanFrame] = deque()
        self._header: int | None = None
        self._rx: int | None = None
        self._responses_on = True
        self._cmd("ATZ", settle=1.5)
        for c in ("ATE0", "ATL0", "ATS1", "ATH1", f"ATSP{protocol}", "ATCAF0", "ATCFC0", "ATAT0", "ATSTFF", "ATR1"):
            out = self._cmd(c)
            if "?" in out:
                raise TransportError(f"ELM327 nepieņēma komandu {c}: {out!r}")
        self.version = self._cmd("ATI")

    # --- zemā līmeņa seriālā komunikācija ---
    def _cmd(self, cmd: str, settle: float = 0.0) -> str:
        self.ser.reset_input_buffer()
        self.ser.write((cmd + "\r").encode("ascii"))
        if settle:
            time.sleep(settle)
        buf = b""
        while not buf.endswith(b">"):
            chunk = self.ser.read(1)
            if not chunk:
                break
            buf += chunk
        text = buf.decode("ascii", errors="replace").replace(">", "").strip()
        if self.debug:
            print(f"ELM> {cmd} -> {text!r}")
        return text

    def _parse(self, text: str) -> None:
        for line in text.replace("\r", "\n").split("\n"):
            parts = line.strip().split()
            if len(parts) < 2 or len(parts[0]) != 3:
                continue  # "NO DATA", "OK", "CAN ERROR" u.c.
            try:
                arb = int(parts[0], 16)
                data = bytes(int(p, 16) for p in parts[1:])
            except ValueError:
                continue
            self._queue.append(CanFrame(arb, data))

    # --- Transport interfeiss ---
    def send(self, frame: CanFrame, expect: int | None = None) -> None:
        if self._header != frame.arb_id:
            self._cmd(f"ATSH{frame.arb_id:03X}")
            self._header = frame.arb_id
        want_resp = expect != 0
        if want_resp != self._responses_on:
            self._cmd("ATR1" if want_resp else "ATR0")
            self._responses_on = want_resp
        line = frame.data.hex().upper()
        if expect and 0 < expect <= 15:
            line += f"{expect:X}"  # ELM atgriežas uzreiz pēc N atbildēm
        out = self._cmd(line)
        if "BUFFER FULL" in out or "CAN ERROR" in out:
            raise TransportError(f"ELM327 kļūda: {out}")
        self._parse(out)

    def recv(self, timeout: float) -> CanFrame | None:
        f = self._queue.popleft() if self._queue else None
        if f is not None and self._rx is not None and f.arb_id != self._rx:
            return self.recv(timeout)
        return f

    def set_rx_filter(self, arb_ids: list[int] | None) -> None:
        self._queue.clear()
        if arb_ids is None or len(arb_ids) != 1:
            self._cmd("ATAR")
            self._rx = None
        else:
            self._cmd(f"ATCRA{arb_ids[0]:03X}")
            self._rx = arb_ids[0]

    def close(self) -> None:
        try:
            self._cmd("ATPC")
        finally:
            self.ser.close()
