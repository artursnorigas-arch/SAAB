import json

import pytest

from saab95 import cli, isotp, obd2, trionic7
from saab95.simulator import SIM_VIN, SimulatedCar


@pytest.fixture
def car():
    return SimulatedCar()


def test_dtc_decode():
    assert obd2.decode_dtc(0x01, 0x71) == "P0171"
    assert obd2.decode_dtc(0x11, 0x05) == "P1105"
    assert obd2.decode_dtc(0xC1, 0x00) == "U0100"


def test_obd_vin_multiframe(car):
    assert obd2.Obd2(car).read_vin() == SIM_VIN


def test_obd_pids_and_dtcs(car):
    o = obd2.Obd2(car)
    sup = o.supported_pids()
    assert 0x0C in sup and 0x42 in sup
    assert 700 < o.read_pid("rpm") < 1700
    assert o.read_pid("coolant") == 89
    assert o.read_dtcs() == ["P0171", "P1105"]
    o.clear_dtcs()
    assert o.read_dtcs() == []


def test_seed_key_known_values():
    assert trionic7.calculate_key(0x1234, 0) == ((((0x1234 << 2) & 0xFFFF) ^ 0x8142) - 0x2356) & 0xFFFF
    assert trionic7.calculate_key(0x0000, 1) == (0x4081 - 0x1F6F) & 0xFFFF


def test_t7_read_write_multirow(car):
    t = trionic7.Trionic7(car)
    t.connect()
    assert t.read_local_id(0x90) == SIM_VIN.encode()  # 19 baitu atbilde = 4 rindas
    t.write_local_id(0x97, b"B235E")
    assert t.unlocked
    assert t.read_local_id(0x97) == b"B235E"


def test_t7_negative_response(car):
    t = trionic7.Trionic7(car)
    t.connect()
    with pytest.raises(trionic7.KwpError) as e:
        t.read_local_id(0x55)
    assert e.value.nrc == 0x31


def test_t7_memory(car):
    t = trionic7.Trionic7(car)
    t.connect()
    assert t.read_memory(0x1000, 0x80) == car.t7_memory[0x1000:0x1080]


def test_isotp_long_request_flow_control():
    sent = []

    class Echo(SimulatedCar):
        def send(self, frame, expect=None):
            sent.append(frame)
            if frame.data[0] >> 4 == 1:
                self._emit(0x7E8, [0x30, 0x00, 0x00])
            elif frame.data[0] >> 4 == 2 and len(sent) == 3:
                self._emit(0x7E8, [0x01, 0x50])

    r = isotp.request(Echo(), 0x7E0, 0x7E8, bytes(range(20)))
    assert r == b"\x50"
    assert [f.data[0] for f in sent] == [0x10, 0x21, 0x22]


def test_cli_write_dry_run_and_apply(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["--sim", "t7-write", "0x97", "ascii:B235E"]) == 0
    assert "Sausais režīms" in capsys.readouterr().out
    assert cli.main(["--sim", "-y", "t7-write", "0x97", "ascii:B235E", "--apply"]) == 0
    out = capsys.readouterr().out
    assert "Ierakstīts un pārbaudīts" in out
    backups = list((tmp_path / "rezerves_kopijas").glob("*.json"))
    assert json.loads(backups[0].read_text())["hex"] == b"B235R".hex()


def test_cli_smoke(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["--sim", "info"]) == 0
    assert cli.main(["--sim", "live", "--count", "1", "--interval", "0", "--csv", "z.csv"]) == 0
    assert cli.main(["--sim", "t7-scan", "--out", "s.json"]) == 0
    assert "0x90" in json.loads((tmp_path / "s.json").read_text())
    assert cli.main(["--sim", "t7-dump", "d.bin", "--length", "0x400"]) == 0
    assert (tmp_path / "d.bin").stat().st_size == 0x400


def test_elm_parse():
    from collections import deque

    from saab95.transport import Elm327Transport

    e = Elm327Transport.__new__(Elm327Transport)
    e._queue, e._rx = deque(), 0x7E8
    e._parse("7E8 10 14 49 02 01 59 53 33\r7E8 21 45 48 35 39 47 35 37\r\rNO DATA")
    assert len(e._queue) == 2
    assert e.recv(0).data[:2] == bytes([0x10, 0x14])
