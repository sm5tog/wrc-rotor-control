# Logging Software Integration — SM5K WRC Rotor Control

This guide covers how to connect your logging software so it can send automatic bearing (azimuth) commands to SM5K WRC Rotor Control. It supplements the main [README](README.md).

## How it works

SM5K WRC Rotor Control listens for bearing packets on a UDP port (default **12040**, shown as "N1MM UDP listen port" in the app's ⚙ Settings). Most logging programs can send this format, often labelled "N1MM Rotor", "N1MM_ROTOR", or "PstRotator" in their own settings.

Two settings must always match between your logger and the rotor app:

- **Destination IP address** — `127.0.0.1` if the logger runs on the same PC as the rotor app, otherwise the actual IP address of the PC running the rotor app.
- **Port number** — must be identical on both sides. Default is `12040`.

If the app's "N1MM" status field in the top bar stays grey with `---` and never turns green, the rotor app is not receiving any packets. That means the problem is on the logging software's side (wrong IP, wrong port, feature not enabled, or a firewall blocking the port), not in SM5K WRC Rotor Control or the rotor itself.

## Log4OM2

Log4OM2 needs **two** separate pages configured. Missing either one is the most common cause of "nothing happens".

**1. Connections page** (left tree: Software integration → Connections → UDP tab)

- Under "UDP OUTBOUND", add a new connection.
- Port: `12040` (or whatever you set as the rotor app's UDP listen port).
- Destination IP Address: `127.0.0.1` (same PC) or the rotor PC's IP (different PC).
- **Service type: `PSTRotator`.** This is the field people miss — it defaults to something else (e.g. `N1MM_CONTACT`, which only sends logged QSO data, never bearings) and must be changed manually.
- Give the connection a name, tick it active, and click "Save and apply".

**2. Antenna Rotator page** (left tree: Software integration → Antenna rotator)

- Select **PSTRotator** (not "Disable rotor support").
- Tick **Send Azimuth**.
- Save and apply.

Both pages must be saved. Click a bearing/spot in Log4OM and the rotor app's compass and N1MM status field should update immediately.

## N1MM Logger+

- Config → Configure Ports, Antennas, Rotators, Other → Rotator tab.
- Enable the rotator, set the port to match the rotor app's UDP listen port (`12040` by default).
- IP address: `127.0.0.1` if running on the same PC, otherwise the rotor PC's IP.

## DXLab (Commander)

- Commander → Setup → Rotator.
- Select "PstRotator" as the rotator control protocol/interface.
- Set the destination host to the rotor PC's IP (or `127.0.0.1` if the same PC) and the port to match the rotor app's UDP listen port.

## PstRotator-compatible software (general)

Any software offering a generic "PstRotator" or "N1MM Rotor" UDP output can be pointed directly at the rotor app: set the destination IP and port to match the rotor app's settings as described above.

## Troubleshooting checklist

1. Rotor app is running and shows "Rotor: connected" (green) before you test the logger — the UDP listener only needs the app open, not the rotor itself connected, but confirm both.
2. IP address matches: `127.0.0.1` only works if both programs run on the *same* PC.
3. Port number is identical in both programs.
4. The correct output format/service type is selected in the logger (e.g. Log4OM2's `PSTRotator` service type, not `N1MM_CONTACT`).
5. Windows Firewall allows `SM5K-Rotor.exe` (check under Windows Security → Firewall → Allowed apps, both Private and Public networks).
6. Only one program should hold the TCP connection to the rotor itself (port 23) — the logger should always talk to the rotor app's UDP listener, never directly to the rotor's IP.

If you're still stuck, get in touch with screenshots of both the rotor app's ⚙ Settings and the relevant page(s) in your logging software.

73, Jonny — SM5TOG
