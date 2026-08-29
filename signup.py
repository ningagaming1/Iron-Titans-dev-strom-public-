import hashlib
import random

# signup.py - the password scrambler.
# one job: turn a real password into something safe to store. we never
# save the real password, only the scrambled version.


def password_funct(user_password, rounds=None):
    """
    Scramble a password.

    Pick a number of rounds (random on signup, passed back in on login
    so the result matches), SHA-256 the password that many times, and
    also hash the matching Fibonacci number as an extra fingerprint.

    Returns (rounds, fib_check, password_hash) - caller saves all three.
    `rounds` acts like a per-user salt.
    """
    if rounds is None:
        rounds = random.randint(4, 100)

    password = user_password
    for _ in range(rounds):
        password = hashlib.sha256(password.encode()).hexdigest()

    # walk the fibonacci sequence `rounds` steps
    a, b = 1, 1
    for _ in range(rounds - 1):
        a, b = b, a + b
    fib_no = a
    fib_check = hashlib.sha256(str(fib_no).encode()).hexdigest()

    return (rounds, fib_check, password)


def password_matches(typed_password, rounds, fib_check, password_hash):
    """
    Re-run password_funct with the saved rounds. If both fingerprints
    match, the typed password is correct.
    """
    _, check_again, hash_again = password_funct(typed_password, rounds)
    return (check_again == fib_check) and (hash_again == password_hash)


def signup():
    """
    CLI helper so `python signup.py` still works. A signup doesnt make
    a real account - it makes a request an admin approves. Actual
    saving lives in login2.py.
    """
    # imported here, not at top, to dodge a circular import
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
