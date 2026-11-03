# saab95: Saab 9-5 (2007) diagnostika un uzstādījumi

Tech2 stila diagnostikas rīks Saab 9-5 vadības moduļiem.

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

## 4. Tech2 režīms (visi moduļi)

```bash
saab95 --elm COM5 tech2          # interaktīva izvēlne kā Tech2
```

Izvēlne: **Vadības moduļi** → modulis → Kļūdu kodi / Dzēst / Datu saraksts / Identifikācija / Aktivizēšanas testi / Iestatījumi / Skenēt identifikatorus. Ir arī OBD-II, moduļu meklēšana un CAN monitors.

### Tech2 funkciju salīdzinājums

| Tech2 funkcija | saab95 | Piezīme |
|---|---|---|
| Kļūdu kodi visiem moduļiem (lasīt/dzēst) | ✓ | KWP 0x18 / 0x14 |
| Datu saraksts | ✓ | parametri jādefinē (skat. zemāk) |
| Identifikācija | ✓ | KWP 0x1A, 0x21 |
| Aktivizēšanas testi | ✓ | KWP 0x30, vadība vienmēr tiek atdota modulim |
| Iestatījumi / konfigurācija | ✓ | rakstīšana ar rezerves kopiju |
| ECM drošības piekļuve | ✓ | tikai Trionic 7 (publisks algoritms) |
| Citu moduļu drošības piekļuve | – | Saab algoritmi nav publiski |
| Programmatūras ielāde (SPS) | – | vajadzīgi GM/Saab TIS2Web faili |
| Atslēgu / imobilaizera programmēšana | – | apzināti nav iekļauts: vajadzīgs Saab drošības kods |
| Moduļu pievienošana/noņemšana | – | atkarīgs no SPS |

### Moduļu atrašana (vienreizējs darbs)

Publiski ir zināma tikai Trionic 7 (ECM) adrese. Pārējo moduļu adreses rīks atrod pats:

```bash
saab95 --can slcan --channel COM6 monitor --seconds 5     # kas raida kopnē
saab95 --can slcan --channel COM6 discover                # P-Bus 500 kbit/s
saab95 --can slcan --channel COM6 --bitrate 47619 discover  # I-Bus 47,6 kbit/s
saab95 module-set ABS --target 0x..                       # piešķir atrasto adresi
saab95 modules                                            # pārskats
```

Tech2 izvēlnē "Meklēt moduļus kopnē" to dara interaktīvi. Pēc tam:

```bash
saab95 --elm COM5 mod ABS dtc               # kļūdu kodi
saab95 --elm COM5 mod ABS clear
saab95 --elm COM5 mod ABS scan              # atrod nolasāmos parametrus
saab95 --elm COM5 mod ABS data              # definēto parametru vērtības
saab95 --elm COM5 mod ABS read 0x10
saab95 --elm COM5 mod ABS write 0x10 Ieslēgts --apply
saab95 --elm COM5 mod ABS actuate "KP vārsts"
```

### Parametru, testu un iestatījumu definēšana

Viss glabājas `moduli_lietotajs.json` darba mapē. Tech2 izvēlnē "Skenēt identifikatorus" nosaukumus var ievadīt uzreiz. Piemērs:

```json
{
  "ABS": {
    "merkis": "0x28",
    "parametri": {
      "0x10": {"nosaukums": "Režīms", "tips": "u8", "rakstams": true,
               "varianti": {"00": "Izslēgts", "01": "Ieslēgts"}},
      "0x12": {"nosaukums": "Temperatūra", "tips": "u8", "nobide": -40, "vieniba": "°C"}
    },
    "aktivizacijas": [
      {"nosaukums": "KP vārsts", "lid": "0x20", "parametrs": "0x07", "dati": "01", "ilgums": 3,
       "piezime": "Pacelt riteni un griezt ar roku"}
    ]
  }
}
```

Tipi: `ascii`, `hex`, `u8`, `s8`, `u16`, `s16`, `u32`. Vērtība = neapstrādātā × `merogs` + `nobide`.

**Svarīgi:** `0x28` šeit ir tikai piemērs (simulatora fiktīvā adrese). Īstās adreses jāatrod uz mašīnas.

## 5. Drošības mehānismi

- Rakstīšana pēc noklusējuma ir **sausais režīms**: tā tikai parāda pašreizējo un jauno vērtību.
- Ar `--apply` rīks vispirms saglabā veco vērtību mapē `rezerves_kopijas/`, tad prasa ierakstīt `APSTIPRINU`, ieraksta un pārbauda, nolasot vērtību atpakaļ.
- Pirms rakstīšanas: aizdedzei jābūt ON, dzinējam izslēgtam, akumulatoram uzlādētam (vēlams lādētājs).
- Ar `--debug` var redzēt katru CAN kadru.

## 6. Ko rīks NEDARA un kāpēc

- **Netaisa T7 programmatūras pārrakstīšanu (flash/tūnings).** Ja kļūda notiek šī procesa vidū, ECU var palikt nedarbspējīgs. Tūningam lietojiet pārbaudītos atvērtā koda rīkus: **T7Suite** (karšu rediģēšana `.bin` failā, ko izveido `t7-dump`) un **TrionicCANFlasher** (ierakstīšana).
- **Neprogrammē atslēgas un imobilaizeru.** Tam Tech2 vajadzīgs Saab drošības kods no servisa sistēmas.
- **Neizslēdz emisiju kontroli** (katalizators, lambda, EGR). Ceļu satiksmē tas ir nelikumīgi, un tehniskajā apskatē to konstatēs.

## 7. Ja nestrādā

- `Nav atbildes no 7E8`: pārbaudiet, vai aizdedze ir ON. Lētajam ELM327 izmēģiniet `--elm-baud 115200` vai `9600`.
- `Trionic 7 neatbild`: ECU var nebūt T7 (dīzelis), vai adapteris neatbalsta neapstrādātu CAN režīmu (`ATCAF0`).
- `piekļuve liegta`: šim identifikatoram vajadzīga drošības atslēga; `t7-write` to iegūst automātiski.

## Izstrāde

```bash
pip install -e .[dev,can]
pytest
```

Simulators (`saab95/simulator.py`) atdarina OBD-II ECU un Trionic 7, tāpēc visu loģiku var testēt bez mašīnas.

Struktūra: `transport.py` (CAN adapteri), `isotp.py`, `obd2.py`, `kwp.py` (visi moduļi), `trionic7.py`, `modules.py` + `moduli.json` (reģistrs), `discovery.py`, `actions.py` (droša rakstīšana, aktivizēšana), `tech2.py` (izvēlne), `simulator.py`, `cli.py`.
