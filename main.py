"""
main.py  ->  one command to run the whole SmartHome project

    python main.py            start everything (seeds on first run)
    python main.py --reset     wipe the databases, reseed, then start
    python main.py --check     run the self-tests and exit (no server)
    python main.py --port 9000 use a different port
    python main.py --debug     print tracebacks instead of a short message

What it does, in order:
    1. sanity-check the Python version and the project layout
    2. make sure data/ exists and, if there is no admin yet, seed one
    3. run a quick self-test over every module (the "debug everything" part)
    4. start the web server (same one as app.py)

Starter admin  ->  username: admin   password: admin123
"""

import argparse
import contextlib
import os
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)                       # run from anywhere, behave the same
sys.path.insert(0, HERE)

MIN_PYTHON = (3, 7)


# -------------------------------------------------------------------
#  small helpers
# -------------------------------------------------------------------
def line(title=""):
    print(("--- " + title + " ").ljust(60, "-") if title else "-" * 60)


def die(message, code=1):
    print("\n[stop] " + message + "\n")
    raise SystemExit(code)


@contextlib.contextmanager
def sandboxed_data():
    """
    Run the block against a throwaway COPY of data/ so the self-test never
    touches the real databases. Repoints the file paths inside each module,
    then puts them back.
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


# -------------------------------------------------------------------
#  1. environment checks
# -------------------------------------------------------------------
def check_environment():
    line("environment")
    if sys.version_info < MIN_PYTHON:
        die(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required, "
            f"this is {sys.version.split()[0]}.")
    print(f"  python {sys.version.split()[0]}  ok")

    needed = ["app.py", "login2.py", "signup.py", "devices.py",
              "intent.py", "voice.py", "seed.py", "web"]
    missing = [n for n in needed if not os.path.exists(os.path.join(HERE, n))]
    if missing:
        die("missing project files: " + ", ".join(missing))
    print(f"  project files  ok ({len(needed)} checked)")

    for page in ("index.html", "dashboard.html", "style.css", "auth.js", "dashboard.js"):
        if not os.path.isfile(os.path.join(HERE, "web", page)):
            die(f"web/{page} is missing - the browser side won't load.")
    print("  web/ assets  ok")


# -------------------------------------------------------------------
#  2. database: seed only when there is nothing there yet
# -------------------------------------------------------------------
def ensure_database(force_reset=False):
    line("database")
    import login2
    import seed

    os.makedirs(login2.DATA_DIR, exist_ok=True)

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


# -------------------------------------------------------------------
#  3. self-test every module ("debug everything")
# -------------------------------------------------------------------
def self_test():
    line("self-test")
    failures = []

    def ok(name):
        print(f"  [ok]   {name}")

    def bad(name, err):
        print(f"  [FAIL] {name}: {err}")
        failures.append(name)

    # -- imports --
    try:
        import app, login2, signup, devices, intent, voice, seed  # noqa: F401
        ok("import all modules")
    except Exception as e:
        bad("import all modules", e)
        return failures            # nothing else will work

    with sandboxed_data():
        _run_checks(ok, bad)
    return failures


def _run_checks(ok, bad):
    import login2, signup, devices, intent, voice

    # -- password scramble round-trips --
    try:
        rounds, fib_check, pw_hash = signup.password_funct("hunter2")
        assert signup.password_matches("hunter2", rounds, fib_check, pw_hash)
        assert not signup.password_matches("wrong", rounds, fib_check, pw_hash)
        ok("signup.password_funct / password_matches")
    except Exception as e:
        bad("signup password round-trip", e)

    # -- intent parsing --
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

    # -- devices: apply an intent and flip the door (runs on a data sandbox) --
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

    # -- voice: no key -> a clean, non-crashing answer --
    try:
        got, text = voice.transcribe("")
        assert got is False
        ok(f"voice.transcribe (no key -> {text!r})")
    except Exception as e:
        bad("voice.transcribe", e)

    # -- login: request -> login a fresh account on the sandbox --
    try:
        made, _ = login2.request_account("selftester", "pw123456")
        assert made
        got, message, _ = login2.login("selftester", "pw123456")
        assert got, message
        bad_try = login2.login("selftester", "nope")[0]
        assert bad_try is False
        ok("login2.request_account / login")
    except Exception as e:
        bad("login2.login", e)


# -------------------------------------------------------------------
#  put it together
# -------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Run the whole SmartHome project with one command.")
    parser.add_argument("--port", type=int, default=8000,
                        help="port for the web server (default 8000)")
    parser.add_argument("--reset", action="store_true",
                        help="wipe the databases and reseed before starting")
    parser.add_argument("--check", action="store_true",
                        help="run the self-tests and exit, don't start the server")
    parser.add_argument("--debug", action="store_true",
                        help="show full tracebacks on error")
    args = parser.parse_args(argv)

    print()
    line("SmartHome - main.py")

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
    app.serve(port=args.port)


if __name__ == "__main__":
    main()
