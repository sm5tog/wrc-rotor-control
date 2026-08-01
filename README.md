# SM5K WRC Rotor Control

A lightweight Windows GUI for controlling a **WRC Wi-Fi Rotor Controller** (GS-232 protocol over TCP), with automatic bearing tracking from **N1MM**, **Log4OM**, and **DXLab/PstRotator** via UDP.

![status](https://img.shields.io/badge/status-active-brightgreen)

## Features

- Compass-style GUI — click anywhere on the dial to set a target heading, click the center to stop
- Live rotor connection status
- Listens for UDP bearing packets from N1MM / Log4OM / DXLab (auto-rotate on band/spot changes), and honors stop packets from PstRotator-compatible software — see [logging software setup guide](README_ROTOR.md)
- Automatic stall detection and correction if the rotor overshoots or gets stuck
- Configurable rotor IP, port, UDP listen port, and window size — no source edits needed
- Also ships as a standalone CLI script (`rotor.py`) for scripted control

## Usage

Click anywhere on the compass dial to send the rotor to that heading. Click the red square in the center to stop. That's it — no menus, no setup beyond the ⚙ settings icon.

## Compatibility

Since the rotor is controlled over the standard **GS-232 protocol**, this should also work with other rotor controllers that speak GS-232 over TCP, not just the WRC unit — the IP/port are fully configurable.

## Requirements

- Windows (tested) — should run anywhere Python + Tkinter is available
- Python 3.9+ (only needed if running from source; the compiled `.exe` has no dependencies)
- A WRC Wi-Fi Rotor Controller reachable on your network

## Running from source

```
python rotor_gui.py
```

On first run it creates `rotor_settings.json` next to the script with default values. Open the ⚙ settings icon in the app to set your rotor's IP address, port, and the UDP port your logging software sends bearings on.

## Compiled EXE

Pre-built Windows executables are published separately at
[sm5tog/wrc-rotor-control-releases](https://github.com/sm5tog/wrc-rotor-control-releases) — no Python installation required.

## CLI usage

```
python rotor.py                # print current bearing
python rotor.py goto <degrees> # rotate to a heading
python rotor.py stop           # stop rotation
```

Uses the same `rotor_settings.json` as the GUI, if present.

## Building the EXE yourself

```
pyinstaller rotor.spec
```

Output goes to `dist/SM5K-Rotor.exe`.

## Support this project

If this saved you some time or money, consider [buying me a coffee via PayPal](https://www.paypal.com/donate/?hosted_button_id=5VX8NE7LQEGF4). Entirely optional — the software is free either way.

## License

MIT — see [LICENSE](LICENSE).

73, Jonny — SM5TOG
