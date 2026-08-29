"""
main.py - one command to run the whole thing.

    python main.py            start everything (seeds on first run)
    python main.py --reset    wipe the dbs, reseed, then start
    python main.py --check    run self-tests and exit, no server
    python main.py --port 9000
    python main.py --https    serve over https so other wifi devices
                              can use the mic (needs the openssl command)
    python main.py --find     search the wifi for a running Sync-Ghar
                              and print its address, then exit
    python main.py --debug    show full tracebacks

Order: check python + files, seed an admin if there's none,
self-test every module, start the server.

The server always listens on every network interface, so other
devices on the same wifi can open it at http://<this-machine-ip>:8000
(the address is printed on startup). It also runs a small discovery
beacon so `python main.py --find` on another machine can locate it.

Starter admin -> username: admin  password: admin123
"""

import argparse
import contextlib
import os
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)                       # run from anywhere
sys.path.insert(0, HERE)

MIN_PYTHON = (3, 7)


def _use_voice_venv():
    """
    If ./.venv has the voice packages, re-exec into it so plain
    `python main.py` gets real speech instead of the browser fallback.
    """
    if os.environ.get("SMARTHOME_NO_REEXEC"):
        return
    try:
        import vosk, piper           # noqa: F401  - already fine, stay
        return
    except ImportError:
        pass

    import subprocess
    for cand in (os.path.join(HERE, ".venv", "bin", "python"),
                 os.path.join(HERE, "venv", "bin", "python")):
        if not os.path.isfile(cand):
            continue
        probe = subprocess.run([cand, "-c", "import vosk, piper"],
                               capture_output=True)
        if probe.returncode == 0:
            print(f"[main] using {os.path.relpath(cand, HERE)} for offline voice\n",
                  flush=True)
            os.environ["SMARTHOME_NO_REEXEC"] = "1"
            os.execv(cand, [cand, *sys.argv])
    # no venv - carry on, voice uses the browser engine


_use_voice_venv()


# --- small helpers ---
def line(title=""):
    print(("--- " + title + " ").ljust(60, "-") if title else "-" * 60)


def die(message, code=1):
    print("\n[stop] " + message + "\n")
    raise SystemExit(code)


@contextlib.contextmanager
def sandboxed_data():
    """
    Point the modules at a throwaway copy of data/ for the duration,
    so self-tests never touch the real dbs. Puts the paths back after.
    """
    import login2
    import devices

    tmp = tempfile.mkdtemp(prefix="smarthome-selftest-")
    try:
        real = os.path.join(HERE, "data")
        if os.path.isdir(real):
            shutil.copytree(real, os.path.join(tmp, "data"))

        saved = (login2.DATA_DIR, login2.USERS_FILE, login2.PENDING_FILE,
                 devices.DEVICES_FILE)
        login2.DATA_DIR = os.path.join(tmp, "data", "users")
        login2.USERS_FILE = os.path.join(login2.DATA_DIR, "users.json")
        login2.PENDING_FILE = os.path.join(login2.DATA_DIR, "pending.json")
        devices.DEVICES_FILE = os.path.join(tmp, "data", "devices.json")
        os.makedirs(login2.DATA_DIR, exist_ok=True)
        try:
            yield
        finally:
            (login2.DATA_DIR, login2.USERS_FILE, login2.PENDING_FILE,
             devices.DEVICES_FILE) = saved
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- 1. environment checks ---
def check_environment():
    line("environment")
    if sys.version_info < MIN_PYTHON:
        die(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required, "
            f"this is {sys.version.split()[0]}.")
    print(f"  python {sys.version.split()[0]}  ok")

    needed = ["app.py", "login2.py", "signup.py", "devices.py",
              "intent.py", "seed.py", "web"]
    missing = [n for n in needed if not os.path.exists(os.path.join(HERE, n))]
    if missing:
        die("missing project files: " + ", ".join(missing))
    print(f"  project files  ok ({len(needed)} checked)")

    for page in ("index.html", "dashboard.html", "style.css", "auth.js", "dashboard.js"):
        if not os.path.isfile(os.path.join(HERE, "web", page)):
            die(f"web/{page} is missing - the browser side won't load.")
    print("  web/ assets  ok")


# --- 2. database: seed only if empty ---
def ensure_database(force_reset=False):
    line("database")
    import login2
    import seed

    os.makedirs(login2.DATA_DIR, exist_ok=True)

    print(f"  developer mode: {'ON (sign-ups auto-approved)' if login2.DEV_MODE else 'OFF (sign-ups need admin approval)'}"
          f" - toggle it on the Invites tab")

    users = login2.load_users()
    if force_reset:
        print("  --reset given: wiping and reseeding")
        seed.main()
        return

    if not users:
        print("  no accounts found - seeding a starter admin")
        seed.main()
        return

    print(f"  {len(users)} account(s) already present - leaving them alone")
    if "admin" not in users:
        print("  note: no 'admin' account (that's fine if you renamed it)")


# --- 3. self-test every module ---
def self_test():
    line("self-test")
    failures = []

    def ok(name):
        print(f"  [ok]   {name}")

    def bad(name, err):
        print(f"  [FAIL] {name}: {err}")
        failures.append(name)

    # imports
    try:
        import app, login2, signup, devices, intent, seed  # noqa: F401
        ok("import all modules")
    except Exception as e:
        bad("import all modules", e)
        return failures            # nothing else will work anyway

    with sandboxed_data():
        _run_checks(ok, bad)
    return failures


def _run_checks(ok, bad):
    import login2, signup, devices, intent

    # password scramble round-trips
    try:
        rounds, fib_check, pw_hash = signup.password_funct("hunter2")
        assert signup.password_matches("hunter2", rounds, fib_check, pw_hash)
        assert not signup.password_matches("wrong", rounds, fib_check, pw_hash)
        ok("signup.password_funct / password_matches")
    except Exception as e:
        bad("signup password round-trip", e)

    # intent parsing
    try:
        cases = {
            "turn on the light": ("on", ["light"]),
            "switch off the fan": ("off", ["fan"]),
            "open the door": ("unlock", ["door"]),
            "lock the door": ("lock", ["door"]),
            "turn on everything": ("on", ["light", "fan"]),
        }
        for text, (action, targets) in cases.items():
            r = intent.parse(text)
            assert r["ok"], f"{text!r} -> not ok"
            assert r["action"] == action, f"{text!r} -> {r['action']} != {action}"
            assert r["targets"] == targets, f"{text!r} -> {r['targets']} != {targets}"
        assert intent.parse("")["ok"] is False
        assert intent.parse("banana")["ok"] is False
        ok(f"intent.parse ({len(cases)} phrases + 2 rejects)")
    except Exception as e:
        bad("intent.parse", e)

    # devices: apply an intent, flip the door (on the sandbox)
    try:
        _, house = devices.apply(intent.parse("turn on the light"), "self-test")
        assert house["light"] is True
        _, house = devices.apply(intent.parse("turn off the light"), "self-test")
        assert house["light"] is False
        devices.set_device("door", False, "self-test")
        assert devices.get_state()["door_locked"] is False
        devices.set_device("door", True, "self-test")
        assert devices.get_state()["door_locked"] is True
        ok("devices.apply / set_device round-trip")
    except Exception as e:
        bad("devices round-trip", e)

    # devices: add a dimmer, drive it, remove it
    try:
        made, _, _ = devices.add_device(
            {"name": "Patio Glow", "room": "Patio", "type": "dimmer", "icon": "*"},
            "self-test")
        assert made
        new_id = devices.list_devices()[-1]["id"]
        devices.set_device(new_id, 40, "self-test")
        assert devices.list_devices()[-1]["level"] == 40
        devices.apply(
            intent.parse("dim the patio glow to 10", devices.catalog()), "self-test")
        assert devices.list_devices()[-1]["level"] == 10
        gone, _, _ = devices.remove_device(new_id, "self-test")
        assert gone
        assert devices.remove_device("light", "self-test")[0] is False   # builtin
        ok("devices.add_device / dimmer / remove_device")
    except Exception as e:
        bad("devices add/remove", e)

    # login: request -> approve if needed -> login
    # works with dev mode on or off
    try:
        made, _ = login2.request_account("selftester", "pw123456")
        assert made
        if "selftester" in login2.load_pending():
            login2.approve("selftester", approved_by="self-test")
        got, message, _ = login2.login("selftester", "pw123456")
        assert got, message
        bad_try = login2.login("selftester", "nope")[0]
        assert bad_try is False
        ok("login2.request_account / approve / login")
    except Exception as e:
        bad("login2.login", e)

    # login cooldown: a wrong password makes you sit out a wait
    try:
        login2.request_account("cooldowner", "pw123456")
        if "cooldowner" in login2.load_pending():
            login2.approve("cooldowner", approved_by="self-test")
        saved = login2.LOGIN_COOLDOWN
        login2.LOGIN_COOLDOWN = 30
        try:
            assert login2.login("cooldowner", "nope")[0] is False
            assert login2.seconds_until_retry("cooldowner") > 0
            # even the right password is refused until the wait is over
            assert login2.login("cooldowner", "pw123456")[0] is False
        finally:
            login2.LOGIN_COOLDOWN = saved
        login2.unlock("cooldowner")
        assert login2.seconds_until_retry("cooldowner") == 0
        ok("login2 cooldown after a wrong password")
    except Exception as e:
        bad("login2 cooldown", e)


# --- put it together ---
def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Run the whole Sync-Ghar project with one command.")
    parser.add_argument("--port", type=int, default=8000,
                        help="port for the web server (default 8000)")
    parser.add_argument("--reset", action="store_true",
                        help="wipe the databases and reseed before starting")
    parser.add_argument("--check", action="store_true",
                        help="run the self-tests and exit, don't start the server")
    parser.add_argument("--debug", action="store_true",
                        help="show full tracebacks on error")
    parser.add_argument("--https", action="store_true",
                        help="serve over https (self-signed cert) so other "
                             "devices on the wifi can use the mic too")
    parser.add_argument("--find", action="store_true",
                        help="search the wifi for a running Sync-Ghar server "
                             "and print its address, then exit")
    parser.add_argument("--no-discovery", action="store_true",
                        help="don't run the discovery beacon (--find won't see this one)")
    args = parser.parse_args(argv)

    if args.find:
        import discovery
        print("\nSearching the wifi for Sync-Ghar servers ...\n")
        discovery._print_results(discovery.discover())
        raise SystemExit(0)

    print()
    line("Sync-Ghar - main.py")

    try:
        check_environment()
        ensure_database(force_reset=args.reset)
        failures = self_test()
    except SystemExit:
        raise
    except Exception as e:
        if args.debug:
            traceback.print_exc()
        die(f"startup failed: {e}")

    line("result")
    if failures:
        print(f"  {len(failures)} self-test(s) FAILED: {', '.join(failures)}")
        if not args.check:
            print("  starting the server anyway - fix the above if something misbehaves")
    else:
        print("  all self-tests passed")

    if args.check:
        line()
        raise SystemExit(1 if failures else 0)

    line("starting server")
    import app
    app.serve(port=args.port, https=args.https, discovery=not args.no_discovery)


if __name__ == "__main__":
    main()
