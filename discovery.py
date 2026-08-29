"""
discovery.py - find other Sync-Ghar servers on the local wifi.

How it works (plain words):
    The server runs a tiny "beacon" - a UDP socket that just listens.
    Any device on the same network can shout one short question into
    the air ("SMARTHOME_DISCOVER?"), and every Sync-Ghar server that
    hears it shouts back its address. No central list, no setup.

    from discovery import Beacon, discover
    Beacon(http_port=8000, scheme="http").start()   # the server does this
    found = discover()                               # a finder does this
    # -> [{"name": "pranjal-laptop",
    #      "url": "http://10.180.40.222:8000", ...}]

Command line:
    python discovery.py           search the wifi and print what's there
"""

import json
import socket
import threading
import time

DISCOVERY_PORT = 8001
PROBE = b"SMARTHOME_DISCOVER?"
REPLY_PREFIX = b"SMARTHOME_HERE "


def lan_ips():
    """This machine's addresses on the local wifi/LAN. Best effort."""
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))          # sends nothing, just picks the route
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass
    return sorted(ips)


# =============================================================
#  server side: answer "who's there?"
# =============================================================
class Beacon:
    """A background UDP responder. start() it once, stop() on shutdown."""

    def __init__(self, http_port=8000, scheme="http", name=None):
        self.http_port = http_port
        self.scheme = scheme
        self.name = name or socket.gethostname()
        self._sock = None
        self._thread = None
        self._stop = threading.Event()

    def _info(self):
        return {
            "name": self.name,
            "scheme": self.scheme,
            "port": self.http_port,
            "ips": lan_ips(),
        }

    def _run(self):
        while not self._stop.is_set():
            try:
                data, addr = self._sock.recvfrom(1024)
            except (OSError, socket.timeout):
                continue
            if data.strip() == PROBE:
                reply = REPLY_PREFIX + json.dumps(self._info()).encode("utf-8")
                try:
                    self._sock.sendto(reply, addr)
                except OSError:
                    pass

    def start(self):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind(("", DISCOVERY_PORT))
            self._sock.settimeout(0.5)
        except OSError as e:
            print(f"  (device discovery off: {e})")
            self._sock = None
            return self
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._sock:
            self._sock.close()
            self._sock = None


# =============================================================
#  finder side: shout, then collect the replies
# =============================================================
def discover(timeout=1.5):
    """
    Broadcast a probe and gather every Sync-Ghar server that answers.
    Returns a list of dicts, each with a ready-to-open "url".
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.4)

    for target in ("255.255.255.255", "<broadcast>"):
        try:
            sock.sendto(PROBE, (target, DISCOVERY_PORT))
        except OSError:
            pass

    mine = set(lan_ips())
    found = {}
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(2048)
        except socket.timeout:
            continue
        except OSError:
            break
        if not data.startswith(REPLY_PREFIX):
            continue
        try:
            info = json.loads(data[len(REPLY_PREFIX):].decode("utf-8"))
        except ValueError:
            continue
        ip = addr[0]
        info["address"] = ip
        info["is_self"] = ip in mine or ip.startswith("127.")
        info["url"] = f"{info.get('scheme', 'http')}://{ip}:{info.get('port', 8000)}"
        found[info["url"]] = info

    sock.close()
    return sorted(found.values(), key=lambda s: (s["is_self"], s["url"]))


def _print_results(servers):
    if not servers:
        print("  Nothing found. Make sure another Sync-Ghar is running")
        print("  (python main.py) and both devices are on the same wifi.")
        return
    print(f"  Found {len(servers)} Sync-Ghar server(s):\n")
    for s in servers:
        tag = "  (this device)" if s.get("is_self") else ""
        print(f"    {s['url']}   - {s.get('name', '?')}{tag}")
    print("\n  Open one of those addresses in a browser.")


if __name__ == "__main__":
    print("Searching the wifi for Sync-Ghar servers ...\n")
    _print_results(discover())
