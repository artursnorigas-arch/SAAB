# Tech2 maināmie uzstādījumi: Saab 9-5 (MY2007)

Avots: Saab servisa dokumentācija (WIS), 9-5 (9600), 2007. gads, Tech2 izvēlnes "Adjustment" un "Programming". Nolasīts 2026-11-15.

Šis dokuments ir ģenerēts no `saab95/moduli.json` (`tech2_iestatijumi`). To pašu sarakstu rāda komanda `saab95 settings`.

**Statuss:** tas ir katalogs, nevis darbojoša funkcija. Rīks šos uzstādījumus mainīt vēl nevar, jo moduļu adreses un uzstādījumu identifikatori nav atrasti uz auto. Visi šie moduļi ir uz komforta kopnes (I-Bus, 47,6 kbit/s), ko ELM327 nesasniedz.

Nosaukumi un vērtības ir atstāti angliski, kā tos rāda Tech2.

## SID: informācijas displejs

WIS: <https://saabwisonline.com/9-5-9600/2007/3-electrical-system/saab-information-display-sid/fault-diagnosis-general>

| Izvēlne | Uzstādījums | Vērtības | Piezīme |
|---|---|---|---|
| Programming | Speed Warning ME | Off / On | Signāls virs 120 km/h; Tuvo Austrumu tirgus prasība. |
| Programming | Service Indicator Message | Service Program 1 / Service Program 2 / Service Program 3, 5 / Service Program 4 (US/CA) / Service Program 6:1 / Service Program 6:2 / Service Program 7 | Pēc kuras servisa programmas parādās 'Time for service'. |
| Programming | Parking Heater Activation | Disabled / Activation By Timer / Activation By Outside Temperature / Activation By Timer And Outside Temp | Tikai ar uzstādītu stāvapsildi. |
| Programming | Parking Heater Type | Electrical Powered / Fuel Powered | Tikai ar uzstādītu stāvapsildi. |
| Programming | Extended Belt Reminder | Yes / No | Jostu atgādinājums, kas pastiprinās ar ātrumu. Eiropā noklusējums Yes. Ja No, tas pats jāiestata TWICE. |
| Adjustment | Recall Service Message | – | Dzēš 'Time for service'. Bez rīka: turēt CLEAR 8 sekundes. |
| Adjustment | Outdoor Temperature | -5 °C … +5 °C | Āra temperatūras rādījuma korekcija. |

## TWICE: signalizācija un centrālā atslēga

WIS: <https://saabwisonline.com/9-5-9600/2007/3-electrical-system/twice/fault-diagnosis-general>

| Izvēlne | Uzstādījums | Vērtības | Piezīme |
|---|---|---|---|
| Adjustment | Anti Theft Installation | Without alarm / Alarm - glass break sensor / Alarm - glass break, tilt sensors | Tikai mainot signalizācijas aparatūru. |
| Adjustment | Soundlevel at arm/disarm | Low / High | Neietekmē skaļumu trauksmes laikā. |
| Adjustment | Number of beeps at arming | 0–7 | ES un GB tirgū pēc likuma 0. |
| Adjustment | Number of beeps at disarming | 0–7 | ES un GB tirgū pēc likuma 0. |
| Adjustment | Number of beeps when opening trunk | 0–7 | ES un GB tirgū pēc likuma 0. |
| Adjustment | Disarming at low battery voltage | No / Yes | Ja Yes, signalizācija izslēdzas zem 7 V. |
| Adjustment | Sound Activation Time | 0–520 s | Sirēnas darbības laiks trauksmē. |
| Adjustment | Flashers Activation Time | 0–520 s | Pagriezienu rādītāju mirgošanas laiks trauksmē. |
| Adjustment | Self Arming | No / Yes | Automātiskā signalizācijas ieslēgšanās. |
| Adjustment | Selfarming Time | 0–2040 s | Laiks līdz automātiskajai ieslēgšanai. |
| Adjustment | TSL By 2 Times at Remote Control | No / Yes | Dubultā aizslēgšana: divi spiedieni 5 s laikā. ASV tirgū nedrīkst būt Yes. |
| Adjustment | Double Unlocking with Remote Control | No / Yes | – |
| Adjustment | TSL Locking with key | No / Yes | Dubultā aizslēgšana: divi atslēgas pagriezieni 5 s laikā. |
| Adjustment | Sound Indication At TSL | No / Yes | – |
| Adjustment | Speed Dependant Locking Of Trunk | No / Yes | – |
| Adjustment | Lock Delay When Not Opening The Trunk | No / Yes | – |
| Adjustment | Lock Delay Time After Closing Trunk Lid | No / Yes | – |
| Adjustment | Belt Warning Sound | On / Off | Jāsaskaņo ar SID 'Extended Belt Reminder'. |
| Adjustment | Transport Mode | On / Off | Atslēdz centrālo atslēgu un signalizāciju, lai taupītu akumulatoru. |
| Adjustment | Steering Wheel Position | Left Hand Side / Right Hand Side | Durvju piktogrammai mērinstrumentu panelī. |

## DICE: gaismas un tīrītāji

WIS: <https://saabwisonline.com/9-5-9600/2007/3-electrical-system/dice/fault-diagnosis-general>

| Izvēlne | Uzstādījums | Vērtības | Piezīme |
|---|---|---|---|
| Adjustment | Audible Key Warning | Yes / No | Brīdinājums par atslēgu aizdedzē, kad atver durvis. |
| Adjustment | Daylight Driving Lights | Alternative 1 / Alternative 2 / Alternative 3 | 1: slēdža 1./2. pozīcijā gaismu nav (visi tirgi, izņemot SE un CA). 2: tuvās gaismas 1. pozīcijā (SE). 3: tuvās gaismas visās pozīcijās (CA). |
| Adjustment | Fog Light Variant | Alternative 1 / Alternative 2 / Alternative 3 | 1: neatkarīgi no tuvajām gaismām. 2: nevar ieslēgt kopā ar tuvajām (US/CA). 3: kopā ar tālajām gaismām. |
| Adjustment | Fan Variant | Single Fan / Dual Fans | Komplektācija, nav jāmaina. |
| Adjustment | A/C System Configuration | Yes / No | Komplektācija, nav jāmaina. |
| Adjustment | Front Wiper Extra Wipe | Yes / No | Papildu vēziens 10 s pēc stikla mazgāšanas. |
| Adjustment | Lights On Warning | Yes / No | Brīdinājums par ieslēgtām gaismām, izņemot atslēgu. |
| Adjustment | Follow Me Home Light Active Time | 20 s / 25 s / 30 s / 35 s / 40 s / 45 s / 50 s | Cik ilgi tuvās gaismas deg pēc izkāpšanas. |

## ACC: klimata kontrole

WIS: <https://saabwisonline.com/9-5-9600/2007/8-body/automatic-climate-control-acc/fault-diagnosis-general>

| Izvēlne | Uzstādījums | Vērtības | Piezīme |
|---|---|---|---|
| Adjustment | Heated seat offset temperature | – | Sēdekļu apsildes temperatūras nobīde; vērtības WIS nav norādītas. |
| Panelis (bez rīka) | Auto/Manual rear window defrost | Auto / Manual | Turēt aizmugurējā stikla apsildes pogu ilgāk par 2 s. |
| Panelis (bez rīka) | Auto/Manual seat heating | Auto / Manual | Turēt sēdekļa apsildes pogu ilgāk par 2 s. |

## Nav iekļauts

- **Moduļu nomaiņas programmēšana** (Spare Part Programming) SID, TWICE, DICE un ACC moduļiem un VIN ierakstīšana DICE: vajadzīga tikai mainot pašu moduli.
- **Atslēgu un pulšu piesaiste** (TWICE "Learn Transponders And Remotes", izvēlne "Immobilizer"): apzināti nav iekļauta rīkā.

## Bez rīka maināmie

- Valoda un mērvienības: dzinējs izslēgts, īsi spiest i/SET līdz LANGUAGE/UNITS, tad turēt i/SET līdz signālam (2007. g. rokasgrāmata).
- Pulkstenis: divas pogas zem pulksteņa displeja.
- Servisa paziņojuma dzēšana: turēt CLEAR 8 sekundes.
- ACC automātiskā/manuālā aizmugurējā stikla un sēdekļu apsilde: turēt attiecīgo pogu ilgāk par 2 sekundēm.

## Juridiskas piezīmes

- Signalizācijas pīkstienu skaits ES un GB tirgū pēc WIS ir iestatīts 0 atbilstoši likumam.
- Dienas gaitas gaismu variants jāizvēlas atbilstoši Latvijas ceļu satiksmes prasībām.
