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


# ---------------- Tech2 funkcijas ----------------
from saab95 import actions, discovery, modules  # noqa: E402
from saab95.kwp import Endpoint, SaabKwp  # noqa: E402
from saab95.tech2 import Tech2  # noqa: E402


def test_discover_finds_modules(car):
    found = discovery.discover(car, range(0x10, 0x30), timeout=0.05)
    assert [f["merkis"] for f in found] == ["0x11", "0x28"]
    assert all(f["kwp"] for f in found)


def test_kwp_dtc_clear_and_actuate(car):
    k = SaabKwp(car, Endpoint(target=0x28))
    k.connect()
    codes = k.read_dtcs()
    assert [d.code for d in codes] == ["C1035", "C1040"]
    assert codes[0].active and not codes[1].active
    k.clear_dtcs()
    assert k.read_dtcs() == []
    actions.actuate(k, 0x20, 0x07, b"\x01", 0, out=lambda s: None)
    assert car.io_log == [(0x28, 0x20, 0x07), (0x28, 0x20, 0x00)]


def test_module_registry_user_override(tmp_path):
    uf = tmp_path / "u.json"
    assert not modules.load(uf)["ABS"].known
    modules.save_user("ABS", {"merkis": "0x28", "parametri": {"0x10": {"nosaukums": "Režīms", "tips": "u8",
                       "rakstams": True, "varianti": {"00": "Izslēgts", "01": "Ieslēgts"}}}}, uf)
    m = modules.load(uf)["ABS"]
    assert m.endpoint.target == 0x28 and m.endpoint.resp == 0x258
    p = m.params[0x10]
    assert p.decode(b"\x01") == "Ieslēgts"
    assert p.encode("izslēgts") == b"\x00"


def test_param_scaling():
    p = modules.Param(0x01, "Temp", kind="u8", scale=1, offset=-40, unit="°C")
    assert p.decode(b"\x82") == "90 °C"
    assert p.encode("90") == b"\x82"


def test_tech2_menu_session(car, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    uf = tmp_path / "moduli_lietotajs.json"
    modules.save_user("ABS", {"merkis": "0x28", "aktivizacijas": [
        {"nosaukums": "KP vārsts", "lid": "0x20", "dati": "01", "ilgums": 0}],
        "parametri": {"0x10": {"nosaukums": "Režīms", "tips": "u8", "rakstams": True}}}, uf)
    answers = iter([
        "1",            # Vadības moduļi
        "3",            # ABS (ECM, TCM, ABS)
        "1",            # kļūdu kodi
        "5", "1", "APSTIPRINU",          # aktivizēšana
        "6", "1", "2", "APSTIPRINU",     # iestatījums 0x10 -> 2
        "0", "0", "0",
    ])
    log = []
    Tech2(car, lambda _: next(answers), log.append, uf).run()
    text = "\n".join(log)
    assert "C1035" in text and "AKTĪVS" in text
    assert "Vadība atdota modulim." in text
    assert "Ierakstīts un pārbaudīts" in text
    assert car.modules[0x28]["lids"][0x10] == b"\x02"
    assert list((tmp_path / "rezerves_kopijas").glob("ABS_lid_10_*.json"))


def test_cli_modules_and_mod(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["modules"]) == 0
    assert cli.main(["module-set", "abs", "--target", "0x28"]) == 0
    assert cli.main(["--sim", "mod", "ABS", "dtc"]) == 0
    assert "C1035" in capsys.readouterr().out
    assert cli.main(["--sim", "mod", "ECM", "read", "0x90"]) == 0
    assert SIM_VIN in capsys.readouterr().out


# ---------------- 2.3t Aero ----------------
from saab95 import aero  # noqa: E402


def test_aero_health_check(car):
    res = {f.title: f for f in aero.health_check(obd2.Obd2(car))}
    assert res["Dzesēšanas šķidrums"].level == "OK"
    assert res["Kļūdu kodi"].level == "PROBLĒMA" and "P0171" in res["Kļūdu kodi"].detail


def test_aero_analyze(tmp_path):
    p = tmp_path / "b.csv"
    p.write_text(
        "laiks,rpm,map,baro,iat,timing,coolant,load,throttle,stft,ltft,voltage\n"
        "1,850,35,101,30,12,90,20,0,1,2,14.1\n"
        "2,4200,205,101,48,8,92,95,100,0,2,14.0\n"
        "3,4800,212,101,55,-2,93,98,100,0,2,14.0\n", encoding="utf-8")
    res = {f.title: f for f in aero.analyze_log(p, boost_max=1.05)}
    assert res["Maks. turbo virsspiediens"].detail.startswith("1.11")
    assert res["Maks. turbo virsspiediens"].level == "PROBLĒMA"
    assert res["Apsteidze zem turbo spiediena"].level == "UZMANĪBU"


def test_cli_live_aero_preset(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["--sim", "live", "--preset", "aero", "--count", "2", "--interval", "0", "--csv", "a.csv"]) == 0
    assert "Turbo virsspiediens" in capsys.readouterr().out
    assert cli.main(["analyze", "a.csv"]) == 0
    assert cli.main(["--sim", "aero-check"]) == 0


def _write_log(path, rows):
    path.write_text("laiks,rpm,map,baro,timing,coolant,stft,ltft,degviela\n" +
                    "".join(f"{i},{r},{m},101,{t},90,{s},{lt},x\n" for i, (r, m, t, s, lt) in enumerate(rows)),
                    encoding="utf-8")


def test_lpg_compare(tmp_path):
    petrol, lpg = tmp_path / "b.csv", tmp_path / "g.csv"
    _write_log(petrol, [(2000, 40, 20, 1, 2)] * 6 + [(4000, 190, 10, 0, 2)] * 6)
    _write_log(lpg, [(2000, 40, 20, 2, 2)] * 6 + [(4000, 190, 5, 9, 2)] * 6)
    out = "\n".join(aero.compare_fuels(petrol, lpg))
    assert "par LIESU" in out and "apsteidze uz gāzes -5.0°" in out
    assert out.count("✓") == 1  # vakuuma zona sakrīt


def test_cli_lpg(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["--sim", "live", "--preset", "aero", "--fuel", "lpg", "--count", "1", "--interval", "0", "--csv", "g.csv"]) == 0
    assert (tmp_path / "g.csv").read_text().splitlines()[1].endswith(",lpg")
    assert cli.main(["--sim", "aero-check", "--fuel", "lpg"]) == 0
    assert "Gāze: aizdedze" in capsys.readouterr().out
    assert cli.main(["lpg-compare", "g.csv", "g.csv"]) == 0
