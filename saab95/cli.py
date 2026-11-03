"""saab95 – Saab 9-5 (2007) diagnostikas un uzstādījumu rīks."""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from . import __version__, obd2, trionic7
from .transport import Elm327Transport, PythonCanTransport, Transport

BACKUP_DIR = Path("rezerves_kopijas")
CONFIRM_WORD = "APSTIPRINU"


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
    names = args.pids.split(",") if args.pids else None
    if names is None:
        sup = o.supported_pids()
        names = [p.name for p in obd2.PIDS.values() if p.pid in sup]
    for n in names:
        if n not in obd2.PIDS:
            sys.exit(f"Nezināms PID '{n}'. Pieejami: {', '.join(obd2.PIDS)}")
    writer = None
    fh = None
    if args.csv:
        fh = open(args.csv, "w", newline="", encoding="utf-8")
        writer = csv.writer(fh)
        writer.writerow(["laiks", *names])
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
            if writer:
                writer.writerow([stamp, *(f"{row[n]:.2f}" for n in names)])
                fh.flush()
            i += 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        if fh:
            fh.close()


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


def _backup(lid: int, raw: bytes) -> Path:
    BACKUP_DIR.mkdir(exist_ok=True)
    p = BACKUP_DIR / f"t7_lid_{lid:02X}_{datetime.now():%Y-%m-%d_%H%M%S}.json"
    p.write_text(
        json.dumps({"lid": lid, "hex": raw.hex(), "laiks": datetime.now().isoformat()}, indent=2),
        encoding="utf-8",
    )
    return p


def _write(args, t: trionic7.Trionic7, lid: int, new: bytes) -> None:
    old = t.read_local_id(lid)
    print(f"Identifikators 0x{lid:02X}")
    print(f"  pašreiz: {old.hex(' ').upper()}  ({trionic7._printable(old)})")
    print(f"  jauns:   {new.hex(' ').upper()}  ({trionic7._printable(new)})")
    if old == new:
        print("Vērtība jau ir tāda pati – nekas netiek mainīts.")
        return
    if len(old) != len(new):
        print(f"  ! Garums atšķiras ({len(old)} -> {len(new)} baiti).")
    if not args.apply:
        print("\nSausais režīms – nekas nav ierakstīts. Pievienojiet --apply, lai ierakstītu.")
        return
    bpath = _backup(lid, old)
    print(f"Rezerves kopija: {bpath}")
    if not confirm(args, "Ierakstīšana ECU. Aizdedze ON, dzinējs IZSLĒGTS, akumulators uzlādēts."):
        print("Atcelts.")
        return
    t.write_local_id(lid, new)
    check = t.read_local_id(lid)
    if check == new:
        print("✓ Ierakstīts un pārbaudīts.")
    else:
        print(f"✗ Pārbaude neizdevās! Nolasīts: {check.hex(' ')}. Atjaunot: saab95 t7-restore {bpath}")
        sys.exit(2)


def cmd_t7_write(args, tr):
    _write(args, _t7(tr), args.lid, parse_hex(args.value))


def cmd_t7_restore(args, tr):
    data = json.loads(Path(args.backup).read_text(encoding="utf-8"))
    _write(args, _t7(tr), int(data["lid"]), bytes.fromhex(data["hex"]))


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
    sub.add_parser("info", help="VIN, atbalstītie PID, kļūdu kodi").set_defaults(fn=cmd_info)

    s = sub.add_parser("live", help="reāllaika dati")
    s.add_argument("--pids", help=f"komatatdalīti: {','.join(obd2.PIDS)}")
    s.add_argument("--interval", type=float, default=0.5)
    s.add_argument("--count", type=int, default=0, help="0 = līdz Ctrl+C")
    s.add_argument("--csv", help="saglabāt žurnālu CSV failā")
    s.set_defaults(fn=cmd_live)

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
    tr = open_transport(args)
    try:
        args.fn(args, tr)
    except (obd2.ObdError, trionic7.KwpError, Exception) as e:  # noqa: BLE001
        if args.debug:
            raise
        print(f"Kļūda: {e}", file=sys.stderr)
        return 1
    finally:
        tr.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
