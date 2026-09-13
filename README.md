# Moonboon for Home Assistant

[![hacs](https://img.shields.io/badge/HACS-custom-41BDF5.svg)](https://hacs.xyz)
[![release](https://img.shields.io/github/v/release/01dnot/moonboon-ha)](https://github.com/01dnot/moonboon-ha/releases)

Control a **Moonboon Connect 2** baby cradle motor from Home Assistant over
Bluetooth LE. No cloud, no account — the integration talks directly to the motor.

Built on a [reverse-engineered protocol specification](https://github.com/01dnot/moonboon-protocol).

> Not affiliated with Moonboon.

## Entities

| Entity | What it does |
|---|---|
| `switch` | Start and stop the rocking |
| `number` Speed | 1–100 % — finer control than the cradle's five buttons |
| `number` Program length | 1–720 minutes |
| `select` Program | Constant speed, or the app's fade-out ramp |
| `sensor` Motor state | Rocking, ready, stopped at the cradle, … |
| `sensor` Remaining / Finishes at | Countdown, and the wall-clock end time |
| `sensor` Last session | Rocks and length of the previous run |
| `binary_sensor` Safety stop | Pushed the instant someone holds the cradle back |
| `button` Reset motor | Clears a stopped state so it can run again |

Prefer a percentage slider? Convert the switch with Home Assistant's
[`switch_as_x`](https://www.home-assistant.io/integrations/switch_as_x/) helper.
It is deliberately not a `fan` entity — a cradle is not a fan.

## Requirements

- Home Assistant 2024.12 or newer
- A Bluetooth adapter that can make **outgoing connections**: a local adapter,
  or an ESPHome Bluetooth proxy with active connections enabled

### Pairing

The motor only accepts new connections while it is in **pairing mode**, and
drops unpaired clients after about 30 seconds. Setup therefore asks you to
press the pairing button so the cradle lights up blue. Once paired, Home
Assistant can connect whenever it needs to, alongside the phones already paired.

Using an ESPHome proxy, its firmware must be new enough to support pairing.
If it is not, setup says so rather than failing obscurely.

## Installation

### Via HACS

1. In Home Assistant, open **HACS**
2. Open the **⋮** menu in the top right and choose **Custom repositories**
3. Paste `https://github.com/01dnot/moonboon-ha`, pick category **Integration**,
   and select **Add**
4. Find **Moonboon** in the list, open it and select **Download**
5. **Restart Home Assistant** — a reload is not enough, Python modules stay
   cached until a full restart

### Manually

Copy `custom_components/moonboon` into `config/custom_components/` so you end
up with `config/custom_components/moonboon/`, then restart Home Assistant.

### Adding the cradle

The motor is discovered automatically — look for it under
**Settings → Devices & Services**. If it does not appear, add it with
**+ Add integration** and search for *Moonboon*.

Setup asks you to press the pairing button on the cradle so it lights up blue.
That step is required: the motor only accepts new connections while in pairing
mode. Close the official Moonboon app first — the motor stops advertising while
a paired phone is connected, so Home Assistant cannot find it.

## Languages

The interface is available in **English** and **Norwegian (bokmål)**. Home
Assistant picks per user, from the language in their profile, so one household
can use both.

Entity IDs are always derived from the English names, so automations keep
working if someone changes language.

## Entity IDs

| Entity | ID |
|---|---|
| Switch | `switch.moonboon` |
| Speed | `number.moonboon_speed` |
| Program length | `number.moonboon_program_length` |
| Program | `select.moonboon_program` |
| Motor state | `sensor.moonboon_motor_state` |
| Remaining | `sensor.moonboon_remaining` |
| Finishes at | `sensor.moonboon_finishes_at` |
| Program step | `sensor.moonboon_program_step` |
| Last session rocks | `sensor.moonboon_last_session_rocks` |
| Last session length | `sensor.moonboon_last_session_length` |
| Safety stop | `binary_sensor.moonboon_safety_stop` |
| Reset motor | `button.moonboon_reset_motor` |

## Example: one script for the usual nap

The stored speed follows changes made on the cradle itself, so a script that
sets everything explicitly gives the same result every time.

```yaml
alias: Rock
icon: mdi:cradle
sequence:
  - action: select.select_option
    target:
      entity_id: select.moonboon_program
    data:
      option: fade_out
  - action: number.set_value
    target:
      entity_id: number.moonboon_speed
    data:
      value: 40
  - action: number.set_value
    target:
      entity_id: number.moonboon_program_length
    data:
      value: 120
  - action: switch.turn_on
    target:
      entity_id: switch.moonboon
```

## Apple Home and Siri

Expose **only the script** through the HomeKit Bridge. A script becomes a
button in Apple Home, and a button has no on/off state -- so it is never caught
by "turn off everything" or by a room command. You can start the rocking on
purpose, but not stop it by accident.

If you would rather have a real on/off accessory, convert the switch with the
[`switch_as_x`](https://www.home-assistant.io/integrations/switch_as_x/) helper
and expose it as a **fan**. Siri treats accessory types as separate categories,
so "turn on the lights" will never reach a fan. Give it its own room as well:
a cradle sharing a room with the lights gets stopped by "turn off the bedroom".

## Things worth knowing

These come out of the reverse engineering and explain behaviour that would
otherwise look like bugs.

**The motor will not rock an empty cradle.** It has a weight sensor. Turning
the switch on with nothing in the cradle raises an error saying so, rather than
silently doing nothing.

**A manual stop has to be reset.** If someone stops the cradle by holding it,
the motor latches into a stopped state and ignores start until it is reset.
The switch does this for you; the *Reset motor* button is there for when you
want it explicitly.

**Changing speed restarts the program.** The motor has no way to adjust speed
without reloading the program, so the integration restarts it while preserving
roughly the time that was left.

**The motor only announces physical interaction.** It pushes a message when
someone changes settings at the cradle or holds it back — and nothing else, not
even when a program ends. The countdown is therefore polled: every 30 seconds
while rocking, every 5 minutes when idle.

## Troubleshooting

**It will not start, and nothing happens.** The cradle is probably empty. The
motor has a weight sensor and refuses to rock without a load; the integration
raises an error saying so.

**Pairing fails or times out.** Make sure the cradle is in pairing mode (blue
light) when you select Submit, and that the official app is closed. If you use
an ESPHome Bluetooth proxy, its firmware must be new enough to support pairing.

**Entities go unavailable.** The motor accepts a limited number of connections.
Check that it is in range of an adapter, and look at the *reachability* line in
the integration's diagnostics, which explains what the Bluetooth stack can see.

**Everything looks stale after an update.** Home Assistant caches Python
modules. Restart it fully, then check the log for the version that is actually
running:

```
Setting up Moonboon ... (integration version x.y.z)
```

### Debug logging

Add this to `configuration.yaml` and restart, then include the log in any
issue report:

```yaml
logger:
  logs:
    custom_components.moonboon: debug
```

Diagnostics can be downloaded from the integration page. Device addresses are
redacted, so they are safe to attach.

## Development

```bash
pip install pytest cbor2
pytest tests/
```

The tests run without Home Assistant and without hardware. Expected byte
strings are taken from captured traffic from the official app, so a change that
breaks compatibility fails the suite.
