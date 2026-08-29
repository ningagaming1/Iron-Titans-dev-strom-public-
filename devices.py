import json
import os
import re
from datetime import datetime

# devices.py - the state of the house.
# one shared house in data/devices.json, everyone sees the same thing.
#
# a device is a small dict:
#   {"id","name","room","type","icon", ...state...}
# type is one of:
#   "toggle"  - on/off appliance   -> state key "on"   (bool)
#   "lock"    - a lock             -> state key "locked" (bool, True = locked)
#   "dimmer"  - dimmable light     -> state keys "on" (bool) + "level" (0-100)
#
# the three starter devices (light / fan / door) are marked "builtin" and
# cannot be removed. anyone logged in can add / remove their own devices.
#
# get_state() also mirrors the builtin devices onto the old flat keys
# ("light", "fan", "door_locked") so older code / the self-tests keep
# working.

DEVICES_FILE = os.path.join("data", "devices.json")

VALID_TYPES = ("toggle", "lock", "dimmer")

# the house everyone starts with
BUILTIN_DEVICES = [
    {"id": "light", "name": "Living Room Light", "room": "Living Room",
     "type": "toggle", "icon": "\U0001f4a1", "on": False, "builtin": True},
    {"id": "fan", "name": "Ceiling Fan", "room": "Living Room",
     "type": "toggle", "icon": "\U0001f300", "on": False, "builtin": True},
    {"id": "door", "name": "Main Door", "room": "Entrance",
     "type": "lock", "icon": "\U0001f512", "locked": True, "builtin": True},
]

# words that shouldn't help match a device by name
_STOP_WORDS = {"the", "a", "an", "my", "room", "main", "living", "bed",
               "front", "back", "smart", "home"}


def _fresh():
    return {"devices": [dict(d) for d in BUILTIN_DEVICES], "activity": []}


# --- storage helpers ---
def _blank_device(d):
    """Fill in any missing state keys for a device of its type."""
    d.setdefault("icon", "\U0001f50c")
    d.setdefault("room", "")
    if d.get("type") not in VALID_TYPES:
        d["type"] = "toggle"
    if d["type"] == "lock":
        d.setdefault("locked", True)
    else:
        d.setdefault("on", False)
    if d["type"] == "dimmer":
        d.setdefault("level", 0)
    return d


def _load():
    try:
        with open(DEVICES_FILE, "r", encoding="utf-8") as f:
            house = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        house = {}

    if not isinstance(house, dict):
        house = {}

    # migrate an old flat file ({"light": bool, "fan": bool, "door_locked": bool})
    if "devices" not in house:
        migrated = _fresh()
        for dev in migrated["devices"]:
            if dev["id"] in ("light", "fan") and dev["id"] in house:
                dev["on"] = bool(house[dev["id"]])
            if dev["id"] == "door" and "door_locked" in house:
                dev["locked"] = bool(house["door_locked"])
        migrated["activity"] = house.get("activity", [])
        house = migrated

    house.setdefault("devices", [])
    house.setdefault("activity", [])
    house["devices"] = [_blank_device(d) for d in house["devices"]
                        if isinstance(d, dict) and d.get("id")]

    # make sure the three builtins are always present
    have = {d["id"] for d in house["devices"]}
    for d in BUILTIN_DEVICES:
        if d["id"] not in have:
            house["devices"].append(dict(d))
    return house


def _save(house):
    os.makedirs(os.path.dirname(DEVICES_FILE), exist_ok=True)
    with open(DEVICES_FILE, "w", encoding="utf-8") as f:
        json.dump(house, f, indent=4)


def _find(house, device_id):
    for d in house["devices"]:
        if d["id"] == device_id:
            return d
    return None


def _log(house, text, icon):
    """Push one line onto the top of the activity list."""
    stamp = datetime.now().strftime("%H:%M")   # local time, nicer for the demo
    house["activity"].insert(0, {"text": text, "icon": icon, "at": stamp})
    del house["activity"][12:]


def _mirror(house):
    """Copy the builtin devices onto the legacy flat keys."""
    out = dict(house)
    out["light"] = False
    out["fan"] = False
    out["door_locked"] = True
    for d in house["devices"]:
        if d["id"] == "light":
            out["light"] = bool(d.get("on"))
        elif d["id"] == "fan":
            out["fan"] = bool(d.get("on"))
        elif d["id"] == "door":
            out["door_locked"] = bool(d.get("locked"))
    return out


# --- what the server calls ---
def get_state():
    """Everything the dashboard needs to draw itself."""
    return _mirror(_load())


def list_devices():
    return _load()["devices"]


def catalog():
    """
    Light metadata for intent.py + the voice vocab:
        [{"id","name","type","words":[...]}]
    `words` are the lower-case words that should match this device.
    """
    out = []
    for d in _load()["devices"]:
        raw = re.split(r"[^a-z0-9]+", (d["id"] + " " + d["name"]).lower())
        words = sorted({w for w in raw if len(w) >= 2 and w not in _STOP_WORDS})
        out.append({"id": d["id"], "name": d["name"],
                    "type": d["type"], "words": words})
    return out


def _apply_value(device, value, who):
    """Change one device in place, return an activity (text, icon) or None."""
    name = device["name"]
    icon = device.get("icon", "\U0001f50c")

    if device["type"] == "lock":
        device["locked"] = bool(value)
        verb = "locked" if device["locked"] else "unlocked"
        return f"{who} {verb} {name}", icon

    if device["type"] == "dimmer":
        if isinstance(value, bool):
            device["on"] = value
            if value and device.get("level", 0) == 0:
                device["level"] = 100
        elif isinstance(value, (int, float)):
            device["level"] = max(0, min(100, int(value)))
            device["on"] = device["level"] > 0
        else:
            device["on"] = bool(value)
        if device["on"]:
            return f"{who} set {name} to {device['level']}%", icon
        return f"{who} turned {name} off", icon

    # toggle
    device["on"] = bool(value)
    return f"{who} turned {name} {'on' if device['on'] else 'off'}", icon


def set_device(device_id, value, who="someone"):
    """
    device_id -> a device id, or "all" for every toggle / dimmer at once.
    value     -> bool (on/off, or locked for a lock) or 0-100 for a dimmer.
    Returns (ok, house).  house is the mirrored dict.
    """
    house = _load()

    if device_id == "all":
        return all_devices(bool(value), who)

    device = _find(house, device_id)
    if not device:
        return False, _mirror(house)

    entry = _apply_value(device, value, who)
    if entry:
        _log(house, *entry)
    _save(house)
    return True, _mirror(house)


def all_devices(on, who="someone"):
    """Flip every toggle + dimmer together. Locks are left alone."""
    house = _load()
    for d in house["devices"]:
        if d["type"] in ("toggle", "dimmer"):
            _apply_value(d, bool(on), who)
    _log(house, f"{who} turned everything {'on' if on else 'off'}",
         "⚡" if on else "\U0001f319")
    _save(house)
    return True, _mirror(house)


def add_device(spec, who="someone"):
    """
    spec -> {"name", "room", "type", "icon"}
    Returns (ok, message, house).
    """
    name = str(spec.get("name", "")).strip()
    room = str(spec.get("room", "")).strip()
    dtype = str(spec.get("type", "toggle")).strip().lower()
    icon = str(spec.get("icon", "")).strip() or "\U0001f50c"

    if not name:
        return False, "Give the device a name.", get_state()
    if dtype not in VALID_TYPES:
        return False, "Type must be toggle, lock or dimmer.", get_state()

    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "device"
    house = _load()
    device_id = base
    n = 2
    while _find(house, device_id):
        device_id = f"{base}-{n}"
        n += 1

    device = _blank_device({
        "id": device_id, "name": name, "room": room,
        "type": dtype, "icon": icon, "builtin": False,
    })
    house["devices"].append(device)
    _log(house, f"{who} added {name}", icon)
    _save(house)
    return True, f"Added {name}.", _mirror(house)


def remove_device(device_id, who="someone"):
    """Delete a device the user added. Builtins can't be removed."""
    house = _load()
    device = _find(house, device_id)
    if not device:
        return False, "No device with that id.", _mirror(house)
    if device.get("builtin"):
        return False, "The starter devices can't be removed.", _mirror(house)

    house["devices"] = [d for d in house["devices"] if d["id"] != device_id]
    _log(house, f"{who} removed {device['name']}", device.get("icon", "\U0001f50c"))
    _save(house)
    return True, f"Removed {device['name']}.", _mirror(house)


def apply(intent_dict, who="someone"):
    """
    Take an intent from intent.parse() and change the house.
    Returns (message, house).
    """
    if not intent_dict.get("ok"):
        return intent_dict.get("say", "Didn't catch that."), get_state()

    action = intent_dict["action"]
    level = intent_dict.get("level")
    house = _load()
    touched = False

    for target in intent_dict.get("targets", []):
        device = _find(house, target)
        if not device:
            continue
        if action == "lock":
            value = True
        elif action == "unlock":
            value = False
        elif action == "on":
            value = True
        elif action == "off":
            value = False
        elif action == "level":
            value = level if level is not None else 100
        else:
            continue
        _apply_value(device, value, who)
        touched = True

    if touched:
        _save(house)
    return intent_dict["say"], _mirror(house)


def clear_activity(who="someone"):
    house = _load()
    house["activity"] = []
    _log(house, f"{who} cleared the activity log", "•")
    _save(house)
    return True, _mirror(house)


def reset():
    """Back to the starting state (used by seed.py)."""
    _save(_fresh())
