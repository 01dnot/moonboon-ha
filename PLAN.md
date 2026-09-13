# HACS-integrasjon for Moonboon Connect 2 — plan

Bygger på den ferdig reverse-engineerte protokollen i `01dnot/moonboon-protocol`.

---

## 0. Den avgjørende forutsetningen: bonding

Alt annet i denne planen er rutinearbeid. **Dette ene punktet avgjør om
prosjektet er mulig.**

Fra reversingen vet vi:

| | Bondet klient | Ubondet klient |
|---|---|---|
| Kan koble til | når som helst | kun i paringsmodus |
| Flere samtidig | ja (begge telefonene) | — |
| Stabilitet | stabil | kastes ut etter ~30 s |

En integrasjon som ikke kan bonde blir ubrukelig: den ville krevd at du trykker
vogga i paringsmodus hver gang, og mistet forbindelsen hvert halvminutt.

**macOS kan ikke bonde her** — CoreBluetooth initierer kun paring når enheten
krever kryptering på et attributt, og SMP-karakteristikken gjør ikke det.
Linux/BlueZ kan derimot initiere paring eksplisitt (`Pair()` over D-Bus,
eksponert som `bleak.pair()`), fordi det er en link-lag-operasjon uavhengig av
attributtkrav. En HA-vert med lokal adapter skal derfor klare det.

**ESPHome Bluetooth Proxy støtter paring.** `ESPHomeClient.pair()` i
`bleak-esphome` kaller `bluetooth_device_pair` over ESPHome-API-et. Den kaster
`NotImplementedError` kun hvis proxy-firmwaren mangler `PAIRING`-feature-flagget
— altså et spørsmål om å oppgradere proxyen, ikke en manglende funksjon.

Den åpne feature requesten (esphome/feature-requests#2013) gjelder noe smalere:
å kunne oppgi en **PIN-kode** via YAML. Moonboon bruker etter alt å dømme
«Just Works»-paring, siden brukeren aldri taster inn en kode når telefonen
pares. Den begrensningen treffer oss derfor trolig ikke.

**Konklusjon: HA med ESPHome-proxy er sannsynligvis nok.** Lokal adapter er
fortsatt det sikreste, men ikke et krav. Må likevel verifiseres i spiken —
dette er utledet fra kildekode, ikke testet mot vår enhet.

### Spike før noe annet bygges

Kjør fra HA selv, over proxyen du allerede har — det er oppsettet som faktisk
skal brukes. En `python_script` eller en liten testintegrasjon holder:

```python
# 1. vogna i paringsmodus
ble_device = bluetooth.async_ble_device_from_address(hass, MAC, connectable=True)
client = await establish_connection(BleakClient, ble_device, "moonboon")
await client.pair()      # -> ESPHomeClient.pair() over proxy, eller BlueZ lokalt
# 2. koble fra, ta vogna UT av paringsmodus
# 3. koble til på nytt -> skal virke uten paringsmodus
# 4. hold forbindelsen i 10 min -> skal IKKE droppe hvert 30. sekund
# 5. sjekk at begge telefonene fortsatt fungerer samtidig
```

Feiler steg 3 eller 4, må planen endres fundamentalt.

**Ikke skriv en linje integrasjonskode før denne spiken er grønn.**

### Hvis spiken feiler

Skulle paring likevel ikke feste seg — enten over proxy eller i det hele tatt —
er reserveløsningen en ESP32-S3 med egen ESP-IDF-firmware som bonder selv og
eksponerer vogga mot HA via ESPHome-API eller MQTT. Det er et eget
innebygd-prosjekt, ikke en HACS-integrasjon, så det er verdt å unngå.

---

## 1. Arkitektur

```
custom_components/moonboon/
  __init__.py           setup/unload entry, oppretter coordinator
  config_flow.py        BT-discovery + paringsmodus-veiledning
  coordinator.py        DataUpdateCoordinator: tilkobling, polling, push
  entity.py             felles base (device_info, availability)
  fan.py                hovedkontroll
  sensor.py             tilstand, gjenstående, forrige økt
  binary_sensor.py      sikkerhetsstopp
  number.py             programlengde
  switch.py             fade-out av/på
  button.py             restart
  diagnostics.py        anonymisert dump til feilrapporter
  manifest.json
  strings.json + translations/{en,nb}.json
  lib/                  vendret protokollklient (se 1.1)
hacs.json
README.md
```

### 1.1 Protokollklienten

Start med å **vendre** klienten under `lib/` i integrasjonen. Den er liten
(~200 linjer) og vi eier den.

Hvis integrasjonen senere skal inn i HA core, må den flyttes til en PyPI-pakke
(`moonboon-ble`) og listes i `manifest.json` → `requirements`, siden core ikke
tillater vendret kode. Det er en ren refaktorering og haster ikke.

Klienten må gjøres om fra CLI-orientert til bibliotek:
- ingen `print`, kun exceptions og returverdier
- egne exceptions: `MoonboonError`, `MoonboonBadState`, `MoonboonNeedsWeight`
- ingen egen reconnect-løkke — det eier coordinatoren

---

## 2. Tilkoblingsstrategi

### Riktig coordinator: vanlig `DataUpdateCoordinator`

HA sin veiledning er entydig: *«If your device only communicates with an active
Bluetooth connection and does not use Bluetooth advertisements:
DataUpdateCoordinator.»*

Det er nøyaktig oss. Moonboon-annonseringen er tom — ingen service-UUID-er,
ingen manufacturer data, bare navnet. All informasjon krever aktiv tilkobling.

`PassiveBluetoothProcessorCoordinator` og `ActiveBluetooth*`-variantene er
bygget for enheter som kringkaster måledata i annonseringen, og passer ikke.

### Transport

HA sin Bluetooth-integrasjon håndterer adaptere og skanning:
- `"dependencies": ["bluetooth_adapters"]` i manifest
- `bluetooth.async_get_scanner()` i stedet for egen `BleakScanner`
  (unngår overhead av flere parallelle skannere)

### HA-API-er vi skal bruke

| API | Hvor | Hvorfor |
|---|---|---|
| `async_scanner_count(connectable=True)` | `async_setup_entry` | Er det i det hele tatt en adapter som kan koble til? Null → `ConfigEntryNotReady` med forklarende melding i stedet for en kryptisk timeout |
| `async_address_reachability_diagnostics(..., CONNECTION)` | feilmeldinger + logg | Lesbar forklaring på hvorfor vogga ikke er nåbar — «ikke sett», «kun via ikke-tilkoblingsbar scanner», «alle scannere opptatt». Ikke parse strengen, den er kun for mennesker |
| `async_request_active_scan()` | config flow | Engangs aktiv sveip rett etter at brukeren har trykket paringsmodus, i stedet for å vente på neste periodiske runde |
| `async_process_advertisements()` | config flow | Vent på at vogga faktisk dukker opp, med timeout |
| `async_ble_device_from_address(connectable=True)` | coordinator | Hent `BLEDevice` uten egen skanner |
| `async_track_unavailable(connectable=True)` | coordinator | Marker entiteter `unavailable` når vogga forsvinner. Merk: kan ta opptil 5 min |
| `async_rediscover_address()` | `async_remove_entry` | Så integrasjonen kan settes opp igjen uten omstart av HA |
| `async_scanner_devices_by_address()` | `diagnostics.py` | Hvilke adaptere ser vogga, med RSSI — gull i feilrapporter |


**Vedvarende forbindelse** — med ett forbehold. Push-meldingene (`pot`,
`ustop`) kommer kun mens vi er tilkoblet, og de er hele grunnen til at HA kan
reagere umiddelbart når noen rører vogga.

Forbeholdet: kjøres dette over en ESPHome-proxy, koster en permanent
forbindelse **én av proxyens tilkoblingsplasser for godt**. ESP32 har 3 som
standard (maks 9, men over 5 frarådes). Med lokal adapter på HA-verten er
kostnaden ubetydelig. Dette bør derfor være en `options flow`-innstilling:
vedvarende (standard) eller koble-ved-behov.

- `bleak-retry-connector.establish_connection()` for robust oppkobling
  (HA-dokumentene anbefaler minst 10 s timeout — BlueZ må resolve services)
- `bluetooth.async_ble_device_from_address(hass, mac, connectable=True)`
- aldri gjenbruk en `BleakClient` mellom tilkoblinger — HA fraråder det
  eksplisitt fordi det gjør oppkobling mindre pålitelig
- reconnect med backoff ved brudd; entiteter blir `unavailable` imens

**Polling i tillegg**, fordi motoren ikke varsler ved programslutt:
- kjører: poll `65/3` hvert 30. sekund
- idle: hvert 5. minutt
- mellom pollene: regn ut `remaining` lokalt fra siste verdi + medgått tid,
  så nedtellinga i UI er jevn uten ekstra trafikk

**Åpen risiko:** vi vet ikke hvor mange samtidige tilkoblinger motoren tåler.
To telefoner fungerer. HA blir en tredje. Må testes i spiken.

---

## 3. Entitetsmodell

### Ikke `fan`

HA definerer `fan` eksplisitt som *«a device that controls the different
vectors of your fan such as speed, direction and oscillation»*. En vugge er
ikke det, og arkitekturdiskusjonene anbefaler konsekvent å komponere av
`switch`/`number`/`select` når ingen domene passer.

Brukere som *vil* ha en fan-entitet (f.eks. for slider i Apple Home via
HomeKit Bridge) kan selv konvertere med HA sin `switch_as_x`-hjelper. Da tar
vi ikke valget på deres vegne.

### switch.moonboon_vugge — hovedkontroll

| | |
|---|---|
| `turn_on()` | `restart` → `65/2` (med gjeldende fart/lengde) → `start` |
| `turn_off()` | `65/1 {"command":"stop"}` |
| `is_on` | `state == "running"` |

### Øvrige entiteter

| Entitet | Kilde |
|---|---|
| `sensor.moonboon_tilstand` | `65/3.state` (enum-device_class) |
| `sensor.moonboon_gjenstaende` | `65/3.remaining`, `device_class: duration` |
| `sensor.moonboon_ferdig_klokken` | beregnet timestamp — bedre enn nedtelling i UI |
| `sensor.moonboon_steg` | `current sequence / total sequences` |
| `sensor.moonboon_vuggebevegelser` | `65/4.cycles`, siste økt |
| `binary_sensor.moonboon_sikkerhetsstopp` | settes av `ustop`-push, nullstilles ved `restart` |
| `number.moonboon_fart` | 1–100 %, styrer `speed` i neste program |
| `number.moonboon_programlengde` | minutter, 1–720 |
| `select.moonboon_program` | `konstant` / `fade-out` — hvilken sekvens som bygges |
| `button.moonboon_restart` | `65/1 {"command":"restart"}` |

`65/0` (hw, fw, protocol, mac) går inn i `DeviceInfo`, ikke egne entiteter.

---

## 4. Config flow

1. **Discovery.** Motoren annonserer **ingen service-UUID-er**, kun navnet.
   Manifest må derfor matche på navn:
   ```json
   "bluetooth": [{"local_name": "Moonboon*", "connectable": true}]
   ```
   `connectable: true` er riktig her — vi trenger utgående tilkobling, og da
   skal vi ikke få treff fra scannere som kun lytter.

2. **Forhåndssjekk.** `async_scanner_count(hass, connectable=True) == 0` →
   avbryt med en melding om at det ikke finnes noen adapter som kan koble til.

3. **Paringssteg.** Egen skjerm: «Trykk vogga i paringsmodus (blått lys), og
   trykk Neste.» Deretter:
   ```python
   await bluetooth.async_request_active_scan(hass)
   info = await bluetooth.async_process_advertisements(
       hass, lambda si: True,
       {"address": address, "connectable": True},
       BluetoothScanningMode.ACTIVE, timeout=30)
   ```
   så `establish_connection()` + `client.pair()`.

4. **Verifisering.** Les `65/0`. Lykkes den, bruk `mac` som `unique_id` og vis
   fw/hw/protocol i bekreftelsen.

5. **Feilhåndtering.** Ved feil, hent
   `async_address_reachability_diagnostics(..., CONNECTION)` og vis den sammen
   med vår egen melding. Skill mellom:
   - fant den ikke → «står vogga i paringsmodus?»
   - `pair()` kastet `NotImplementedError` → «denne adapteren/proxyen støtter
     ikke paring, prøv en lokal Bluetooth-adapter»
   - paring avvist → vogga var ikke i paringsmodus da vi rakk frem

Legg inn en **repair issue** hvis bonding senere går tapt (vogga fabrikkstilt,
eller bond slettet) — da må brukeren pare på nytt, og det skal være selvforklarende.

---

## 5. Feilhåndtering som kommer direkte fra reversingen

Dette er detaljene som skiller en integrasjon som virker fra en som frustrerer:

**`rc: 0` betyr ikke at kommandoen hadde effekt.** Etter hver skriving må
`65/3` leses for å bekrefte. Gjelder spesielt `start`.

**Tom vogn.** Motoren har vektsensor og nekter å gå uten vekt. `turn_on` må
derfor lese status etterpå, og kaste
`HomeAssistantError("Motoren trenger vekt i vogga for å starte")` hvis den
fortsatt ikke kjører. Uten dette vil brukeren tro integrasjonen er ødelagt.

**`start` virker kun fra `ready`.** Send alltid `restart` først. Hopper man
over det, svarer motoren `rc: 0` og gjør ingenting.

**`stop` fra stoppet tilstand gir `rc: 6` (BAD_STATE).** Skal behandles som
suksess, ikke feil.

**Push-meldinger bruker SMP-versjon 0**, mens forespørsler bruker versjon 1.
Aldri valider versjonsfeltet ved mottak.

---

## 6. Faser

| Fase | Innhold | Avhenger av |
|---|---|---|
| **0** | Bonding-spike på Linux | — |
| **1** | Protokollklient som async-bibliotek + tester mot innspilte fixtures | 0 |
| **2** | Integrasjonsskjelett: manifest, config flow, coordinator, `fan` | 1 |
| **3** | Øvrige entiteter, diagnostics | 2 |
| **4** | HACS-pakking: `hacs.json`, brands-PR, oversettelser (nb/en), README | 3 |
| **5** | Polish: options flow, repair issues, reauth ved tapt bond | 4 |

Fase 0 er en kveld. Fase 1–2 gir noe som faktisk styrer vogga fra HA.
Fase 3–5 er det som gjør den delbar med andre.

---

## 7. Åpne spørsmål

1. **Hvor kjører HA, og finnes det en lokal BT-adapter?** Avgjør om prosjektet
   er gjennomførbart i det hele tatt.
2. **`fan` eller `switch` + `number`?** `fan` gir best UI, `switch`+`number` er
   semantisk ærligere.
3. **Skal integrasjonen holde forbindelsen permanent?** Gir umiddelbare
   oppdateringer, men okkuperer en tilkoblingsplass hos motoren.
4. **Publiseres den offentlig?** Påvirker om vi tar brands-PR mot HACS og
   hvor mye oversettelse/dokumentasjon som lønner seg.
