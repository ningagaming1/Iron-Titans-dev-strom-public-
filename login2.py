import json
import os
from datetime import datetime, timezone

from signup import password_funct, password_matches

# =============================================================
#  login2.py  ->  "the login + approval system"
# -------------------------------------------------------------
#  TWO databases (just two JSON files):
#
#    data/users/pending.json  -> people who signed up and are
#                                WAITING for an admin to approve
#                                them. They CANNOT log in yet.
#
#    data/users/users.json    -> approved people. In this project
#                                every approved person is also an
#                                admin, so being in this file means
#                                "you can log in AND you can approve
#                                other people".
#
#  Flow:  request_account()  -> writes into pending.json
#         approve(username)   -> moves the record pending -> users
#         login()             -> only checks users.json
#
#  Notes between the two of us are marked "you:" (programmer)
#  and "me:" (data science engineer).
# =============================================================

DATA_DIR = os.path.join("data", "users")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
PENDING_FILE = os.path.join(DATA_DIR, "pending.json")

# how many wrong passwords before we lock an account
MAX_TRIES = 5

# DEVELOPER MODE
# --------------
# While True: a new account skips the waiting list and can log in
# straight away (no admin approval needed). Handy while we build.
# Flip to False for the "real" behaviour before the final demo.
DEV_MODE = True


def _safe(user):
    """A copy of a user record with the secret bits removed."""
    hidden = ("password", "fib_check", "rounds")
    clean = {k: v for k, v in user.items() if k not in hidden}
    clean["is_admin"] = True          # every approved user is an admin
    return clean


# -------------------------------------------------------------
#  tiny storage helpers (read / write a JSON file safely)
# -------------------------------------------------------------
def _now():
    """Current time as a plain text string, e.g. 2026-08-29T10:30:00+00:00."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load(path):
    """
    Read a JSON file and return a dict.
    If the file is missing or broken, return an empty dict instead
    of crashing - handy on the very first run.
    """
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(path, data):
    """Write a dict back to a JSON file, nicely indented."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def load_users():
    return _load(USERS_FILE)


def load_pending():
    return _load(PENDING_FILE)


# -------------------------------------------------------------
#  1. SIGNUP  ->  create a pending request
# -------------------------------------------------------------
def request_account(username, password):
    """
    Save a signup request into pending.json.

    Returns (ok, message) so the website / CLI can show the message.

    me (data eng): I'm scrambling the password RIGHT HERE using
    your password_funct(). That way the real password never even
    reaches the database file, not even in the waiting list.
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

    # DEV_MODE: don't bother with the waiting list, make the account now.
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


# -------------------------------------------------------------
#  2. ADMIN  ->  see / approve / reject requests
# -------------------------------------------------------------
def list_pending():
    """Return the list of usernames currently waiting for approval."""
    return list(load_pending().keys())


def approve(username, approved_by="admin"):
    """
    Move one person from pending.json into users.json.
    After this they can log in, and they are also an admin.
    """
    username = username.lower().strip()

    pending = load_pending()
    users = load_users()

    if username not in pending:
        return False, "No pending request with that username."

    record = pending.pop(username)          # take it out of the waiting list

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
    """Every approved user is an admin, so this just checks users.json."""
    return username.lower().strip() in load_users()


# -------------------------------------------------------------
#  3. LOGIN
# -------------------------------------------------------------
def login(username, password):
    """
    Try to log a person in.

    Returns (ok, message, user).
      ok      -> True / False
      message -> text to show the user
      user    -> the user's record (without the password) when ok,
                 otherwise None

    Rules:
      * unknown username            -> fail
      * still waiting for approval  -> fail (tell them to wait)
      * account locked              -> fail, UNLESS the password given
                                       is the stored recovery hash
      * wrong password              -> fail, count the miss,
                                       lock after MAX_TRIES misses
      * correct password            -> success; always reset the miss
                                       counter and clear the lock
    """
    username = username.lower().strip()

    users = load_users()
    pending = load_pending()

    # not approved yet?
    if username in pending:
        return False, "Your account is still waiting for admin approval.", None

    # never heard of them
    if username not in users:
        return False, "Wrong username or password.", None

    user = users[username]

    # locked from too many wrong tries
    if user.get("is_locked", False):
        # RECOVERY KEY: if you paste the stored password hash from
        # users.json as the password, we accept it and unlock the
        # account. It's a convenience for our build - it is NOT a
        # real security feature, since anyone who can read the file
        # can get in. Fine for a local hackathon toy.
        if password == user["password"]:
            user["is_locked"] = False
            user["failed_attempts"] = 0
            user["last_login"] = _now()
            _save(USERS_FILE, users)
            return True, f"Unlocked with the recovery hash. Welcome back, {username}!", _safe(user)

        return False, ("This account is locked. Paste the recovery hash from "
                       "users.json as the password, or ask an admin to unlock it."), None

    # the real check - re-scramble what they typed and compare
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

    # success - always clear the miss counter, note the time, hand back
    # a safe copy (no password / hash bits).
    user["failed_attempts"] = 0
    user["is_locked"] = False
    user["last_login"] = _now()
    _save(USERS_FILE, users)

    return True, f"Welcome back, {username}!", _safe(user)


def unlock(username):
    """Admin helper: unlock an account and reset its miss counter."""
    username = username.lower().strip()
    users = load_users()
    if username not in users:
        return False, "No such user."
    users[username]["is_locked"] = False
    users[username]["failed_attempts"] = 0
    _save(USERS_FILE, users)
    return True, f"'{username}' is unlocked."


# -------------------------------------------------------------
#  4. a small text menu so you can try it without the website
# -------------------------------------------------------------
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
            # only an already-approved admin should do this
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
