# saab95: Saab 9-5 (2007) diagnostika un uzstādījumi

Komandrindas rīks Saab 9-5 (MY2006–2010) vadības blokiem:

| Līmenis | Ko dara | Statuss |
|---|---|---|
| **OBD-II / EOBD** | VIN, reāllaika dati, kļūdu kodi, kodu dzēšana | standarta protokols, drošs |
| **Trionic 7 (KWP2000)** | ECU identifikācija, identifikatoru skenēšana, lasīšana/rakstīšana, atmiņas kopija | eksperimentāls, jāpārbauda uz mašīnas |

Trionic 7 ir benzīna dzinēju (2.0t / 2.3t / Aero, B205/B235) ECU. Dīzeļa versijām (TiD) ir cits ECU, un uz tām darbojas tikai OBD-II daļa.

## 1. Aparatūra

| Adapteris | OBD-II | Trionic 7 | Piezīmes |
|---|---|---|---|
| **OBDLink SX / EX** (USB) | ✓ | ✓ | ieteicams, stabils ELM327 klons |
| Lēts ELM327 v1.5 (Bluetooth/USB) | ✓ | ± | kloni bieži nepilnīgi izpilda `ATCAF0`/`ATR0` |
| **Lawicel CANUSB** / CANable (slcan) | ✓ | ✓ | īsts CAN adapteris, ātrāks |
| Kvaser, PEAK PCAN-USB | ✓ | ✓ | profesionāli |

P-Bus (dzinēja CAN, 500 kbit/s) ir OBD ligzdā uz **6. (CAN-H) un 14. (CAN-L)** kontakta.

## 2. Uzstādīšana

```bash
pip install -e .            # ELM327
pip install -e .[can]       # + python-can (CANUSB, Kvaser, PCAN)
```

## 3. Lietošana

Adapteri norāda pirms komandas:

```bash
saab95 --elm COM5 info                                   # Windows, ELM327
saab95 --elm /dev/ttyUSB0 info                           # Linux/Mac
saab95 --can slcan --channel COM6 info                   # Lawicel CANUSB
saab95 --can pcan --channel PCAN_USBBUS1 info
saab95 --sim info                                        # virtuāla mašīna, bez adaptera
```

### OBD-II

```bash
saab95 --elm COM5 info                                   # VIN, PID saraksts, kļūdas
saab95 --elm COM5 live                                   # visi atbalstītie parametri
saab95 --elm COM5 live --pids rpm,map,iat,timing --csv brauciens.csv
saab95 --elm COM5 dtc                                    # kļūdu kodi
saab95 --elm COM5 dtc --clear                            # dzēst (prasa apstiprinājumu)
```

Pieejamie parametri: `load, coolant, stft, ltft, map, rpm, speed, timing, iat, maf, throttle, runtime, mil_dist, fuel, baro, voltage, ambient`.

### Trionic 7

```bash
saab95 --elm COM5 t7-info                  # identifikācija
saab95 --elm COM5 t7-scan                  # nolasa VISUS identifikatorus 0x00–0xFF → JSON
saab95 --elm COM5 t7-read 0x90             # viens identifikators
saab95 --elm COM5 t7-write 0x90 "ascii:YS3E..."            # sausais režīms: tikai rāda izmaiņu
saab95 --elm COM5 t7-write 0x90 "ascii:YS3E..." --apply    # ieraksta
saab95 --elm COM5 t7-restore rezerves_kopijas/t7_lid_90_....json --apply
saab95 --can slcan --channel COM6 t7-dump mans_ecu.bin     # 512 KB programmatūras kopija
```

**Ieteicamā secība pirmajā reizē:** `info` → `t7-info` → `t7-scan` → `t7-dump`. Pēc tam ir rezerves kopijas un pilns saraksts, ko ECU atļauj nolasīt.

## 4. Drošības mehānismi

- Rakstīšana pēc noklusējuma ir **sausais režīms**: tā tikai parāda pašreizējo un jauno vērtību.
- Ar `--apply` rīks vispirms saglabā veco vērtību mapē `rezerves_kopijas/`, tad prasa ierakstīt `APSTIPRINU`, ieraksta un pārbauda, nolasot vērtību atpakaļ.
- Pirms rakstīšanas: aizdedzei jābūt ON, dzinējam izslēgtam, akumulatoram uzlādētam (vēlams lādētājs).
- Ar `--debug` var redzēt katru CAN kadru.

## 5. Ko rīks NEDARA un kāpēc

- **Netaisa T7 programmatūras pārrakstīšanu (flash/tūnings).** Ja kļūda notiek šī procesa vidū, ECU var palikt nedarbspējīgs. Tūningam lietojiet pārbaudītos atvērtā koda rīkus: **T7Suite** (karšu rediģēšana `.bin` failā, ko izveido `t7-dump`) un **TrionicCANFlasher** (ierakstīšana).
- **Nemaina komforta uzstādījumus** (SID, CIM, durvju slēgšana, gaismas). Tie ir citos moduļos uz I-Bus (47,6 kbit/s), un tos maina ar Tech2. Daļu var iestatīt SID izvēlnē bez rīkiem.
- **Neizslēdz emisiju kontroli** (katalizators, lambda, EGR). Ceļu satiksmē tas ir nelikumīgi, un tehniskajā apskatē to konstatēs.

## 6. Ja nestrādā

- `Nav atbildes no 7E8`: pārbaudiet, vai aizdedze ir ON. Lētajam ELM327 izmēģiniet `--elm-baud 115200` vai `9600`.
- `Trionic 7 neatbild`: ECU var nebūt T7 (dīzelis), vai adapteris neatbalsta neapstrādātu CAN režīmu (`ATCAF0`).
- `piekļuve liegta`: šim identifikatoram vajadzīga drošības atslēga; `t7-write` to iegūst automātiski.

## Izstrāde

```bash
pip install -e .[dev,can]
pytest
```

Simulators (`saab95/simulator.py`) atdarina OBD-II ECU un Trionic 7, tāpēc visu loģiku var testēt bez mašīnas.

Struktūra: `transport.py` (CAN adapteri), `isotp.py`, `obd2.py`, `trionic7.py`, `simulator.py`, `cli.py`.
