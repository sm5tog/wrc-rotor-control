## ==========================================================
## SM5K WRC Rotator Control
## WRC Wi-Fi Rotor Controller – GS-232 over TCP + N1MM UDP
## ==========================================================

import tkinter as tk
import threading
import socket
import math
import json
import os
import sys
import webbrowser
import xml.etree.ElementTree as ET

# Works correctly both as .py script and as PyInstaller EXE / desktop shortcut
if getattr(sys, 'frozen', False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(_BASE_DIR, "rotor_settings.json")
DEFAULT_HOST     = "192.168.1.1"
DEFAULT_PORT     = 23
DEFAULT_UDP_PORT = 12040
DEFAULT_SIZE     = 460
MIN_SIZE = 300
MAX_SIZE = 700
DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=5VX8NE7LQEGF4"

# ── Palette ────────────────────────────────────────────────
BG     = "#16181d"
PANEL  = "#1e2028"
BORDER = "#2a2d3a"
TEXT   = "#d4d8e8"
MUTED  = "#555a6e"
GREEN  = "#48c774"
RED    = "#e05252"
AMBER  = "#e8a030"
BTNBG  = "#2a2d3a"

# ── Settings ───────────────────────────────────────────────

def load_settings():
    try:
        with open(CONFIG_FILE) as f:
            d = json.load(f)
            return {
                "host":     d.get("host",     DEFAULT_HOST),
                "port":     int(d.get("port",     DEFAULT_PORT)),
                "udp_port": int(d.get("udp_port", DEFAULT_UDP_PORT)),
                "size":     int(d.get("size",     DEFAULT_SIZE)),
            }
    except Exception:
        return {"host": DEFAULT_HOST, "port": DEFAULT_PORT,
                "udp_port": DEFAULT_UDP_PORT, "size": DEFAULT_SIZE}

def save_settings(s):
    with open(CONFIG_FILE, "w") as f:
        json.dump(s, f, indent=2)

# ── Rotor TCP connection ───────────────────────────────────

class Rotor:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None
        self.lock = threading.Lock()
        self._connect()

    def _connect(self):
        try:
            s = socket.socket()
            s.settimeout(3)
            s.connect((self.host, self.port))
            self.sock = s
            return True
        except Exception:
            self.sock = None
            return False

    def reconnect(self, host, port):
        with self.lock:
            if self.sock:
                try: self.sock.close()
                except Exception: pass
            self.host = host
            self.port = port
            self.sock = None
        return self._connect()

    def _send(self, cmd, expect_reply=True):
        with self.lock:
            for _ in range(2):
                try:
                    if self.sock is None:
                        self._connect()
                    self.sock.send((cmd + "\r\n").encode())
                    if not expect_reply:
                        return ""
                    self.sock.settimeout(1)
                    return self.sock.recv(64).decode(errors="replace").strip()
                except Exception:
                    self.sock = None
            return None

    def get_azimuth(self):
        resp = self._send("C")
        if resp is None:
            return None
        try:
            return int(resp.strip().lstrip("+"))
        except ValueError:
            return None

    def goto(self, degrees):
        self._send(f"M{max(0, min(360, int(degrees))):03d}", expect_reply=False)

    def stop(self):
        self._send("S", expect_reply=False)



# ── N1MM UDP listener ──────────────────────────────────────
# N1MM sends XML packets on the configured UDP port:
#   <N1MMRotator><StationName>…</StationName><bearing>270.0</bearing>…</N1MMRotator>
# DXLab Suite uses the same format.

class UDPListener:
    def __init__(self, port, on_bearing):
        self.port = port
        self.on_bearing = on_bearing   # callback(float)
        self._sock = None
        self._thread = None
        self._running = False

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._sock:
            try: self._sock.close()
            except Exception: pass

    def restart(self, port):
        self.stop()
        self.port = port
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind(("", self.port))
            self._sock.settimeout(1.0)
            while self._running:
                try:
                    data, _ = self._sock.recvfrom(4096)
                    self._parse(data)
                except socket.timeout:
                    continue
        except Exception:
            pass
        finally:
            if self._sock:
                try: self._sock.close()
                except Exception: pass

    def _parse(self, data):
        try:
            text = data.decode(errors="replace").strip()
            if not text.startswith("<"):
                text = text[text.index("<"):]
            root = ET.fromstring(text)
            # Log4OM / PstRotator: <PST><AZIMUTH>161</AZIMUTH></PST>
            # N1MM / DXLab:        <N1MMRotator><bearing>270.0</bearing>…
            for tag in ("AZIMUTH", "bearing", "Bearing"):
                el = root.find(tag)
                if el is not None:
                    self.on_bearing(float(el.text))
                    return
        except Exception:
            pass


# ── Settings dialog ────────────────────────────────────────

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, cfg, on_apply):
        super().__init__(parent)
        self.title("Settings")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()
        self.on_apply = on_apply

        def row(label, default):
            tk.Label(self, text=label, bg=BG, fg=MUTED,
                     font=("Consolas", 10), anchor="w").pack(fill="x", padx=20, pady=(12, 2))
            e = tk.Entry(self, bg=BTNBG, fg=TEXT, insertbackground=TEXT,
                         font=("Consolas", 12), relief="flat",
                         highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=AMBER)
            e.insert(0, str(default))
            e.pack(fill="x", padx=20, ipady=4)
            return e

        self.e_host     = row("Rotor IP address",            cfg["host"])
        self.e_port     = row("Rotor TCP port",              cfg["port"])
        self.e_udp_port = row("N1MM UDP listen port",        cfg["udp_port"])
        self.e_size     = row(f"Compass size ({MIN_SIZE}–{MAX_SIZE} px)", cfg["size"])

        self.lbl_status = tk.Label(self, text="", bg=BG, fg=MUTED,
                                   font=("Consolas", 10))
        self.lbl_status.pack(pady=(10, 0))

        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(pady=(6, 16), padx=20, fill="x")

        tk.Button(btn_row, text="Connect & save",
                  bg=BTNBG, fg=TEXT, font=("Consolas", 11, "bold"),
                  relief="flat", bd=0, padx=16, pady=6,
                  activebackground=BORDER, activeforeground=TEXT,
                  cursor="hand2", command=self._apply).pack(side="left")

        tk.Button(btn_row, text="Close",
                  bg=BG, fg=MUTED, font=("Consolas", 10),
                  relief="flat", bd=0, padx=12, pady=6,
                  activebackground=BORDER, activeforeground=TEXT,
                  cursor="hand2", command=self.destroy).pack(side="right")

        donate = tk.Label(self, text="♥ Support this project (PayPal)",
                          bg=BG, fg=MUTED, font=("Consolas", 9, "underline"),
                          cursor="hand2")
        donate.pack(pady=(0, 14))
        donate.bind("<Button-1>", lambda e: webbrowser.open(DONATE_URL))
        donate.bind("<Enter>", lambda e: donate.config(fg=AMBER))
        donate.bind("<Leave>", lambda e: donate.config(fg=MUTED))

    def _apply(self):
        host = self.e_host.get().strip()
        try:
            port     = int(self.e_port.get().strip())
            udp_port = int(self.e_udp_port.get().strip())
            size     = max(MIN_SIZE, min(MAX_SIZE, int(self.e_size.get().strip())))
        except ValueError:
            self.lbl_status.config(text="Invalid value.", fg=RED)
            return
        self.lbl_status.config(text="Connecting...", fg=MUTED)
        self.update_idletasks()
        threading.Thread(
            target=lambda: self.on_apply(
                {"host": host, "port": port, "udp_port": udp_port, "size": size},
                self._on_result),
            daemon=True).start()

    def _on_result(self, ok):
        self.after(0, lambda: self.lbl_status.config(
            text="● Connected!" if ok else "● Failed.",
            fg=GREEN if ok else RED))


# ── Main app ───────────────────────────────────────────────

class RotorApp(tk.Tk):

    STOP_R_FRAC  = 0.12
    TICK_GAP_MAJ = 18
    TICK_GAP_MIN = 10

    def __init__(self):
        super().__init__()
        self.title("SM5K WRC Rotator Control")
        self.configure(bg=BG)
        self.resizable(False, False)

        self._cfg = load_settings()
        self.rotor = Rotor(self._cfg["host"], self._cfg["port"])
        self.az_actual = None
        self.az_target = None
        self._canvas_size = self._cfg["size"]
        self._az_prev = None          # last reading, for stall detection
        self._stall_count = 0         # polls with no movement
        self._correction_count = 0    # corrections sent for current target

        self._udp = UDPListener(self._cfg["udp_port"], self._on_udp_bearing)
        self._udp.start()

        self._build_ui()
        self._poll()

    # ── Geometry ──────────────────────────────────────────

    @property
    def _cx(self): return self._canvas_size // 2
    @property
    def _cy(self): return self._canvas_size // 2
    @property
    def _radius(self): return int(self._canvas_size * 0.44)
    @property
    def _stop_r(self): return max(18, int(self._radius * self.STOP_R_FRAC))

    # ── Layout ────────────────────────────────────────────

    def _build_ui(self):
        # Topbar
        bar = tk.Frame(self, bg=BORDER)
        bar.pack(fill="x")

        self.lbl_conn = tk.Label(bar, text="Rotor: ---", bg=BORDER, fg=MUTED,
                                 font=("Consolas", 9), anchor="w")
        self.lbl_conn.pack(side="left", padx=6, pady=3)

        self.lbl_n1mm = tk.Label(bar, text="N1MM: ---", bg=BORDER, fg=MUTED,
                                 font=("Consolas", 9), anchor="w")
        self.lbl_n1mm.pack(side="left", padx=6, pady=3)

        cfg_btn = tk.Button(bar, text="⚙", bg=BORDER, fg=MUTED,
                            activebackground=BORDER, activeforeground=TEXT,
                            relief="flat", font=("Consolas", 12),
                            cursor="hand2", bd=0,
                            command=self._open_settings)
        cfg_btn.pack(side="right", padx=8, pady=2)

        # Canvas
        C = self._canvas_size
        self.canvas = tk.Canvas(self, width=C, height=C, bg=BG,
                                highlightthickness=0, cursor="crosshair")
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._on_click)

        self._draw_static()

    def _rebuild_canvas(self):
        C = self._canvas_size
        self.canvas.config(width=C, height=C)
        self.canvas.delete("all")
        self.needle_target = None
        self.needle_actual = None
        self.label_actual_deg = None
        self.label_target_deg = None
        self._draw_static()
        self._update_canvas()

    # ── Compass rose ──────────────────────────────────────

    def _draw_static(self):
        cx = cy = self._cx
        R = self._radius
        outer     = R
        inner_maj = R - self.TICK_GAP_MAJ
        inner_min = R - self.TICK_GAP_MIN

        self.canvas.create_oval(cx - R - 3, cy - R - 3,
                                cx + R + 3, cy + R + 3,
                                outline=BORDER, width=2, fill=PANEL)

        for deg in range(0, 360, 5):
            rad = math.radians(deg - 90)
            c, s = math.cos(rad), math.sin(rad)
            if deg % 30 == 0:
                inner, color, w = inner_maj - 6, TEXT, 2
            elif deg % 10 == 0:
                inner, color, w = inner_maj, MUTED, 1
            else:
                inner, color, w = inner_min, BORDER, 1
            self.canvas.create_line(cx + c * inner, cy + s * inner,
                                    cx + c * outer, cy + s * outer,
                                    fill=color, width=w)

        lbl_r = inner_maj - int(R * 0.12)
        for deg, lbl in {0: "N", 90: "E", 180: "S", 270: "W"}.items():
            rad = math.radians(deg - 90)
            self.canvas.create_text(cx + math.cos(rad) * lbl_r,
                                    cy + math.sin(rad) * lbl_r,
                                    text=lbl, fill=TEXT,
                                    font=("Consolas", max(8, R // 14), "bold"))

        deg_r = inner_maj - int(R * 0.09)
        cardinals = {0, 90, 180, 270}
        fsz = max(7, R // 20)
        for deg in range(0, 360, 30):
            if deg in cardinals:
                continue
            rad = math.radians(deg - 90)
            self.canvas.create_text(cx + math.cos(rad) * deg_r,
                                    cy + math.sin(rad) * deg_r,
                                    text=str(deg), fill=MUTED,
                                    font=("Consolas", fsz))

        sr = self._stop_r
        self.stop_circle = self.canvas.create_oval(
            cx - sr, cy - sr, cx + sr, cy + sr,
            fill="#2a1a1a", outline="#5a2020", width=1)
        self.stop_label = self.canvas.create_text(
            cx, cy, text="■", fill="#5a2020",
            font=("Consolas", max(9, sr - 6), "bold"))

        self.needle_target    = None
        self.needle_actual    = None
        self.label_actual_deg = None
        self.label_target_deg = None

    # ── Dynamic drawing ───────────────────────────────────

    def _needle(self, degrees, color, length_frac, width):
        cx = cy = self._cx
        rad = math.radians(degrees - 90)
        L = self._radius * length_frac
        return self.canvas.create_line(cx, cy,
                                       cx + math.cos(rad) * L,
                                       cy + math.sin(rad) * L,
                                       fill=color, width=width,
                                       arrow=tk.LAST,
                                       arrowshape=(max(8, width * 3),
                                                   max(10, width * 3 + 2),
                                                   max(3, width)),
                                       capstyle=tk.ROUND)

    def _update_canvas(self):
        for item in (self.needle_target, self.needle_actual,
                     self.label_actual_deg, self.label_target_deg):
            if item:
                self.canvas.delete(item)

        cx = cy = self._cx
        R = self._radius
        fsz_az  = max(12, R // 8)
        fsz_tgt = max(10, R // 11)

        if self.az_target is not None:
            self.needle_target = self._needle(self.az_target, AMBER, 0.74, 2)

        if self.az_actual is not None:
            self.needle_actual = self._needle(self.az_actual, GREEN, 0.87, max(3, R // 50))
            self.label_actual_deg = self.canvas.create_text(
                cx, cy + R * 0.48,
                text=f"{int(self.az_actual)}°",
                fill=GREEN, font=("Consolas", fsz_az, "bold"))

        if self.az_target is not None:
            self.label_target_deg = self.canvas.create_text(
                cx, cy + R * 0.63,
                text=f"→ {int(self.az_target)}°",
                fill=AMBER, font=("Consolas", fsz_tgt))

        self.canvas.tag_raise(self.stop_circle)
        self.canvas.tag_raise(self.stop_label)

    # ── Mouse click ───────────────────────────────────────

    def _on_click(self, event):
        cx = cy = self._cx
        dist = math.hypot(event.x - cx, event.y - cy)
        if dist <= self._stop_r:
            self._stop()
            return
        if dist > self._radius + 10:
            return
        angle = (math.degrees(math.atan2(event.y - cy, event.x - cx)) + 90) % 360
        self._set_target(angle)

    # ── Target / stop ─────────────────────────────────────

    def _set_target(self, angle):
        self.az_target = angle
        self._stall_count = 0
        self._correction_count = 0
        self.rotor.goto(angle)
        self._update_canvas()

    def _stop(self):
        self.az_target = None
        self.rotor.stop()
        self._update_canvas()

    # ── N1MM UDP callback ─────────────────────────────────

    def _on_udp_bearing(self, bearing):
        # Called from UDP thread — schedule on main thread
        self.after(0, self._apply_udp_bearing, bearing)

    def _apply_udp_bearing(self, bearing):
        self.lbl_n1mm.config(text=f"N1MM: {int(bearing)}°", fg=AMBER)
        self._set_target(bearing)

    # ── Poll ──────────────────────────────────────────────

    def _poll(self):
        def worker():
            az = self.rotor.get_azimuth()
            self.after(0, self._on_poll_result, az)
        threading.Thread(target=worker, daemon=True).start()

    def _on_poll_result(self, az):
        if az is not None:
            self.az_actual = az
            self.lbl_conn.config(text="Rotor: connected", fg=GREEN)

            if self.az_target is not None:
                error = abs(az - self.az_target)
                if error <= 2:
                    # On target
                    self.az_target = None
                    self._stall_count = 0
                    self._correction_count = 0
                    self.lbl_n1mm.config(text="N1MM: ---", fg=MUTED)
                else:
                    # Track stall: no movement (<1°) since last poll
                    if self._az_prev is not None and abs(az - self._az_prev) < 1:
                        self._stall_count += 1
                    else:
                        self._stall_count = 0

                    # 17 polls × 300 ms ≈ 5 s stall, still >5° off → goto again
                    if self._stall_count >= 17 and error > 5 and self._correction_count < 3:
                        self._correction_count += 1
                        self._stall_count = 0
                        self.rotor.goto(self.az_target)

            self._az_prev = az
        else:
            self.lbl_conn.config(text="Rotor: no connection", fg=RED)

        self._update_canvas()
        self.after(300, self._poll)

    # ── Settings ──────────────────────────────────────────

    def _open_settings(self):
        SettingsDialog(self, self._cfg, self._apply_settings)

    def _apply_settings(self, new_cfg, callback):
        ok = self.rotor.reconnect(new_cfg["host"], new_cfg["port"])
        if new_cfg["udp_port"] != self._cfg["udp_port"]:
            self._udp.restart(new_cfg["udp_port"])
        self._cfg = new_cfg
        self._canvas_size = new_cfg["size"]
        save_settings(new_cfg)
        self.after(0, self._rebuild_canvas)
        callback(ok)


# ── Entry point ───────────────────────────────────────────

if __name__ == "__main__":
    app = RotorApp()
    app.mainloop()
