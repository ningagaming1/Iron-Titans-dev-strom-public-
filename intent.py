import re

# =============================================================
#  intent.py  ->  "plain English  ->  a clear instruction"
# -------------------------------------------------------------
#  This is the "brain". It does not touch any device. It just
#  reads a sentence and decides what the person wants:
#
#     parse("could you please switch off the fan")
#       -> {"ok": True, "action": "off", "targets": ["fan"],
#           "say": "Turning the fan off"}
#
#     parse("open the door")
#       -> {"ok": True, "action": "unlock", "targets": ["door"],
#           "say": "Unlocking the door"}
#
#  devices.apply() takes this dict and actually flips things.
# =============================================================

# every word we accept for a device  ->  the real device name
DEVICE_WORDS = {
    "light": "light", "lights": "light", "lamp": "light", "bulb": "light",
    "fan": "fan", "cooler": "fan",
    "door": "door", "gate": "door", "lock": "door", "latch": "door",
}

TURN_ON_WORDS  = {"on", "start", "begin", "enable", "activate"}
TURN_OFF_WORDS = {"off", "stop", "disable", "shut", "kill"}

OPEN_WORDS  = {"open", "unlock", "unlatch"}
CLOSE_WORDS = {"close", "lock", "shut", "latch"}

EVERYTHING_WORDS = {"everything", "all", "every"}


def parse(text):
    """Return an intent dict. Always has 'ok' and 'say'."""
    cleaned = re.sub(r"[^a-z\s]", " ", (text or "").lower())
    words = cleaned.split()

    if not words:
        return _fail("Say something like 'turn on the light'.")

    word_set = set(words)

    # ---- what devices are mentioned? ----
    targets = []
    for w in words:
        name = DEVICE_WORDS.get(w)
        if name and name not in targets:
            targets.append(name)

    if word_set & EVERYTHING_WORDS:
        targets = ["light", "fan"]          # "everything" = the switchable stuff

    if not targets:
        return _fail("Which device? Try 'turn off the fan'.")

    # ---- the door has its own words (lock / unlock) ----
    if targets == ["door"]:
        if word_set & OPEN_WORDS:
            return _ok("unlock", ["door"], "Unlocking the door")
        if word_set & CLOSE_WORDS or word_set & TURN_OFF_WORDS:
            return _ok("lock", ["door"], "Locking the door")
        return _fail("Lock or unlock the door?")

    # ---- light / fan: figure out on vs off ----
    wants_on  = bool(word_set & TURN_ON_WORDS)  or bool(word_set & OPEN_WORDS)
    wants_off = bool(word_set & TURN_OFF_WORDS) or bool(word_set & CLOSE_WORDS)

    if wants_on and not wants_off:
        return _ok("on", targets, _phrase(targets, "on"))
    if wants_off and not wants_on:
        return _ok("off", targets, _phrase(targets, "off"))

    return _fail("Should I turn that on or off?")


# ---- small helpers ----
def _ok(action, targets, say):
    return {"ok": True, "action": action, "targets": targets, "say": say}


def _fail(say):
    return {"ok": False, "action": None, "targets": [], "say": say}


def _phrase(targets, action):
    names = " and ".join("the " + t for t in targets)
    return f"Turning {names} {action}"
