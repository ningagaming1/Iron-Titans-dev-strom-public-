# archive/

Old code kept for reference. **Not imported by the app. Do not run.**

## adminconnection.py

An earlier, standalone admin/login experiment. It was replaced by
`login2.py` + `signup.py`.

It is dangerous to run now because it uses a **different, incompatible
layout** for `data/users/users.json`:

| file | `adminconnection.py` expects | the live app (`login2.py`) uses |
|------|------------------------------|---------------------------------|
| users.json | `{admins: [], users: {}, signup_requests: {}}` | `{username: {rounds, fib_check, password, ...}}` |
| password | single SHA-256 | SHA-256 iterated `rounds` times + Fibonacci check |

`load_data()` in that file **auto-migrates and overwrites** users.json on
import, which would corrupt the real database. That's why it lives here
and not in the project root.
