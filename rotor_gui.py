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
import subprocess
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET

import win_snap

# Works correctly both as .py script and as PyInstaller EXE / desktop shortcut
if getattr(sys, 'frozen', False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _dir_writable(d):
    probe = os.path.join(d, ".sm5k_write_test")
    try:
        with open(probe, "w"):
            pass
        os.remove(probe)
        return True
    except OSError:
        return False


def _resolve_config_file():
    """Keep rotor_settings.json next to the program when that folder is
    writable. If it is not (typically an install under Program Files), fall
    back to %APPDATA%\\SM5K-Rotor and migrate any existing file once. This
    stops the rotor IP, window position and size from silently failing to
    save for those users."""
    local = os.path.join(_BASE_DIR, "rotor_settings.json")
    if os.path.exists(local):
        if _dir_writable(_BASE_DIR):
            return local
    elif _dir_writable(_BASE_DIR):
        return local
    appdata = os.path.join(os.environ.get("APPDATA", _BASE_DIR), "SM5K-Rotor")
    try:
        os.makedirs(appdata, exist_ok=True)
    except OSError:
        return local
    target = os.path.join(appdata, "rotor_settings.json")
    if os.path.exists(local) and not os.path.exists(target):
        try:
            with open(local) as src, open(target, "w") as dst:
                dst.write(src.read())
        except OSError:
            pass
    return target


CONFIG_FILE = _resolve_config_file()
DEFAULT_HOST     = "192.168.1.1"
DEFAULT_PORT     = 23
DEFAULT_UDP_PORT = 12040
DEFAULT_UI_MODE  = "classic"          # "classic" (windowed, for most users) or "compact" (borderless companion)
SIZE_BY_MODE = {
    "classic": {"default": 460, "min": 50},
    "compact": {"default": 153, "min": 50},
}
MAX_SIZE = 2000          # only a sanity cap now; classic mode resizes freely
COMPACT_CEILING = 300    # a size above this belongs to classic, not compact
TOPBAR_H = 26            # approx height of the classic-mode status bar
DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=5VX8NE7LQEGF4"
HELP_URL   = "https://github.com/sm5tog/wrc-rotor-control/blob/master/README_ROTOR.md"

VERSION = "1.4.0"

# Auto-uppdatering: samma mönster som TCISync/jtspots, releaserna ligger i
# repots EGEN Releases-flik (sm5tog/wrc-rotor-control), inte i ett separat
# "-release"-repo.
UPDATE_REPO      = "sm5tog/wrc-rotor-control"
UPDATE_CHECK_URL = "https://api.github.com/repos/%s/releases/latest" % UPDATE_REPO
UPDATE_CHECK_MS  = 60 * 60 * 1000   # en gång i timmen
UPDATER_NAME     = "RotorUpdater.exe"

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
            ui_mode = d.get("ui_mode", DEFAULT_UI_MODE)
            if ui_mode not in SIZE_BY_MODE:
                ui_mode = DEFAULT_UI_MODE
            return {
                "host":     d.get("host",     DEFAULT_HOST),
                "port":     int(d.get("port",     DEFAULT_PORT)),
                "udp_port": int(d.get("udp_port", DEFAULT_UDP_PORT)),
                "ui_mode":  ui_mode,
                "size":     int(d.get("size", SIZE_BY_MODE[ui_mode]["default"])),
                "ontop":    bool(d.get("ontop", True)),
                "x":        d.get("x"),
                "y":        d.get("y"),
                "w":        d.get("w"),
                "h":        d.get("h"),
            }
    except Exception:
        return {"host": DEFAULT_HOST, "port": DEFAULT_PORT,
                "udp_port": DEFAULT_UDP_PORT, "ui_mode": DEFAULT_UI_MODE,
                "size": SIZE_BY_MODE[DEFAULT_UI_MODE]["default"],
                "ontop": True,
                "x": None, "y": None, "w": None, "h": None}

def save_settings(s):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(s, f, indent=2)
    except OSError:
        pass

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
    def __init__(self, port, on_bearing, on_stop=None):
        self.port = port
        self.on_bearing = on_bearing   # callback(float)
        self.on_stop = on_stop         # callback()
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
            # PstRotator stop:     <PST><STOP>1</STOP></PST>
            stop_el = root.find("STOP")
            if stop_el is not None and self.on_stop is not None:
                self.on_stop()
                return
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
        self.ui_mode = cfg["ui_mode"]
        self.var_ontop = tk.BooleanVar(value=cfg.get("ontop", True))

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

        tk.Label(self, text="Window style", bg=BG, fg=MUTED,
                 font=("Consolas", 10), anchor="w").pack(fill="x", padx=20, pady=(12, 2))
        mode_row = tk.Frame(self, bg=BG)
        mode_row.pack(fill="x", padx=20)
        self.mode_buttons = {}
        for mode, label in (("classic", "Classic (windowed)"), ("compact", "Compact (borderless)")):
            b = tk.Button(mode_row, text=label,
                          font=("Consolas", 9, "bold"), relief="flat", bd=0,
                          padx=8, pady=6, cursor="hand2",
                          command=lambda m=mode: self._select_mode(m))
            b.pack(side="left", expand=True, fill="x", padx=(0, 6) if mode == "classic" else 0)
            self.mode_buttons[mode] = b
        self._select_mode(self.ui_mode)

        self.e_host     = row("Rotor IP address",            cfg["host"])
        self.e_port     = row("Rotor TCP port",              cfg["port"])
        self.e_udp_port = row("N1MM UDP listen port",        cfg["udp_port"])
        self.e_size     = row(f"Compass size (min {SIZE_BY_MODE[self.ui_mode]['min']} px, or drag the window edge)", cfg["size"])
        self.lbl_size_hint = self.e_size

        chk = tk.Checkbutton(self, text="Always on top", variable=self.var_ontop,
                             bg=BG, fg=TEXT, selectcolor=BTNBG,
                             activebackground=BG, activeforeground=TEXT,
                             font=("Consolas", 10), anchor="w",
                             highlightthickness=0, bd=0)
        chk.pack(fill="x", padx=20, pady=(10, 0))

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
        donate.pack(pady=(0, 4))
        donate.bind("<Button-1>", lambda e: webbrowser.open(DONATE_URL))
        donate.bind("<Enter>", lambda e: donate.config(fg=AMBER))
        donate.bind("<Leave>", lambda e: donate.config(fg=MUTED))

        help_lbl = tk.Label(self, text="? Help / logging software setup",
                          bg=BG, fg=MUTED, font=("Consolas", 9, "underline"),
                          cursor="hand2")
        help_lbl.pack(pady=(0, 14))
        help_lbl.bind("<Button-1>", lambda e: webbrowser.open(HELP_URL))
        help_lbl.bind("<Enter>", lambda e: help_lbl.config(fg=AMBER))
        help_lbl.bind("<Leave>", lambda e: help_lbl.config(fg=MUTED))

    def _select_mode(self, mode):
        self.ui_mode = mode
        for m, b in self.mode_buttons.items():
            selected = (m == mode)
            b.config(bg=AMBER if selected else BTNBG,
                     fg=BG if selected else TEXT,
                     activebackground=AMBER if selected else BORDER)
        if hasattr(self, "lbl_size_hint"):
            # Reset the size field to the new mode's default when the current
            # value doesn't fit that mode (a classic-sized window has no place
            # in compact mode, and vice versa).
            try:
                cur = int(self.e_size.get().strip())
            except ValueError:
                cur = 0
            lo = SIZE_BY_MODE[mode]["min"]
            hi = COMPACT_CEILING if mode == "compact" else MAX_SIZE
            if cur < lo or cur > hi:
                self.e_size.delete(0, "end")
                self.e_size.insert(0, str(SIZE_BY_MODE[mode]["default"]))

    def _apply(self):
        host = self.e_host.get().strip()
        try:
            port     = int(self.e_port.get().strip())
            udp_port = int(self.e_udp_port.get().strip())
            min_size = SIZE_BY_MODE[self.ui_mode]["min"]
            size     = max(min_size, min(MAX_SIZE, int(self.e_size.get().strip())))
        except ValueError:
            self.lbl_status.config(text="Invalid value.", fg=RED)
            return
        self.lbl_status.config(text="Connecting...", fg=MUTED)
        self.update_idletasks()
        threading.Thread(
            target=lambda: self.on_apply(
                {"host": host, "port": port, "udp_port": udp_port,
                 "ui_mode": self.ui_mode, "size": size,
                 "ontop": self.var_ontop.get()},
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
        self.title("SM5K WRC Rotator Control  v%s" % VERSION)
        self.configure(bg=BG)

        self._cfg = load_settings()
        self.rotor = Rotor(self._cfg["host"], self._cfg["port"])
        self.az_actual = None
        self.az_target = None
        self._canvas_size = self._cfg["size"]
        self._az_prev = None          # last reading, for stall detection
        self._stall_count = 0         # polls with no movement
        self._correction_count = 0    # corrections sent for current target
        self.lbl_conn = None
        self.lbl_n1mm = None
        self._geom_save_job = None
        self._redraw_job = None
        self._last_win_size = (0, 0)
        self._topbar_h = TOPBAR_H     # refined from the real bar in _build_ui

        self._udp = UDPListener(self._cfg["udp_port"], self._on_udp_bearing, self._on_udp_stop)
        self._udp.start()

        self._apply_window_style()
        self._build_ui()
        self._restore_geometry()
        self.attributes("-topmost", self._cfg["ontop"])
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Configure>", self._on_configure)
        self._poll()
        self._update_available_tag = None
        self.after(0, self._update_check_tick)

    # ── Geometry ──────────────────────────────────────────

    @property
    def _is_compact(self): return self._cfg["ui_mode"] == "compact"
    @property
    def _cw(self):
        try:
            w = self.canvas.winfo_width()
            return w if w > 1 else self._canvas_size
        except (AttributeError, tk.TclError):
            return self._canvas_size
    @property
    def _ch(self):
        try:
            h = self.canvas.winfo_height()
            return h if h > 1 else self._canvas_size
        except (AttributeError, tk.TclError):
            return self._canvas_size
    @property
    def _cx(self): return self._cw // 2
    @property
    def _cy(self): return self._ch // 2
    @property
    def _radius(self): return int(min(self._cw, self._ch) * 0.44)
    @property
    def _stop_r(self): return max(18, int(self._radius * self.STOP_R_FRAC))

    # ── Window chrome ─────────────────────────────────────

    def _apply_window_style(self):
        # Borderless in compact mode (companion-window style); normal titlebar
        # in classic mode so it behaves like an ordinary desktop app.
        compact = self._is_compact
        self.overrideredirect(compact)
        # Classic mode resizes freely (the compass follows); compact mode
        # stays a fixed-size companion window.
        self.resizable(not compact, not compact)
        if not compact:
            self.minsize(SIZE_BY_MODE["classic"]["min"],
                         SIZE_BY_MODE["classic"]["min"] + self._topbar_h)

    def _restore_geometry(self):
        cfg = self._cfg
        if not self._is_compact:
            w, h = cfg.get("w"), cfg.get("h")
            if not w or not h:
                w = self._canvas_size
                h = self._canvas_size + self._topbar_h
            w = max(SIZE_BY_MODE["classic"]["min"], int(w))
            h = max(SIZE_BY_MODE["classic"]["min"] + self._topbar_h, int(h))
            self.minsize(SIZE_BY_MODE["classic"]["min"],
                         SIZE_BY_MODE["classic"]["min"] + self._topbar_h)
            self.geometry(f"{w}x{h}")
            self._canvas_size = min(w, h - self._topbar_h)
        x, y = cfg.get("x"), cfg.get("y")
        if x is not None and y is not None and self._point_on_screen(int(x), int(y)):
            self.geometry(f"+{int(x)}+{int(y)}")

    @staticmethod
    def _point_on_screen(x, y):
        # Reject a saved position that would place the window off every
        # attached display (e.g. a monitor that is no longer connected).
        try:
            import win32api, win32con
            vx = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
            vy = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
            vw = win32api.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
            vh = win32api.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)
            return (vx - 8) <= x <= (vx + vw - 40) and (vy - 8) <= y <= (vy + vh - 40)
        except Exception:
            return True

    def _on_configure(self, event):
        if event.widget is not self:
            return
        size = (self.winfo_width(), self.winfo_height())
        if size != self._last_win_size:
            self._last_win_size = size
            if not self._is_compact:
                if self._redraw_job is not None:
                    self.after_cancel(self._redraw_job)
                self._redraw_job = self.after(40, self._redraw_compass)
        if self._geom_save_job is not None:
            self.after_cancel(self._geom_save_job)
        self._geom_save_job = self.after(600, self._save_geometry)

    def _redraw_compass(self):
        self._redraw_job = None
        self._canvas_size = min(self._cw, self._ch)
        self.canvas.delete("all")
        self._draw_static()
        self._update_canvas()

    def _save_geometry(self):
        self._geom_save_job = None
        try:
            self._cfg["x"] = self.winfo_x()
            self._cfg["y"] = self.winfo_y()
            if not self._is_compact:
                self._cfg["w"] = self.winfo_width()
                self._cfg["h"] = self.winfo_height()
                # Keep "size" in step so the Settings dialog shows the real
                # current compass size instead of resetting the window.
                self._cfg["size"] = max(SIZE_BY_MODE["classic"]["min"],
                                        min(self.winfo_width(),
                                            self.winfo_height() - self._topbar_h))
            save_settings(self._cfg)
        except tk.TclError:
            pass

    # ── Layout ────────────────────────────────────────────

    def _build_ui(self):
        for w in self.winfo_children():
            w.destroy()

        if not self._is_compact:
            bar = tk.Frame(self, bg=BORDER)
            bar.pack(fill="x")
            self._bar = bar

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

            self.ontop_btn = tk.Button(bar, text="^",
                                bg=AMBER if self._cfg["ontop"] else BORDER,
                                fg=BG if self._cfg["ontop"] else MUTED,
                                activebackground=BORDER, activeforeground=TEXT,
                                relief="flat", font=("Consolas", 10, "bold"),
                                cursor="hand2", bd=0, width=2,
                                command=self._toggle_ontop)
            self.ontop_btn.pack(side="right", padx=(8, 0), pady=2)

            self.update_btn = tk.Button(bar, text="", bg=GREEN, fg=BG,
                                activebackground=GREEN, activeforeground=BG,
                                relief="flat", font=("Consolas", 9, "bold"),
                                cursor="hand2", bd=0,
                                command=self._launch_updater)
        else:
            self.lbl_conn = None
            self.lbl_n1mm = None
            self.ontop_btn = None
            self.update_btn = None

        if not self._is_compact:
            self.update_idletasks()
            self._topbar_h = max(self._bar.winfo_reqheight(), 1)

        C = self._canvas_size
        self.canvas = tk.Canvas(self, width=C, height=C, bg=BG,
                                highlightthickness=0, cursor="crosshair")
        if self._is_compact:
            self.canvas.pack()
        else:
            # Fill the window so the compass can follow a resize.
            self.canvas.pack(fill="both", expand=True)
        # Left button: press/drag/release – a plain click sets the target;
        # in compact mode a drag past the threshold moves the borderless window.
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", self._on_right_click)

        self._draw_static()

        if self.update_btn is not None and getattr(self, "_update_available_tag", None):
            self.update_btn.config(text="Update: %s" % self._update_available_tag)
            self.update_btn.pack(side="right", padx=(0, 8), pady=2)

    def _rebuild_canvas(self):
        self._apply_window_style()
        if self._is_compact and not (
                SIZE_BY_MODE["compact"]["min"] <= self._canvas_size
                <= COMPACT_CEILING):
            # Coming from a large classic window — start compact at its default.
            self._canvas_size = SIZE_BY_MODE["compact"]["default"]
        self._build_ui()
        if not self._is_compact:
            self.geometry(f"{self._canvas_size}x{self._canvas_size + self._topbar_h}")
        self._update_canvas()
        if self.az_actual is not None and self.lbl_conn is not None:
            self.lbl_conn.config(text="Rotor: connected", fg=GREEN)

    # ── Compass rose ──────────────────────────────────────

    def _draw_static(self):
        cx, cy = self._cx, self._cy
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

        if not self._is_compact:
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

    def _label_offset(self, degrees, base):
        # Flip the label to the opposite half from its own needle, so text
        # never sits on the needle it belongs to (or the other one).
        rad = math.radians(degrees - 90)
        return -base if math.sin(rad) > 0 else base

    def _needle(self, degrees, color, length_frac, width):
        cx, cy = self._cx, self._cy
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

        cx, cy = self._cx, self._cy
        R = self._radius
        sr = self._stop_r
        if self._is_compact:
            fsz_az, fsz_tgt = max(10, R // 9), max(8, R // 13)
            off_actual, off_target = R * 0.27, R * 0.42
        else:
            fsz_az, fsz_tgt = max(12, R // 8), max(10, R // 11)
            off_actual, off_target = R * 0.48, R * 0.63

        # Keep the digits clear of the stop ring, which always renders on
        # top of everything else.
        off_actual = max(off_actual, sr + fsz_az * 0.7)
        off_target = max(off_target, off_actual + fsz_tgt * 1.3)

        if self.az_target is not None:
            self.needle_target = self._needle(self.az_target, AMBER, 0.74, 2)

        if self.az_actual is not None:
            self.needle_actual = self._needle(self.az_actual, GREEN, 0.87, max(3, R // 50))
            y = self._label_offset(self.az_actual, off_actual)
            self.label_actual_deg = self.canvas.create_text(
                cx, cy + y,
                text=f"{int(self.az_actual)}°",
                fill=GREEN, font=("Consolas", fsz_az, "bold"))

        if self.az_target is not None:
            y = self._label_offset(self.az_target, off_target)
            self.label_target_deg = self.canvas.create_text(
                cx, cy + y,
                text=f"→ {int(self.az_target)}°",
                fill=AMBER, font=("Consolas", fsz_tgt))

        self.canvas.tag_raise(self.stop_circle)
        self.canvas.tag_raise(self.stop_label)
        for item in (self.label_actual_deg, self.label_target_deg):
            if item:
                self.canvas.tag_raise(item)

    # ── Mouse click ───────────────────────────────────────

    def _on_press(self, event):
        self._drag_origin = (event.x_root, event.y_root)
        self._win_origin  = (self.winfo_x(), self.winfo_y())
        self._moved = False

    def _on_drag(self, event):
        if not self._is_compact:
            return  # classic mode has a normal titlebar to drag by
        dx = event.x_root - self._drag_origin[0]
        dy = event.y_root - self._drag_origin[1]
        if abs(dx) > 5 or abs(dy) > 5:
            self._moved = True
        if self._moved:
            x = self._win_origin[0] + dx
            y = self._win_origin[1] + dy
            x, y = win_snap.snap(self.title(), x, y, self.winfo_width(), self.winfo_height())
            self.geometry(f"+{x}+{y}")

    def _on_release(self, event):
        # A plain click (no meaningful drag) counts as a target/stop action.
        if not self._moved:
            self._handle_click(event.x, event.y)
        else:
            self._save_geometry()

    def _handle_click(self, x, y):
        cx, cy = self._cx, self._cy
        dist = math.hypot(x - cx, y - cy)
        if dist <= self._stop_r:
            self._stop()
            return
        if dist > self._radius + 10:
            return
        angle = (math.degrees(math.atan2(y - cy, x - cx)) + 90) % 360
        self._set_target(angle)

    def _on_right_click(self, event):
        menu = tk.Menu(self, tearoff=0, bg=PANEL, fg=TEXT,
                       activebackground=BORDER, activeforeground=TEXT, bd=0)
        menu.add_command(label="Settings…", command=self._open_settings)
        menu.add_command(label="Help / logging software setup", command=lambda: webbrowser.open(HELP_URL))
        menu.add_separator()
        menu.add_command(label="Avsluta", command=self._on_close)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _on_close(self):
        for job in (self._geom_save_job, self._redraw_job):
            if job is not None:
                self.after_cancel(job)
        self._save_geometry()
        self.destroy()

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
        if self.lbl_n1mm is not None:
            self.lbl_n1mm.config(text=f"N1MM: {int(bearing)}°", fg=AMBER)
        self._set_target(bearing)

    def _on_udp_stop(self):
        # Called from UDP thread — schedule on main thread
        self.after(0, self._stop)

    # ── Poll ──────────────────────────────────────────────

    def _poll(self):
        def worker():
            az = self.rotor.get_azimuth()
            self.after(0, self._on_poll_result, az)
        threading.Thread(target=worker, daemon=True).start()

    def _on_poll_result(self, az):
        if az is not None:
            self.az_actual = az
            if self.lbl_conn is not None:
                self.lbl_conn.config(text="Rotor: connected", fg=GREEN)

            if self.az_target is not None:
                error = abs(az - self.az_target)
                if error <= 2:
                    # On target
                    self.az_target = None
                    self._stall_count = 0
                    self._correction_count = 0
                    if self.lbl_n1mm is not None:
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
            # No reply from the rotor: clear the reading. In compact mode the
            # absence of the green value is the "not connected" cue; in
            # classic mode the topbar label also switches to red.
            self.az_actual = None
            if self.lbl_conn is not None:
                self.lbl_conn.config(text="Rotor: no connection", fg=RED)

        self._update_canvas()
        self.after(300, self._poll)

    # ── Ontop ─────────────────────────────────────────────

    def _toggle_ontop(self):
        self._cfg["ontop"] = not self._cfg["ontop"]
        self.attributes("-topmost", self._cfg["ontop"])
        save_settings(self._cfg)
        if self.ontop_btn is not None:
            self.ontop_btn.config(
                bg=AMBER if self._cfg["ontop"] else BORDER,
                fg=BG if self._cfg["ontop"] else MUTED)

    # ── Auto-uppdatering (samma mönster som TCISync/jtspots) ──

    def _update_check_tick(self):
        threading.Thread(target=self._check_for_update, daemon=True).start()
        self.after(UPDATE_CHECK_MS, self._update_check_tick)

    @staticmethod
    def _version_tuple(v):
        v = v.strip().lstrip("vV")
        parts = []
        for p in v.split("."):
            try:
                parts.append(int(p))
            except ValueError:
                break
        return tuple(parts)

    def _check_for_update(self):
        # Frågar bara GitHubs "senaste release"-tagg, laddar aldrig ner något
        # själv. Tyst vid nätverksfel/inget repo/inga releaser än.
        try:
            req = urllib.request.Request(UPDATE_CHECK_URL, headers={"User-Agent": "SM5K-Rotor"})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.load(r)
            tag = data.get("tag_name", "")
            if self._version_tuple(tag) > self._version_tuple(VERSION):
                self.after(0, lambda t=tag: self._show_update_available(t))
        except Exception:
            pass

    def _show_update_available(self, tag):
        if self._update_available_tag == tag:
            return
        self._update_available_tag = tag
        if self.update_btn is not None:
            self.update_btn.config(text="Update: %s" % tag)
            self.update_btn.pack(side="right", padx=(0, 8), pady=2)

    def _launch_updater(self):
        # Bara meningsfullt i en fryst .exe (se rotor_updater.py), no-op annars
        # (t.ex. vid `python rotor_gui.py` under utveckling).
        if not getattr(sys, "frozen", False):
            return
        updater = os.path.join(_BASE_DIR, UPDATER_NAME)
        if not os.path.exists(updater):
            return
        try:
            subprocess.Popen([updater, "--update"], cwd=_BASE_DIR)
        except Exception:
            return
        self._on_close()

    # ── Settings ──────────────────────────────────────────

    def _open_settings(self):
        SettingsDialog(self, self._cfg, self._apply_settings)

    def _apply_settings(self, new_cfg, callback):
        ok = self.rotor.reconnect(new_cfg["host"], new_cfg["port"])
        if new_cfg["udp_port"] != self._cfg["udp_port"]:
            self._udp.restart(new_cfg["udp_port"])
        style_changed = new_cfg["ui_mode"] != self._cfg["ui_mode"]
        ontop_changed = new_cfg["ontop"] != self._cfg["ontop"]
        self._cfg = new_cfg
        self._canvas_size = new_cfg["size"]
        save_settings(new_cfg)
        if ontop_changed:
            self.after(0, lambda: self.attributes("-topmost", new_cfg["ontop"]))
        self.after(0, self._rebuild_canvas if style_changed else self._resize_only)
        callback(ok)

    def _resize_only(self):
        if not self._is_compact:
            self.geometry(f"{self._canvas_size}x{self._canvas_size + self._topbar_h}")
        self._build_ui()
        self._update_canvas()
        if self.az_actual is not None and self.lbl_conn is not None:
            self.lbl_conn.config(text="Rotor: connected", fg=GREEN)


# ── Entry point ───────────────────────────────────────────

if __name__ == "__main__":
    app = RotorApp()
    app.mainloop()
