import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import login2
import devices
import intent
import voice

# folder this file lives in - so it works no matter which
# directory you run "python app.py" from
HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")           # all the html / css / js lives here
os.chdir(HERE)

# =============================================================
#  app.py  ->  "the bridge between the web pages and Python"
# -------------------------------------------------------------
#  Run:   python app.py     then open  http://localhost:8000
#
#  Pages come from the  web/  folder.
#
#  API:
#    POST /api/signup        {username, password}
#    POST /api/login         {username, password}
#    POST /api/session       {username}            -> account still exists?
#    POST /api/pending       {admin}
#    POST /api/approve       {admin, username}
#    POST /api/reject        {admin, username}
#    GET  /api/config                              -> {dev_mode, voice}
#    GET  /api/devices                             -> the whole house
#    POST /api/devices/set   {username, device, value}
#    POST /api/command       {username, text}      -> text -> intent -> house
#    POST /api/voice         {username, audio}     -> audio -> Google -> intent
#    POST /api/activity/clear {username}
# =============================================================

PORT = 8000

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):

    # ---- low-level helpers ------------------------------------
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
        """Serve a file from web/. Unknown page -> the login page."""
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

    # ---- GET: pages, assets, read-only data ------------------
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
            self._send_json({"dev_mode": login2.DEV_MODE, "voice": voice.has_key()})
        elif route == "/api/devices":
            self._send_json({"ok": True, "house": devices.get_state()})
        elif route.startswith("/api/"):
            self._send_json({"ok": False, "message": "unknown endpoint"}, 404)
        else:
            # /style.css, /auth.js, /dashboard.js, /index.html, ...
            self._send_static(route)

    # ---- POST: the API --------------------------------------
    def do_POST(self):
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

        # ---- the house ----
        elif self.path == "/api/devices/set":
            device = str(data.get("device", ""))
            value = data.get("value")
            if device == "all":
                ok, house = devices.all_devices(bool(value), who)
            else:
                ok, house = devices.set_device(device, value, who)
            self._send_json({"ok": ok, "house": house})

        elif self.path == "/api/command":
            # typed text  ->  intent  ->  house
            parsed = intent.parse(str(data.get("text", "")))
            message, house = devices.apply(parsed, who)
            self._send_json({"ok": parsed["ok"], "message": message, "house": house})

        elif self.path == "/api/voice":
            # audio clip  ->  Google Speech-to-Text  ->  intent  ->  house
            ok, text = voice.transcribe(str(data.get("audio", "")))
            if not ok:
                self._send_json({
                    "ok": False,
                    "need_key": (text == "no-key"),
                    "message": ("No Google API key set on the server."
                                if text == "no-key" else text),
                    "house": devices.get_state(),
                })
                return
            parsed = intent.parse(text)
            message, house = devices.apply(parsed, who)
            self._send_json({"ok": True, "heard": text, "message": message, "house": house})

        elif self.path == "/api/activity/clear":
            ok, house = devices.clear_activity(who)
            self._send_json({"ok": ok, "house": house})

        else:
            self._send_json({"ok": False, "message": "unknown endpoint"}, 404)

    def log_message(self, fmt, *args):
        print("  ", self.command, self.path.split("?")[0])


def serve(port=PORT):
    """Start the web server and block until Ctrl+C. Used by app.py and main.py."""
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
    if not voice.has_key():
        print("  (voice: no GOOGLE_API_KEY - the page will use the")
        print("   browser's speech engine instead)")
    print("=" * 48 + "\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
