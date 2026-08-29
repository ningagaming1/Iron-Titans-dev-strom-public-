import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import login2
import devices
import intent

try:
    import voice                     # offline voice, optional
except Exception:                    # missing dep shouldnt kill the app
    voice = None

# run from anywhere, paths still work
HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")
os.chdir(HERE)

# app.py - the bridge between the web pages and python.
# run:  python app.py   then open  http://localhost:8000

PORT = 8000

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):

    # --- small helpers ---
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _send_static(self, name):
        """Serve a file from web/. Unknown page falls back to login."""
        name = (name or "").lstrip("/") or "index.html"
        full = os.path.normpath(os.path.join(WEB, name))
        if not full.startswith(WEB) or not os.path.isfile(full):
            full = os.path.join(WEB, "index.html")

        ctype = CONTENT_TYPES.get(os.path.splitext(full)[1], "text/plain; charset=utf-8")
        try:
            with open(full, "rb") as f:
                body = f.read()
        except FileNotFoundError:
            self._send_json({"ok": False, "message": name + " not found"}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return {}

    def _read_raw(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def _send_wav(self, wav_bytes):
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(wav_bytes)))
        self._cors()
        self.end_headers()
        self.wfile.write(wav_bytes)

    # --- GET: pages, assets, read-only stuff ---
    def do_GET(self):
        route = self.path.split("?")[0].rstrip("/") or "/"

        if route in ("/", "/index", "/login"):
            self._send_static("index.html")
        elif route in ("/dashboard", "/home"):
            self._send_static("dashboard.html")
        elif route == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        elif route == "/api/config":
            self._send_json({"dev_mode": login2.DEV_MODE})
        elif route == "/api/devices":
            self._send_json({"ok": True, "house": devices.get_state()})
        elif route == "/api/voice/status":
            self._send_json(voice.status() if voice else
                            {"stt": False, "tts": False, "ready": False,
                             "hint": "voice.py failed to import"})
        elif route.startswith("/api/"):
            self._send_json({"ok": False, "message": "unknown endpoint"}, 404)
        else:
            # css / js / html
            self._send_static(route)

    # --- POST: the API ---
    def do_POST(self):
        # /api/voice sends raw audio not json, do it first
        if self.path.split("?")[0] == "/api/voice":
            self._handle_voice()
            return

        data = self._read_body()
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))
        admin = str(data.get("admin", "")).strip()
        who = username or "someone"

        if self.path == "/api/signup":
            ok, message = login2.request_account(username, password)
            self._send_json({"ok": ok, "message": message})

        elif self.path == "/api/login":
            ok, message, user = login2.login(username, password)
            self._send_json({"ok": ok, "message": message, "user": user})

        elif self.path == "/api/session":
            self._send_json({"ok": login2.is_admin(username), "username": username})

        elif self.path == "/api/pending":
            if not login2.is_admin(admin):
                self._send_json({"ok": False, "message": "Not an admin."})
                return
            self._send_json({"ok": True, "pending": login2.list_pending()})

        elif self.path == "/api/approve":
            if not login2.is_admin(admin):
                self._send_json({"ok": False, "message": "Not an admin."})
                return
            ok, message = login2.approve(username, approved_by=admin)
            self._send_json({"ok": ok, "message": message})

        elif self.path == "/api/reject":
            if not login2.is_admin(admin):
                self._send_json({"ok": False, "message": "Not an admin."})
                return
            ok, message = login2.reject(username)
            self._send_json({"ok": ok, "message": message})

        elif self.path == "/api/devmode":
            if not login2.is_admin(admin):
                self._send_json({"ok": False, "message": "Not an admin."})
                return
            on = login2.set_dev_mode(bool(data.get("on")))
            self._send_json({
                "ok": True,
                "dev_mode": on,
                "message": ("Developer mode is ON - new sign-ups log in "
                            "straight away." if on else
                            "Developer mode is OFF - new sign-ups wait for "
                            "admin approval."),
            })

        # --- the house ---
        elif self.path == "/api/devices/set":
            device = str(data.get("device", ""))
            value = data.get("value")
            if device == "all":
                ok, house = devices.all_devices(bool(value), who)
            else:
                ok, house = devices.set_device(device, value, who)
            self._send_json({"ok": ok, "house": house})

        elif self.path == "/api/command":
            # text -> intent -> house
            parsed = intent.parse(str(data.get("text", "")))
            message, house = devices.apply(parsed, who)
            self._send_json({"ok": parsed["ok"], "message": message, "house": house})

        elif self.path == "/api/activity/clear":
            ok, house = devices.clear_activity(who)
            self._send_json({"ok": ok, "house": house})

        elif self.path == "/api/voice/tts":
            text = str(data.get("text", "")).strip()
            if not voice or not voice.status().get("tts"):
                self._send_json({"ok": False, "message": "server TTS not set up"}, 503)
            elif not text:
                self._send_json({"ok": False, "message": "no text"}, 400)
            else:
                try:
                    self._send_wav(voice.synthesize(text))
                except Exception as e:
                    self._send_json({"ok": False, "message": str(e)}, 500)

        else:
            self._send_json({"ok": False, "message": "unknown endpoint"}, 404)

    # --- voice: mic -> text -> house -> spoken reply ---
    def _handle_voice(self):
        raw = self._read_raw()
        from urllib.parse import parse_qs, urlparse
        qs = parse_qs(urlparse(self.path).query)
        who = (qs.get("user", [""])[0]).strip() or "someone"
        if not voice or not voice.status().get("stt"):
            self._send_json({"ok": False, "offline": True,
                             "message": "server voice not set up - run voice_setup.py"}, 503)
            return
        if not raw:
            self._send_json({"ok": False, "message": "empty audio"}, 400)
            return
        try:
            result = voice.handle(raw, who)
        except Exception as e:
            self._send_json({"ok": False, "message": str(e)}, 500)
            return

        wav = result.pop("audio_wav", None)
        if wav:
            import base64
            result["audio_b64"] = base64.b64encode(wav).decode("ascii")
        self._send_json(result)

    def log_message(self, fmt, *args):
        print("  ", self.command, self.path.split("?")[0])


def serve(port=PORT):
    """Start the server, block till Ctrl+C. Used by app.py and main.py."""
    try:
        server = ThreadingHTTPServer(("", port), Handler)
    except OSError as e:
        print(f"\nCould not start on port {port}: {e}")
        print("Another copy of the server is probably already running.")
        print(f"Close it (or run: pkill -f app.py) and try again.\n")
        raise SystemExit(1)

    print("=" * 48)
    print("  SmartHome is running.")
    print(f"  Open this in your browser:  http://localhost:{port}")
    print("  Keep this window OPEN. Press Ctrl+C to stop.")
    print("  (voice uses the browser's own speech engine - Chrome or Edge)")
    print("=" * 48 + "\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
