"""saab95 – Saab 9-5 (2007) diagnostikas un uzstādījumu rīks."""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from . import __version__, actions, aero, discovery, modules, obd2, trionic7
from .kwp import SaabKwp
from .transport import Elm327Transport, PythonCanTransport, Transport

CONFIRM_WORD = actions.CONFIRM_WORD


def open_transport(args) -> Transport:
    if args.sim:
        from .simulator import SimulatedCar

        tr: Transport = SimulatedCar()
    elif args.elm:
        tr = Elm327Transport(args.elm, baudrate=args.elm_baud)
    elif args.can:
        tr = PythonCanTransport(args.can, args.channel, bitrate=args.bitrate)
    else:
        sys.exit("Norādiet adapteri: --elm PORTS, --can INTERFEISS --channel KANĀLS vai --sim")
    tr.debug = args.debug
    return tr


def confirm(args, text: str) -> bool:
    print(f"\n⚠  {text}")
    if args.yes:
        return True
    ans = input(f"Lai turpinātu, ierakstiet {CONFIRM_WORD}: ").strip()
    return ans == CONFIRM_WORD


def parse_lid(s: str) -> int:
    v = int(s, 0)
    if not 0 <= v <= 0xFF:
        raise argparse.ArgumentTypeError("identifikatoram jābūt 0x00..0xFF")
    return v


def parse_hex(s: str) -> bytes:
    if s.startswith("ascii:"):
        return s[6:].encode("ascii")
    return bytes.fromhex(s.replace(" ", "").replace(":", ""))


# ---------------- OBD-II ----------------
def cmd_info(args, tr):
    o = obd2.Obd2(tr)
    print(f"VIN:              {o.read_vin()}")
    sup = o.supported_pids()
    names = [p.name for p in obd2.PIDS.values() if p.pid in sup]
    print(f"Atbalstītie PID:  {len(sup)}  (rīkā pieejami: {', '.join(names)})")
    print(f"Kļūdu kodi:       {', '.join(o.read_dtcs()) or 'nav'}")


def cmd_live(args, tr):
    o = obd2.Obd2(tr)
    names = args.pids.split(",") if args.pids else (list(aero.PRESET) if args.preset == "aero" else None)
    if names is None:
        sup = o.supported_pids()
        names = [p.name for p in obd2.PIDS.values() if p.pid in sup]
    for n in names:
        if n not in obd2.PIDS:
            sys.exit(f"Nezināms PID '{n}'. Pieejami: {', '.join(obd2.PIDS)}")
    show_boost = "map" in names and "baro" in names
    writer = None
    fh = None
    if args.csv:
        fh = open(args.csv, "w", newline="", encoding="utf-8")
        writer = csv.writer(fh)
        writer.writerow(["laiks", *names, *(["boost"] if show_boost else []), "degviela"])
    i = 0
    try:
        while args.count == 0 or i < args.count:
            row = {}
            for n in names:
                try:
                    row[n] = o.read_pid(n)
                except Exception:  # noqa: BLE001 - viens PID nedrīkst apturēt žurnālu
                    row[n] = float("nan")
            stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"\n[{stamp}]")
            for n in names:
                p = obd2.PIDS[n]
                print(f"  {p.title:<34} {row[n]:>9.1f} {p.unit}")
            extra = []
            if show_boost:
                b = aero.boost_bar(row["map"], row["baro"])
                print(f"  {'Turbo virsspiediens':<34} {b:>9.2f} bar")
                extra = [f"{b:.3f}"]
            if writer:
                writer.writerow([stamp, *(f"{row[n]:.2f}" for n in names), *extra, args.fuel])
                fh.flush()
            i += 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        if fh:
            fh.close()


def cmd_aero_check(args, tr):
    print("Saab 9-5 2.3t Aero veselības pārbaude (dzinējs sasilis, tukšgaitā)\n")
    if args.fuel == "lpg":
        print("Degviela: GĀZE – korekcijas vērtējiet salīdzinājumā ar benzīnu.\n")
    for f in aero.health_check(obd2.Obd2(tr)):
        print(f)
    if args.fuel == "lpg":
        for f in aero.LPG_ADVICE:
            print(f)


def cmd_analyze(args, tr):
    print(f"Brauciena analīze: {args.file}\n")
    for f in aero.analyze_log(args.file, args.boost_max):
        print(f)


def cmd_lpg_compare(args, tr):
    print(f"Benzīns: {args.petrol}\nGāze:    {args.lpg}\n")
    for line in aero.compare_fuels(args.petrol, args.lpg, tolerance=args.tolerance):
        print(line)


def cmd_dtc(args, tr):
    o = obd2.Obd2(tr)
    for title, pending in (("Saglabātie", False), ("Gaidošie", True)):
        try:
            codes = o.read_dtcs(pending)
        except obd2.ObdError:
            continue
        print(f"{title} kļūdu kodi:")
        for c in codes:
            print(f"  {c}  {obd2.DTC_HINTS.get(c, '')}")
        if not codes:
            print("  nav")
    if args.clear:
        if confirm(args, "Kļūdu kodu dzēšana atiestata arī OBD gatavības testus (readiness)."):
            o.clear_dtcs()
            print("Kļūdu kodi izdzēsti.")
        else:
            print("Atcelts.")


# ---------------- Trionic 7 ----------------
def _t7(tr) -> trionic7.Trionic7:
    t = trionic7.Trionic7(tr)
    t.connect()
    return t


def cmd_t7_info(args, tr):
    t = _t7(tr)
    for k, v in t.identify().items():
        print(f"{k:<20} {v}")


def cmd_t7_scan(args, tr):
    t = _t7(tr)
    found = {}
    print("Skenē lokālos identifikatorus 0x00..0xFF (tikai lasīšana)...")
    for lid in range(0x100):
        if lid == 0xF0:
            continue
        try:
            raw = t.read_local_id(lid)
        except trionic7.KwpError:
            continue
        found[f"0x{lid:02X}"] = {"hex": raw.hex(" ").upper(), "teksts": trionic7._printable(raw)}
        print(f"  0x{lid:02X}: {trionic7._printable(raw)}")
    out = Path(args.out)
    out.write_text(json.dumps(found, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Atrasti {len(found)} identifikatori, saglabāts: {out}")


def cmd_t7_read(args, tr):
    t = _t7(tr)
    raw = t.read_local_id(args.lid)
    print(f"0x{args.lid:02X} hex:    {raw.hex(' ').upper()}")
    print(f"0x{args.lid:02X} teksts: {trionic7._printable(raw)}")


def _write(args, kwp: SaabKwp, module: str, lid: int, new: bytes) -> None:
    res = actions.write_with_backup(kwp, module, lid, new, args.apply, lambda t: confirm(args, t))
    if res == "sauss":
        print("Pievienojiet --apply, lai ierakstītu.")
    elif res == "kluda":
        sys.exit(2)


def cmd_t7_write(args, tr):
    _write(args, _t7(tr), "ECM", args.lid, parse_hex(args.value))


def cmd_t7_restore(args, tr):
    data = json.loads(Path(args.backup).read_text(encoding="utf-8"))
    key = data.get("modulis", "ECM")
    kwp = _module(tr, key)
    _write(args, kwp, key, int(data["lid"]), bytes.fromhex(data["hex"]))


# ---------------- visi moduļi ----------------
def _module(tr, key: str) -> SaabKwp:
    mods = modules.load()
    if key not in mods:
        sys.exit(f"Nezināms modulis '{key}'. Pieejami: {', '.join(mods)}")
    m = mods[key]
    if not m.known:
        sys.exit(f"{key} adrese nav zināma. Palaidiet 'saab95 discover' un 'saab95 module-set {key} --target 0x..'.")
    kwp = SaabKwp(tr, m.endpoint)
    kwp.connect()
    return kwp


def cmd_modules(args, tr):
    for m in modules.load().values():
        addr = f"0x{m.endpoint.target:02X}" if m.known else "  ?  "
        print(f"{m.key:<6} {addr}  {m.bus:<18} {m.name:<42} {m.status}")


def cmd_module_set(args, tr):
    patch = {"merkis": args.target, "statuss": "iestatīts manuāli"}
    for k in ("init_tx", "init_rx", "req", "resp", "ack"):
        if getattr(args, k):
            patch[k] = getattr(args, k)
    modules.save_user(args.key.upper(), patch)
    print(f"Saglabāts {modules.USER_FILE}")


def cmd_mod(args, tr):
    key = args.key.upper()
    m = modules.load()[key] if key in modules.load() else None
    kwp = _module(tr, key)
    act = args.action
    if act == "dtc":
        codes = kwp.read_dtcs()
        for d in codes:
            print(f"  {d.code}  {'AKTĪVS' if d.active else 'vēsturisks'}  st=0x{d.status:02X}  {obd2.DTC_HINTS.get(d.code, '')}")
        if not codes:
            print("Kļūdu kodu nav.")
    elif act == "clear":
        if confirm(args, f"Dzēst visus {key} kļūdu kodus?"):
            kwp.clear_dtcs()
            print("Izdzēsts.")
    elif act == "read":
        lid = parse_lid(args.arg[0])
        raw = kwp.read_local_id(lid)
        p = m.params.get(lid)
        print(f"0x{lid:02X}: {p.decode(raw) if p else trionic7.printable(raw)}  [{raw.hex(' ').upper()}]")
    elif act == "write":
        lid = parse_lid(args.arg[0])
        p = m.params.get(lid)
        new = p.encode(args.arg[1]) if p and not args.arg[1].startswith(("ascii:", "hex:")) else parse_hex(args.arg[1].removeprefix("hex:"))
        _write(args, kwp, key, lid, new)
    elif act == "data":
        for p in m.params.values():
            print(f"  {p.name:<36} {p.decode(kwp.read_local_id(p.lid))}")
    elif act == "scan":
        found = actions.scan_lids(kwp)
        out = Path(f"{key}_skenesana_{datetime.now():%Y-%m-%d}.json")
        out.write_text(json.dumps({f"0x{k:02X}": v.hex(" ").upper() for k, v in found.items()}, indent=2), encoding="utf-8")
        print(f"Saglabāts {out}")
    elif act == "actuate":
        name = " ".join(args.arg)
        a = next((x for x in m.actuators if x.name.lower() == name.lower()), None)
        if a is None:
            sys.exit(f"Nav tāda testa. Pieejami: {', '.join(x.name for x in m.actuators) or 'nav definēti'}")
        if confirm(args, f"Aktivizēt '{a.name}' uz {a.duration:g} s?"):
            actions.actuate(kwp, a.lid, a.param, a.data, a.duration)


def cmd_discover(args, tr):
    print("Meklē moduļus (dzinējs IZSLĒGTS, aizdedze ON)...")
    found = discovery.discover(tr, range(args.first, args.last + 1),
                               progress=lambda t: print(f"\r  0x{t:02X}", end="", flush=True))
    print()
    for f in found:
        print(f"  mērķis {f['merkis']}  KWP={'jā' if f['kwp'] else 'nē'}  {f['atbildes']}")
    out = Path(f"atrastie_moduli_{datetime.now():%Y-%m-%d}.json")
    out.write_text(json.dumps(found, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Atrasti {len(found)}. Saglabāts {out}. Piešķiriet: saab95 module-set <MODULIS> --target 0x..")


def cmd_monitor(args, tr):
    rows = discovery.summarize(discovery.monitor(tr, args.seconds), args.seconds)
    for r in rows:
        print(f"  {r['id']}  {r['kadri']:>5}  {r['hz']:>6} Hz  {r['pedejie_dati']}")
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=2), encoding="utf-8")


def cmd_tech2(args, tr):
    from .tech2 import Tech2

    Tech2(tr).run()


def cmd_t7_dump(args, tr):
    t = _t7(tr)
    t.security_access()
    start, length, chunk = args.start, args.length, 0x80
    out = bytearray()
    t0 = time.monotonic()
    for addr in range(start, start + length, chunk):
        n = min(chunk, start + length - addr)
        out += t.read_memory(addr, n)
        done = len(out) / length
        print(f"\r  {addr + n:06X}  {done:6.1%}  {time.monotonic() - t0:5.0f}s", end="", flush=True)
    Path(args.out).write_bytes(out)
    print(f"\nSaglabāts {len(out)} baiti: {args.out}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="saab95", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    a = p.add_argument_group("adapteris")
    a.add_argument("--elm", metavar="PORTS", help="ELM327 seriālais ports, piem. COM5 vai /dev/ttyUSB0")
    a.add_argument("--elm-baud", type=int, default=38400)
    a.add_argument("--can", metavar="INTERFEISS", help="python-can interfeiss: slcan, kvaser, pcan, socketcan...")
    a.add_argument("--channel", default="can0", help="python-can kanāls (piem. COM6, PCAN_USBBUS1, can0)")
    a.add_argument("--bitrate", type=int, default=500_000)
    a.add_argument("--sim", action="store_true", help="virtuāla mašīna testēšanai")
    p.add_argument("--debug", action="store_true", help="rādīt visus CAN kadrus")
    p.add_argument("-y", "--yes", action="store_true", help="neprasīt apstiprinājumu")

    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tech2", help="interaktīva Tech2 stila izvēlne").set_defaults(fn=cmd_tech2)
    sub.add_parser("modules", help="moduļu saraksts").set_defaults(fn=cmd_modules)

    s = sub.add_parser("mod", help="darbības ar moduli: dtc, clear, data, read, write, scan, actuate")
    s.add_argument("key", help="ECM, TCM, ABS, SRS, MIU, SID, ACC, DICE, TWICE")
    s.add_argument("action", choices=["dtc", "clear", "data", "read", "write", "scan", "actuate"])
    s.add_argument("arg", nargs="*", help="read LID | write LID VĒRTĪBA | actuate NOSAUKUMS")
    s.add_argument("--apply", action="store_true", help="write: tiešām ierakstīt")
    s.set_defaults(fn=cmd_mod)

    s = sub.add_parser("discover", help="meklēt moduļus kopnē")
    s.add_argument("--first", type=lambda x: int(x, 0), default=0x01)
    s.add_argument("--last", type=lambda x: int(x, 0), default=0xFF)
    s.set_defaults(fn=cmd_discover)

    s = sub.add_parser("monitor", help="pasīvi klausīties CAN kopni")
    s.add_argument("--seconds", type=float, default=5.0)
    s.add_argument("--out")
    s.set_defaults(fn=cmd_monitor)

    s = sub.add_parser("module-set", help="piešķirt modulim atrasto adresi")
    s.add_argument("key")
    s.add_argument("--target", required=True)
    for k in ("init_tx", "init_rx", "req", "resp", "ack"):
        s.add_argument(f"--{k.replace('_', '-')}", dest=k)
    s.set_defaults(fn=cmd_module_set)

    sub.add_parser("info", help="VIN, atbalstītie PID, kļūdu kodi").set_defaults(fn=cmd_info)

    s = sub.add_parser("live", help="reāllaika dati")
    s.add_argument("--pids", help=f"komatatdalīti: {','.join(obd2.PIDS)}")
    s.add_argument("--interval", type=float, default=0.5)
    s.add_argument("--count", type=int, default=0, help="0 = līdz Ctrl+C")
    s.add_argument("--csv", help="saglabāt žurnālu CSV failā")
    s.add_argument("--preset", choices=["aero"], help="aero = turbo dzinēja parametri + turbo virsspiediens")
    s.add_argument("--fuel", choices=["benzins", "lpg"], default="benzins", help="ar kuru degvielu brauc (atzīme žurnālā)")
    s.set_defaults(fn=cmd_live)

    s = sub.add_parser("aero-check", help="2.3t Aero veselības pārbaude tukšgaitā")
    s.add_argument("--fuel", choices=["benzins", "lpg"], default="benzins")
    s.set_defaults(fn=cmd_aero_check)

    s = sub.add_parser("lpg-compare", help="salīdzināt benzīna un gāzes braucienu (gāzes kalibrācijas pārbaude)")
    s.add_argument("petrol", help="CSV ar benzīnu")
    s.add_argument("lpg", help="CSV ar gāzi")
    s.add_argument("--tolerance", type=float, default=5.0, help="pieļaujamā starpība, %% (noklusējums 5)")
    s.set_defaults(fn=cmd_lpg_compare)
    s = sub.add_parser("analyze", help="analizēt brauciena CSV žurnālu (bez adaptera)")
    s.add_argument("file")
    s.add_argument("--boost-max", type=float, help="brīdināt, ja virsspiediens pārsniedz (bar)")
    s.set_defaults(fn=cmd_analyze)

    s = sub.add_parser("dtc", help="kļūdu kodi")
    s.add_argument("--clear", action="store_true", help="dzēst kļūdu kodus")
    s.set_defaults(fn=cmd_dtc)

    sub.add_parser("t7-info", help="Trionic 7 identifikācija").set_defaults(fn=cmd_t7_info)
    s = sub.add_parser("t7-scan", help="nolasīt visus T7 lokālos identifikatorus")
    s.add_argument("--out", default=f"t7_skenesana_{datetime.now():%Y-%m-%d}.json")
    s.set_defaults(fn=cmd_t7_scan)

    s = sub.add_parser("t7-read", help="nolasīt vienu identifikatoru")
    s.add_argument("lid", type=parse_lid)
    s.set_defaults(fn=cmd_t7_read)

    s = sub.add_parser("t7-write", help="mainīt identifikatora vērtību (ar rezerves kopiju)")
    s.add_argument("lid", type=parse_lid)
    s.add_argument("value", help="hex baiti ('01 02 FF') vai 'ascii:TEKSTS'")
    s.add_argument("--apply", action="store_true", help="tiešām ierakstīt (citādi sausais režīms)")
    s.set_defaults(fn=cmd_t7_write)

    s = sub.add_parser("t7-restore", help="atjaunot vērtību no rezerves kopijas")
    s.add_argument("backup")
    s.add_argument("--apply", action="store_true")
    s.set_defaults(fn=cmd_t7_restore)

    s = sub.add_parser("t7-dump", help="nolasīt ECU atmiņu (programmatūras kopija T7Suite)")
    s.add_argument("out")
    s.add_argument("--start", type=lambda x: int(x, 0), default=0)
    s.add_argument("--length", type=lambda x: int(x, 0), default=0x80000)
    s.set_defaults(fn=cmd_t7_dump)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd in ("modules", "module-set", "analyze", "lpg-compare"):
        args.fn(args, None)
        return 0
    tr = open_transport(args)
    try:
        args.fn(args, tr)
    except Exception as e:  # noqa: BLE001
        if args.debug:
            raise
        print(f"Kļūda: {e}", file=sys.stderr)
        return 1
    finally:
        tr.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
