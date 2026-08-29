import json
import os
from datetime import datetime, timezone

from signup import password_funct, password_matches

# login2.py - login + approval.
# two json files: pending.json (signed up, waiting for an admin, cant
# log in yet) and users.json (approved, and every approved user is also
# an admin). request_account() writes pending, approve() moves it to
# users, login() only checks users.

DATA_DIR = os.path.join("data", "users")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
PENDING_FILE = os.path.join(DATA_DIR, "pending.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

# wrong passwords before an account locks
MAX_TRIES = 5

# dev mode: True = new accounts skip the waiting list and can log in
# right away. handy while building. initial value from SMARTHOME_DEV_MODE
# env var, else settings.json, else the default. an admin can flip it at
# runtime (Invites tab / POST /api/devmode) and set_dev_mode() saves it.
DEV_MODE_DEFAULT = False


def _read_dev_mode():
    env = os.environ.get("SMARTHOME_DEV_MODE")
    if env is not None:
        return env.strip().lower() in ("1", "true", "yes", "on")
    return bool(_load(SETTINGS_FILE).get("dev_mode", DEV_MODE_DEFAULT))


def set_dev_mode(on):
    """Flip developer mode on/off at runtime and remember it in settings.json."""
    global DEV_MODE
    DEV_MODE = bool(on)
    settings = _load(SETTINGS_FILE)
    settings["dev_mode"] = DEV_MODE
    _save(SETTINGS_FILE, settings)
    return DEV_MODE


def _safe(user):
    """A copy of a user record without the secret bits."""
    hidden = ("password", "fib_check", "rounds")
    clean = {k: v for k, v in user.items() if k not in hidden}
    clean["is_admin"] = True          # every approved user is an admin
    return clean


# --- storage helpers ---
def _now():
    """Now as text, e.g. 2026-08-29T10:30:00+00:00."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load(path):
    """Read a JSON file -> dict. Missing or broken -> empty dict."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(path, data):
    """Write a dict to a JSON file."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def load_users():
    return _load(USERS_FILE)


def load_pending():
    return _load(PENDING_FILE)


# read the remembered / env value now that the helpers exist
DEV_MODE = _read_dev_mode()


# --- 1. signup -> a pending request ---
def request_account(username, password):
    """
    Save a signup request into pending.json. Returns (ok, message).

    Password is scrambled here, so the real one never hits any file,
    not even the waiting list.
    """
    username = username.lower().strip()

    if not username or not password:
        return False, "Username and password are required."

    users = load_users()
    pending = load_pending()

    if username in users:
        return False, "That username is already taken."
    if username in pending:
        return False, "You already have a request waiting for approval."

    rounds, fib_check, password_hash = password_funct(password)

    # dev mode: skip the waiting list, make the account now
    if DEV_MODE:
        users[username] = {
            "username": username,
            "rounds": rounds,
            "fib_check": fib_check,
            "password": password_hash,
            "is_locked": False,
            "failed_attempts": 0,
            "approved_by": "dev-mode",
            "approved_at": _now(),
        }
        _save(USERS_FILE, users)
        return True, "Dev mode is on - account created. You can log in right away."

    pending[username] = {
        "username": username,
        "rounds": rounds,
        "fib_check": fib_check,
        "password": password_hash,
        "requested_at": _now(),
    }
    _save(PENDING_FILE, pending)

    return True, "Request sent. An admin has to approve you before you can log in."


# --- 2. admin: see / approve / reject requests ---
def list_pending():
    """Return the list of usernames currently waiting for approval."""
    return list(load_pending().keys())


def approve(username, approved_by="admin"):
    """Move one person from pending.json to users.json. Now they can log in."""
    username = username.lower().strip()

    pending = load_pending()
    users = load_users()

    if username not in pending:
        return False, "No pending request with that username."

    record = pending.pop(username)          # off the waiting list

    users[username] = {
        "username": username,
        "rounds": record["rounds"],
        "fib_check": record["fib_check"],
        "password": record["password"],
        "is_locked": False,
        "failed_attempts": 0,
        "approved_by": approved_by,
        "approved_at": _now(),
    }

    _save(USERS_FILE, users)
    _save(PENDING_FILE, pending)
    return True, f"'{username}' is approved and can log in now."


def reject(username):
    """Throw away a pending request."""
    username = username.lower().strip()
    pending = load_pending()

    if username not in pending:
        return False, "No pending request with that username."

    pending.pop(username)
    _save(PENDING_FILE, pending)
    return True, f"Request from '{username}' was rejected."


def is_admin(username):
    """Every approved user is an admin, so just check users.json."""
    return username.lower().strip() in load_users()


# --- 3. login ---
def login(username, password):
    """
    Try to log a person in. Returns (ok, message, user), user is None
    on failure and has no password bits on success.

    unknown or still-pending -> fail. locked -> fail unless the password
    is the stored recovery hash. wrong password -> counts a miss, locks
    after MAX_TRIES. right password -> clears the counter and the lock.
    """
    username = username.lower().strip()

    users = load_users()
    pending = load_pending()

    if username in pending:
        return False, "Your account is still waiting for admin approval.", None

    if username not in users:
        return False, "Wrong username or password.", None

    user = users[username]

    # locked from too many wrong tries
    if user.get("is_locked", False):
        # recovery key: paste the stored password hash from users.json
        # as the password to unlock. just a build convenience, not real
        # security - anyone who can read the file gets in. fine for a toy.
        if password == user["password"]:
            user["is_locked"] = False
            user["failed_attempts"] = 0
            user["last_login"] = _now()
            _save(USERS_FILE, users)
            return True, f"Unlocked with the recovery hash. Welcome back, {username}!", _safe(user)

        return False, ("This account is locked. Paste the recovery hash from "
                       "users.json as the password, or ask an admin to unlock it."), None

    # re-scramble what they typed and compare
    ok = password_matches(
        password,
        user["rounds"],
        user["fib_check"],
        user["password"],
    )

    if not ok:
        user["failed_attempts"] = user.get("failed_attempts", 0) + 1
        tries_left = MAX_TRIES - user["failed_attempts"]

        if tries_left <= 0:
            user["is_locked"] = True
            _save(USERS_FILE, users)
            return False, "Too many wrong tries. Account locked.", None

        _save(USERS_FILE, users)
        return False, f"Wrong password. {tries_left} tries left.", None

    # success - clear the counter, note the time, hand back a safe copy
    user["failed_attempts"] = 0
    user["is_locked"] = False
    user["last_login"] = _now()
    _save(USERS_FILE, users)

    return True, f"Welcome back, {username}!", _safe(user)


def unlock(username):
    """Admin helper: unlock an account, reset its miss counter."""
    username = username.lower().strip()
    users = load_users()
    if username not in users:
        return False, "No such user."
    users[username]["is_locked"] = False
    users[username]["failed_attempts"] = 0
    _save(USERS_FILE, users)
    return True, f"'{username}' is unlocked."


# --- 4. tiny text menu, to try it without the website ---
def main():
    while True:
        print("\n==== SMARTHOME ====")
        print("1. Request an account")
        print("2. Log in")
        print("3. (admin) see pending requests")
        print("4. (admin) approve someone")
        print("5. (admin) reject someone")
        print("0. Quit")

        choice = input("Pick: ").strip()

        if choice == "1":
            u = input("Username: ")
            p = input("Password: ")
            print(request_account(u, p)[1])

        elif choice == "2":
            u = input("Username: ")
            p = input("Password: ")
            ok, message, user = login(u, p)
            print(message)
            if ok:
                print("Logged in as:", user["username"], "(admin)")

        elif choice == "3":
            waiting = list_pending()
            print("Waiting for approval:", ", ".join(waiting) if waiting else "(nobody)")

        elif choice == "4":
            # only an approved admin should do this
            admin = input("Your (admin) username: ")
            if not is_admin(admin):
                print("You are not an admin.")
                continue
            print("Waiting:", ", ".join(list_pending()) or "(nobody)")
            who = input("Approve who? ")
            print(approve(who, approved_by=admin)[1])

        elif choice == "5":
            admin = input("Your (admin) username: ")
            if not is_admin(admin):
                print("You are not an admin.")
                continue
            who = input("Reject who? ")
            print(reject(who)[1])

        elif choice == "0":
            print("Bye")
            break

        else:
            print("Not an option.")


if __name__ == "__main__":
    main()
