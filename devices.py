import json
import os
from datetime import datetime, timezone

# devices.py - the state of the house.
# one shared house in data/devices.json, everyone sees the same thing.
# light + fan are on/off, door_locked True means locked. plus a short
# activity list of the last few actions.

DEVICES_FILE = os.path.join("data", "devices.json")

# a fresh house
FRESH_HOUSE = {
    "light": False,
    "fan": False,
    "door_locked": True,
    "activity": [],
}


# --- storage helpers ---
def _load():
    try:
        with open(DEVICES_FILE, "r", encoding="utf-8") as f:
            house = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        house = {}
    # fill gaps so old / half-written files still load
    house.setdefault("light", False)
    house.setdefault("fan", False)
    house.setdefault("door_locked", True)
    house.setdefault("activity", [])
    return house


def _save(house):
    os.makedirs(os.path.dirname(DEVICES_FILE), exist_ok=True)
    with open(DEVICES_FILE, "w", encoding="utf-8") as f:
        json.dump(house, f, indent=4)


def _log(house, text, icon):
    """Push one line onto the top of the activity list."""
    stamp = datetime.now().strftime("%H:%M")   # local time, nicer for the demo
    house["activity"].insert(0, {"text": text, "icon": icon, "at": stamp})
    del house["activity"][12:]


# --- what the server calls ---
def get_state():
    """Everything the dashboard needs to draw itself."""
    return _load()


def set_device(device, value, who="someone"):
    """
    device -> "light" | "fan" | "door"  (for "door", value True = locked)
    Returns (ok, house).
    """
    house = _load()
    value = bool(value)

    if device == "light":
        house["light"] = value
        _log(house, f"{who} turned the light {'on' if value else 'off'}", "light")
    elif device == "fan":
        house["fan"] = value
        _log(house, f"{who} turned the fan {'on' if value else 'off'}", "fan")
    elif device == "door":
        house["door_locked"] = value
        _log(house, f"{who} {'locked' if value else 'unlocked'} the door",
             "lock" if value else "unlock")
    else:
        return False, house

    _save(house)
    return True, house


def all_devices(on, who="someone"):
    """Flip light + fan together. Door is left alone."""
    house = _load()
    house["light"] = bool(on)
    house["fan"] = bool(on)
    _log(house, f"{who} turned everything {'on' if on else 'off'}",
         "bulk" if on else "night")
    _save(house)
    return True, house


def apply(intent_dict, who="someone"):
    """
    Take an intent from intent.parse() and change the house.
    Returns (message, house).
    """
    if not intent_dict.get("ok"):
        # not understood - say why, touch nothing
        return intent_dict.get("say", "Didn't catch that."), get_state()

    action = intent_dict["action"]

    if action == "lock":
        _, house = set_device("door", True, who)
        return intent_dict["say"], house
    if action == "unlock":
        _, house = set_device("door", False, who)
        return intent_dict["say"], house

    turn_on = (action == "on")
    house = get_state()
    for target in intent_dict["targets"]:
        if target in ("light", "fan"):
            _, house = set_device(target, turn_on, who)
    return intent_dict["say"], house


def clear_activity(who="someone"):
    house = _load()
    house["activity"] = []
    _log(house, f"{who} cleared the activity log", "info")
    _save(house)
    return True, house


def reset():
    """Back to the starting state (used by seed.py)."""
    _save({
        "light": False,
        "fan": False,
        "door_locked": True,
        "activity": [],
    })
