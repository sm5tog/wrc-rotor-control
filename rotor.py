import socket
import time
import json
import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(_BASE_DIR, "rotor_settings.json")
DEFAULT_HOST = "192.168.1.1"
DEFAULT_PORT = 23
TIMEOUT = 5


def _load_config():
    try:
        with open(CONFIG_FILE) as f:
            d = json.load(f)
            return d.get("host", DEFAULT_HOST), int(d.get("port", DEFAULT_PORT))
    except Exception:
        return DEFAULT_HOST, DEFAULT_PORT


HOST, PORT = _load_config()


def _send(s, cmd):
    s.send((cmd + "\r\n").encode())
    time.sleep(0.3)
    s.settimeout(2)
    try:
        return s.recv(1024).decode(errors="replace").strip()
    except socket.timeout:
        return ""


def get_azimuth(s):
    resp = _send(s, "C")
    # Svar: +0153  (grader utan decimaler)
    resp = resp.strip().lstrip("+")
    return int(resp)


def goto(s, degrees):
    degrees = max(0, min(360, int(degrees)))
    _send(s, f"M{degrees:03d}")


def stop(s):
    _send(s, "A")


def connect():
    s = socket.socket()
    s.settimeout(TIMEOUT)
    s.connect((HOST, PORT))
    return s


if __name__ == "__main__":
    import sys

    s = connect()

    if len(sys.argv) == 1:
        az = get_azimuth(s)
        print(f"Aktuell bäring: {az}°")

    elif sys.argv[1] == "goto" and len(sys.argv) == 3:
        target = int(sys.argv[2])
        print(f"Roterar till {target}°...")
        goto(s, target)
        while True:
            az = get_azimuth(s)
            print(f"  {az}°", end="\r")
            if abs(az - target) <= 2:
                print(f"\nFramme: {az}°")
                break
            time.sleep(1)

    elif sys.argv[1] == "stop":
        stop(s)
        print("Stopp skickat.")

    else:
        print("Användning:")
        print("  python rotor.py              # läs av bäring")
        print("  python rotor.py goto <grader> # rotera till heading")
        print("  python rotor.py stop          # stoppa rotation")

    s.close()
