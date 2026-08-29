import json
import hashlib
import uuid
import os
from datetime import datetime

data_dir = "data/users"
file_path = os.path.join(data_dir, "users.json")

# data helpers (auto-migrate old format)
def ensure_data_file():
    """Make the data folder + file if they're missing."""
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    if not os.path.exists(file_path):
        initial_data = {
            "admins": [],
            "users": {},
            "signup_requests": {}
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(initial_data, f, indent=4)


def migrate_old_format(data):
    if "admins" in data or "users" in data or "signup_requests" in data:
        return data

    # old format: top-level keys are the user profiles
    old_users = data

    new_data = {
        "admins": [],
        "users": old_users,
        "signup_requests": {}
    }
    return new_data


def load_data():
    # load users.json, migrate the old format if needed
    ensure_data_file()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        raw_data = {
            "admins": [],
            "users": {},
            "signup_requests": {}
        }

    data = migrate_old_format(raw_data)

    # write it back so later loads are already in the new format
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    return data


def save_data(data):
    ensure_data_file()
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def is_admin(data, username: str) -> bool:
    return username in data.get("admins", [])

# signup request flow
def signup_request():
    """New signup -> a pending request. Cant log in till an admin approves."""
    data = load_data()

    print("\n=== SIGNUP REQUEST ===")
    username = input("Username: ").lower().strip()
    if not username:
        print("❌ Username cannot be empty")
        return

    # already a user?
    if username in data.get("users", {}):
        print("❌ Username already exists")
        return

    # already asked?
    if username in data.get("signup_requests", {}):
        print("⚠️ You already have a pending signup request")
        return

    password = input("Password: ")
    confirm = input("Confirm Password: ")

    if password != confirm:
        print("❌ Passwords do not match")
        return

    request_id = str(uuid.uuid4())
    requested_at = datetime.utcnow().isoformat()

    data["signup_requests"][username] = {
        "request_id": request_id,
        "username": username,
        "password_hash": hash_password(password),
        "requested_at": requested_at,
        "status": "pending"
    }

    save_data(data)
    print("✔ Signup request sent. Wait for admin approval.")

# admin login
def admin_login():
    """First run with no admins creates one, otherwise checks user+password."""
    data = load_data()

    print("\n=== ADMIN LOGIN ===")

    # no admins yet -> create the first one
    if not data.get("admins"):
        print("⚠️ No admins exist yet. Creating the first admin.")
        username = input("First admin username: ").lower().strip()
        if not username:
            print("❌ Username cannot be empty")
            return

        password = input("First admin password: ")
        confirm = input("Confirm password: ")
        if password != confirm:
            print("❌ Passwords do not match")
            return

        user_id = str(uuid.uuid4())
        data["users"][username] = {
            "user_id": user_id,
            "username": username,
            "is_locked": False,
            "password": hash_password(password),
            "budget": [],
            "tasks": {},
            "journal": {},
            "contacts": {},
            "grades": []
        }
        data["admins"].append(username)
        save_data(data)
        print(f"✔ Admin '{username}' created. You are now logged in as admin.")
        return username

    # normal admin login
    username = input("Admin username: ").lower().strip()
    password = input("Admin password: ")

    if username not in data.get("users", {}):
        print("❌ Admin not found")
        return None

    user = data["users"][username]
    if user.get("is_locked", False):
        print("❌ This admin account is locked")
        return None

    if user["password"] != hash_password(password):
        print("❌ Incorrect password")
        return None

    if not is_admin(data, username):
        print("❌ This user is not an admin")
        return None

    print(f"✔ Logged in as admin: {username}")
    return username

# admin-only features

def view_pending_requests():
    """List every pending signup request."""
    data = load_data()
    requests = data.get("signup_requests", {})

    print("\n=== PENDING SIGNUP REQUESTS ===")
    pending = [r for r in requests.values() if r.get("status") == "pending"]

    if not pending:
        print("No pending requests.")
        return

    for i, req in enumerate(pending, start=1):
        print(f"{i}. Username: {req['username']}")
        print(f"   Request ID: {req['request_id']}")
        print(f"   Requested at: {req['requested_at']}")
        print(f"   Status: {req['status']}")
        print()


def approve_request(admin_username: str):
    """Approve a request: make a real user, mark the request approved."""
    data = load_data()

    view_pending_requests()

    req_username = input("Enter the username of the request to approve (or empty to cancel): ").lower().strip()
    if not req_username:
        print("Cancelled.")
        return

    requests = data.get("signup_requests", {})
    if req_username not in requests:
        print("❌ Request not found")
        return

    req = requests[req_username]
    if req.get("status") != "pending":
        print(f"⚠️ This request is already {req.get('status')}")
        return

    # turn the pending request into a real user
    user_id = str(uuid.uuid4())
    data["users"][req_username] = {
        "user_id": user_id,
        "username": req_username,
        "is_locked": False,
        "password": req["password_hash"],
        "budget": [],
        "tasks": {},
        "journal": {},
        "contacts": {},
        "grades": []
    }

    # every approved user becomes an admin
    if req_username not in data["admins"]:
        data["admins"].append(req_username)
    del data["signup_requests"][req_username]
    save_data(data)

    # mark the request approved
    req["status"] = "approved"
    req["approved_by"] = admin_username
    req["approved_at"] = datetime.utcnow().isoformat()

    save_data(data)
    print(f"✔ Request for '{req_username}' approved. User can now log in.")


def deny_request(admin_username: str):
    """Deny a pending signup request."""
    data = load_data()

    if not is_admin(data, admin_username):
        print("❌ You are not an admin")
        return

    view_pending_requests()

    req_username = input("Enter the username of the request to deny (or empty to cancel): ").lower().strip()
    if not req_username:
        print("Cancelled.")
        return

    requests = data.get("signup_requests", {})
    if req_username not in requests:
        print("❌ Request not found")
        return

    req = requests[req_username]
    if req.get("status") != "pending":
        print(f"⚠️ This request is already {req.get('status')}")
        return

    req["status"] = "denied"
    req["denied_by"] = admin_username
    req["denied_at"] = datetime.utcnow().isoformat()

    save_data(data)
    print(f"✔ Request for '{req_username}' denied.")

# make a user an admin
def make_user_admin(admin_username: str):
    data = load_data()

    if not is_admin(data, admin_username):
        print("❌ You are not an admin")
        return

    users = data.get("users", {})
    admins = data.get("admins", [])

    print("\n=== MAKE USER AN ADMIN ===")

    if not users:
        print("No users found.")
        return

    print("Existing users:")
    for i, (uname, udata) in enumerate(users.items(), start=1):
        admin_tag = " [ADMIN]" if uname in admins else ""
        print(f"{i}. {uname}{admin_tag}")

    target = input("\nEnter the username to make an admin (or empty to cancel): ").lower().strip()
    if not target:
        print("Cancelled.")
        return

    if target not in users:
        print("❌ User not found")
        return

    if target in admins:
        print(f"⚠️ {target} is already an admin")
        return

    admins.append(target)
    data["admins"] = admins
    save_data(data)

    print(f"✔ {target} is now an admin and can approve/deny requests.")

# normal user login
def user_login():
    """Plain user login against data["users"]."""
    data = load_data()

    print("\n=== USER LOGIN ===")
    username = input("Username: ").lower().strip()
    password = input("Password: ")

    users = data.get("users", {})
    if username not in users:
        print("❌ User not found")
        return

    user = users[username]
    if user.get("is_locked", False):
        print("❌ This account is locked")
        return

    if user["password"] != hash_password(password):
        print("❌ Incorrect password")
        return

    admin_tag = " [ADMIN]" if is_admin(data, username) else ""
    print(f"✔ Logged in as: {username}{admin_tag}")

# main menu
def main_menu():
    """Text menu: view / approve / deny requests."""
    while True:
        print("\n=== MAIN MENU ===")
        print("1. View pending requests (admin only)")
        print("2. Approve request (admin only)")
        print("3. Deny request (admin only)")
        print("0. Exit")

        choice = input("Choose an option: ").strip()

        
        if choice == "1":
            data = load_data()
            view_pending_requests()
            
        elif choice == "2":
            print("Who do you want to verify?")
            user=input(":-")
            approve_request(user)
        elif choice == "3":
            print("Who do you want to verify?")
            user=input(":-")
            deny_request(user)
        elif choice == "0":
            print("Exiting...")
            break
        else:
            print("Invalid option. Try again.")


if __name__ == "__main__":
    main_menu()