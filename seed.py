import json

import login2
import devices
from signup import password_funct

# seed.py - start from scratch.
# run `python seed.py` for a clean slate: empties the dbs and makes one
# starter admin (admin / admin123) so someone can log in and approve
# the rest. change these before the demo if you want.

FIRST_ADMIN = "admin"
FIRST_PASSWORD = "admin123"


def main():
    # empty the user dbs
    login2._save(login2.PENDING_FILE, {})

    rounds, fib_check, password_hash = password_funct(FIRST_PASSWORD)
    login2._save(login2.USERS_FILE, {
        FIRST_ADMIN: {
            "username": FIRST_ADMIN,
            "rounds": rounds,
            "fib_check": fib_check,
            "password": password_hash,
            "is_locked": False,
            "failed_attempts": 0,
            "approved_by": "system",
            "approved_at": login2._now(),
        }
    })

    # reset the house (all off, door locked, no history)
    devices.reset()

    print("Databases reset.")
    print(f"Starter admin -> username: {FIRST_ADMIN}  password: {FIRST_PASSWORD}")


if __name__ == "__main__":
    main()
