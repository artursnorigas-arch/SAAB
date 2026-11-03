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


WIFI_DEFAULT = "192.168.0.10:35000"


def _open_port(port: str, baudrate: int, timeout: float):
    """COM5 / /dev/ttyUSB0 / 192.168.0.10:35000 / socket://... -> pyserial objekts."""
    import serial  # noqa: PLC0415 - neobligāta atkarība

    if "://" in port:
        return serial.serial_for_url(port, timeout=timeout)
    host, _, tail = port.rpartition(":")
    if host and tail.isdigit() and "." in host:
        return serial.serial_for_url(f"socket://{port}", timeout=timeout)
    return serial.Serial(port, baudrate, timeout=timeout)


class Elm327Transport(Transport):
    """ELM327 (USB, Bluetooth vai Wi-Fi) – arī lēti kloni.

    Pilnais režīms (ATCAF0): neapstrādāti CAN kadri → OBD-II + Saab Trionic 7.
    Ierobežotais režīms (ja klons neatbalsta ATCAF0): ELM pats veido ISO-TP →
    darbojas tikai OBD-II.

    ELM327 nevar pasīvi klausīties kopni – atbildes tiek nolasītas tikai pēc
    kadra nosūtīšanas. Pieprasījuma/atbildes diagnostikai ar to pietiek.
    """

    OBD_IDS = range(0x7DF, 0x7F0)

    def __init__(self, port: str, baudrate: int = 38400, protocol: str = "6", timeout: float = 3.0, ser=None):
        self.ser = ser if ser is not None else _open_port(port, baudrate, timeout)
        self._queue: deque[CanFrame] = deque()
        self._header: int | None = None
        self._rx: int | None = None
        self._responses_on = True
        self.caps = {"ATCAF0": True, "ATR0": True, "ATCRA": True, "skaits": True}
        self.version = self._cmd("ATZ", settle=1.5).splitlines()[-1:] or [""]
        self.version = self.version[0]
        for c in ("ATE0", "ATL0", "ATS1", "ATH1", f"ATSP{protocol}", "ATSTFF"):
            if not self._ok(c):
                raise TransportError(f"Adapteris nepieņēma pamata komandu {c} – vai tas tiešām ir ELM327?")
        self._ok("ATAT0")  # daži kloni neatbalsta – nav kritiski
        if not (self._ok("ATCAF0") and self._ok("ATCFC0")):
            self.caps["ATCAF0"] = False
            self._cmd("ATCAF1")
            self._cmd("ATCFC1")
        self._ok("ATR1")

    @property
    def raw_can(self) -> bool:
        return self.caps["ATCAF0"]

    def voltage(self) -> str:
        return self._cmd("ATRV")

    # --- zemā līmeņa komunikācija ---
    def _ok(self, cmd: str) -> bool:
        return "?" not in self._cmd(cmd)

    def _cmd(self, cmd: str, settle: float = 0.0) -> str:
        self.ser.reset_input_buffer()
        self.ser.write((cmd + "\r").encode("ascii"))
        if settle:
            time.sleep(settle)
        buf = b""
        while not buf.endswith(b">"):
            chunk = self.ser.read(max(1, getattr(self.ser, "in_waiting", 0) or 0))
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
                continue  # "NO DATA", "OK", "SEARCHING...", "CAN ERROR" u.c.
            try:
                arb = int(parts[0], 16)
                data = bytes(int(p, 16) for p in parts[1:])
            except ValueError:
                continue
            self._queue.append(CanFrame(arb, data))

    # --- Transport interfeiss ---
    def send(self, frame: CanFrame, expect: int | None = None) -> None:
        data = frame.data
        if not self.raw_can:
            if frame.arb_id not in self.OBD_IDS:
                raise TransportError(
                    "Šis ELM327 klons neatbalsta neapstrādātu CAN režīmu (ATCAF0), tāpēc Saab Trionic 7 un "
                    "citu moduļu funkcijas nav pieejamas. Darbojas tikai OBD-II (info, live, dtc, aero-check)."
                )
            pci = data[0] >> 4
            if pci == 3:
                return  # Flow Control nosūta pats ELM (ATCFC1)
            if pci != 0:
                raise TransportError("Ierobežotajā režīmā nevar sūtīt daudzkadru pieprasījumus")
            data = data[1 : 1 + (data[0] & 0x0F)]
            expect = None
        if self._header != frame.arb_id:
            self._cmd(f"ATSH{frame.arb_id:03X}")
            self._header = frame.arb_id
        want_resp = expect != 0 or not self.caps["ATR0"]
        if want_resp != self._responses_on:
            if self._ok("ATR1" if want_resp else "ATR0"):
                self._responses_on = want_resp
            else:
                self.caps["ATR0"] = False
        line = data.hex().upper()
        if expect and 0 < expect <= 15 and self.caps["skaits"]:
            out = self._cmd(line + f"{expect:X}")  # ELM atgriežas uzreiz pēc N atbildēm
            if out.strip() == "?":
                self.caps["skaits"] = False
                out = self._cmd(line)
        else:
            out = self._cmd(line)
        if "BUFFER FULL" in out or "CAN ERROR" in out:
            raise TransportError(f"ELM327 kļūda: {out}")
        if "UNABLE TO CONNECT" in out:
            raise TransportError("ELM327 nevar pieslēgties auto kopnei – vai aizdedze ir ON?")
        self._parse(out)

    def recv(self, timeout: float) -> CanFrame | None:
        while self._queue:
            f = self._queue.popleft()
            if self._rx is None or f.arb_id == self._rx:
                return f
        return None

    def set_rx_filter(self, arb_ids: list[int] | None) -> None:
        self._queue.clear()
        if arb_ids is None or len(arb_ids) != 1:
            self._cmd("ATAR")
            self._rx = None
            return
        self._rx = arb_ids[0]  # programmatiskais filtrs darbojas vienmēr
        if self.caps["ATCRA"] and not self._ok(f"ATCRA{arb_ids[0]:03X}"):
            self.caps["ATCRA"] = False

    def monitor(self, seconds: float) -> list[CanFrame]:
        """Pasīvā klausīšanās ar ATMA (lēti kloni var ziņot BUFFER FULL)."""
        self._cmd("ATAR")
        self._rx = None
        self.ser.reset_input_buffer()
        self.ser.write(b"ATMA\r")
        end = time.monotonic() + seconds
        buf = b""
        while time.monotonic() < end:
            buf += self.ser.read(self.ser.in_waiting or 1)
        self.ser.write(b"\r")
        time.sleep(0.2)
        buf += self.ser.read(self.ser.in_waiting)
        self._queue.clear()
        self._parse(buf.decode("ascii", errors="replace").replace(">", ""))
        frames = list(self._queue)
        self._queue.clear()
        return frames

    def close(self) -> None:
        try:
            self._cmd("ATPC")
        finally:
            self.ser.close()
