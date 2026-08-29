import hashlib
import random

# =============================================================
#  signup.py  ->  "the password scrambler"
# -------------------------------------------------------------
#  This file has ONE job: turn a real password into something
#  safe to store in our database. We never save the real
#  password, only the scrambled version.
#
#  You (programmer) wrote password_funct().
#  I (data science engineer) added password_matches() next to
#  it and fixed two small bugs. See the notes below.
# =============================================================


def password_funct(user_password, rounds=None):
    """
    Scramble a password.

    Steps:
      1. Pick a number of "rounds". On signup we pick a random
         number. When we later CHECK a login we pass the same
         number back in, so we get the same result.
      2. Run SHA-256 on the password that many times in a row.
      3. As a small extra fingerprint, also hash the matching
         Fibonacci number.

    Returns a tuple: (rounds, fib_check, password_hash)
    The caller saves all three values in the database.

    ---- notes on the two fixes (data eng) ----
    * The old code did `fib_no.encode()` but fib_no is a number,
      and numbers have no .encode(). Wrapped it in str() -> str(fib_no).
    * The old code picked `rounds` randomly and never saved it,
      so the SAME password scrambled differently every time and
      login could never match. Now `rounds` is saved with the
      user (think of it like a per-user salt).
    """
    if rounds is None:
        rounds = random.randint(4, 100)

    password = user_password
    for _ in range(rounds):
        password = hashlib.sha256(password.encode()).hexdigest()

    # walk the Fibonacci sequence `rounds` steps
    a, b = 1, 1
    for _ in range(rounds - 1):
        a, b = b, a + b
    fib_no = a
    fib_check = hashlib.sha256(str(fib_no).encode()).hexdigest()

    return (rounds, fib_check, password)


def password_matches(typed_password, rounds, fib_check, password_hash):
    """
    Check a password typed at login against what we stored.

    We re-run password_funct with the SAME rounds number that we
    saved for this user. If both fingerprints come out equal, the
    password is correct.
    """
    _, check_again, hash_again = password_funct(typed_password, rounds)
    return (check_again == fib_check) and (hash_again == password_hash)


def signup():
    """
    Small command-line helper so `python signup.py` still works.
    A new signup does NOT create a real account straight away -
    it creates a REQUEST that an admin has to approve first.
    The actual saving lives in login2.py (our main system).
    """
    # imported here (not at the top) so the two files don't
    # import each other in a loop.
    from login2 import request_account

    print("\n=== REQUEST AN ACCOUNT ===")
    username = input("Username: ").lower().strip()
    if not username:
        print("Username cannot be empty")
        return

    password = input("Password: ")
    confirm = input("Confirm password: ")
    if password != confirm:
        print("Passwords do not match")
        return

    ok, message = request_account(username, password)
    print(message)


if __name__ == "__main__":
    signup()
