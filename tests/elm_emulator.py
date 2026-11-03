"""ELM327 Wi-Fi emulators testiem: TCP serveris virs SimulatedCar."""
from __future__ import annotations

import socket
import threading

from saab95.simulator import SimulatedCar
from saab95.transport import CanFrame


class ElmEmulator:
    def __init__(self, supports_caf0: bool = True, port: int = 0):
        self.car = SimulatedCar()
        self.car.set_rx_filter(None)
        self.supports_caf0 = supports_caf0
        self.srv = socket.create_server(("127.0.0.1", port))
        self.port = self.srv.getsockname()[1]
        self.reset()
        threading.Thread(target=self._serve, daemon=True).start()

    def reset(self):
        self.header, self.caf, self.cfc, self.resp, self.cra = 0x7DF, True, True, True, None

    def _serve(self):
        while True:
            conn, _ = self.srv.accept()
            threading.Thread(target=self._client, args=(conn,), daemon=True).start()

    def _client(self, conn):
        buf = b""
        with conn:
            while True:
                data = conn.recv(1024)
                if not data:
                    return
                buf += data
                while b"\r" in buf:
                    line, buf = buf.split(b"\r", 1)
                    reply = self.handle(line.decode().strip().upper().replace(" ", ""))
                    conn.sendall((reply + "\r\r>").encode())

    def _collect(self):
        out = []
        while (f := self.car.recv(0)) is not None:
            if self.cra is None or f.arb_id == self.cra:
                out.append(f)
        return out

    def _fmt(self, frames):
        return "\r".join(f"{f.arb_id:03X} " + " ".join(f"{b:02X}" for b in f.data) for f in frames) or "NO DATA"

    def handle(self, cmd: str) -> str:
        if cmd.startswith("AT"):
            c = cmd[2:]
            if c == "Z":
                self.reset()
                return "\r\rELM327 v1.5"
            if c == "I":
                return "ELM327 v1.5"
            if c == "RV":
                return "12.6V"
            if c == "CAF0":
                if not self.supports_caf0:
                    return "?"
                self.caf = False
                return "OK"
            if c == "CAF1":
                self.caf = True
                return "OK"
            if c in ("CFC0", "CFC1"):
                self.cfc = c == "CFC1"
                return "OK"
            if c in ("R0", "R1"):
                self.resp = c == "R1"
                return "OK"
            if c.startswith("SH"):
                self.header = int(c[2:], 16)
                return "OK"
            if c.startswith("CRA"):
                self.cra = int(c[3:], 16)
                return "OK"
            if c == "AR":
                self.cra = None
                return "OK"
            return "OK"
        if len(cmd) % 2:
            cmd = cmd[:-1]  # atbilžu skaita cipars
        data = bytes.fromhex(cmd)
        if self.caf:
            if self.header not in range(0x7DF, 0x7F0):
                return "NO DATA"
            data = bytes([len(data)]) + data
        self.car.send(CanFrame(self.header, data + bytes(8 - len(data))))
        frames = self._collect()
        if self.caf and self.cfc and frames and frames[0].data[0] >> 4 == 1:
            self.car.send(CanFrame(self.header if self.header != 0x7DF else 0x7E0, bytes([0x30] + [0] * 7)))
            frames += self._collect()
        if not self.resp:
            return ""
        return self._fmt(frames)
