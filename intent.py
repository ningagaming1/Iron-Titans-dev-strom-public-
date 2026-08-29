import re

# =============================================================
#  intent.py  ->  "plain English  ->   clear instruction"
# -------------------------------------------------------------
# reads a sentence, decides what the person wants, touches no device.
# parse("switch off the fan")
#   -> {"ok": True, "action": "off", "targets": ["fan"], "say": ...}
# parse("dim the light to 40 percent")
#   -> {"ok": True, "action": "level", "targets": ["light"], "level": 40, ...}
# devices.apply() takes that dict and flips things.
#
# parse() takes an optional `catalog` (from devices.catalog()) so it can
# also match devices the user added at runtime. Without it, only the
# three starter devices are known.

# words we accept for the starter devices -> the real device id
DEVICE_WORDS = {
    "light": "light", "lights": "light", "lamp": "light", "bulb": "light",
    "fan": "fan", "cooler": "fan",
    "door": "door", "gate": "door", "lock": "door", "latch": "door",
}

TURN_ON_WORDS  = {"on", "start", "begin", "enable", "activate"}
TURN_OFF_WORDS = {"off", "stop", "disable", "shut", "kill"}

OPEN_WORDS  = {"open", "unlock", "unlatch"}
CLOSE_WORDS = {"close", "lock", "shut", "latch"}

DIM_WORDS = {"dim", "set", "level", "brightness"}

EVERYTHING_WORDS = {"everything", "all", "every"}

# device ids -> their type, when no catalog is passed
_DEFAULT_TYPES = {"light": "toggle", "fan": "toggle", "door": "lock"}


def _word_map(catalog):
    """word -> device id, device id -> type, device id -> display name."""
    words = dict(DEVICE_WORDS)
    types = dict(_DEFAULT_TYPES)
    names = {"light": "the light", "fan": "the fan", "door": "the door"}
    # a device the user added owns the words in its name - so "the bedroom
    # lamp" points at that device, not the built-in living-room light.
    for dev in catalog or []:
        types[dev["id"]] = dev.get("type", "toggle")
        names[dev["id"]] = dev.get("name", dev["id"])
        for w in dev.get("words", []):
            words[w] = dev["id"]
        words[dev["id"]] = dev["id"]
    return words, types, names


def parse(text, catalog=None):
    """Return an intent dict. Always has 'ok' and 'say'."""
    words_map, types, names = _word_map(catalog)

    cleaned = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
    words = cleaned.split()

    if not words:
        return _fail("Say something like 'turn on the light'.")

    word_set = set(words)

    # a number in the sentence -> a dimmer level
    nums = [int(w) for w in words if w.isdigit()]
    level = max(0, min(100, nums[0])) if nums else None

    # which devices are mentioned?
    targets = []
    for w in words:
        name = words_map.get(w)
        if name and name not in targets:
            targets.append(name)

    if word_set & EVERYTHING_WORDS:
        targets = [d for d, t in types.items() if t in ("toggle", "dimmer")] or \
                  ["light", "fan"]

    if not targets:
        return _fail("Which device? Try 'turn off the fan'.")

    kinds = {types.get(t, "toggle") for t in targets}

    # all locks -> lock / unlock
    if kinds == {"lock"}:
        if word_set & OPEN_WORDS:
            return _ok("unlock", targets, _phrase(targets, "unlock", names))
        if word_set & CLOSE_WORDS or word_set & TURN_OFF_WORDS:
            return _ok("lock", targets, _phrase(targets, "lock", names))
        return _fail("Lock or unlock it?")

    # a level for a dimmer  ("set the light to 30", "dim the lamp")
    if "dimmer" in kinds and (level is not None or (word_set & DIM_WORDS)):
        lvl = level if level is not None else 30
        say = _phrase(targets, "set", names) + f" to {lvl}%"
        return _ok("level", targets, say, level=lvl)

    wants_on  = bool(word_set & TURN_ON_WORDS)  or bool(word_set & OPEN_WORDS)
    wants_off = bool(word_set & TURN_OFF_WORDS) or bool(word_set & CLOSE_WORDS)

    if wants_on and not wants_off:
        return _ok("on", targets, _phrase(targets, "on", names))
    if wants_off and not wants_on:
        return _ok("off", targets, _phrase(targets, "off", names))

    return _fail("Should I turn that on or off?")


# --- helpers ---
def _ok(action, targets, say, level=None):
    out = {"ok": True, "action": action, "targets": targets, "say": say}
    if level is not None:
        out["level"] = level
    return out


def _fail(say):
    return {"ok": False, "action": None, "targets": [], "say": say}


def _phrase(targets, action, names=None):
    names = names or {}
    label = " and ".join(names.get(t, "the " + t) for t in targets)
    verbs = {"on": "Turning", "off": "Turning", "lock": "Locking",
             "unlock": "Unlocking", "set": "Setting"}
    tail = {"on": " on", "off": " off"}.get(action, "")
    return f"{verbs.get(action, 'Setting')} {label}{tail}"
