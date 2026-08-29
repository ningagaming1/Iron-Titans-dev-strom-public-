"""
voice.py - offline speech in and out.

    transcribe(audio_bytes)    mic audio -> text     (Vosk)
    answer(text, who)          text -> {reply, house, ok, kind}
    synthesize(text)           text -> WAV bytes     (Piper)
    handle(audio_bytes, who)   the whole loop in one call

Vosk + Piper, both free and offline once voice_setup.py has grabbed
the models (into data/models/, git-ignored). If a model is missing,
status() says so and the browser uses its own Web Speech engine.

answer() runs the text through intent.py first; if it's not a device
command it tries chatbot_reply(), else a canned "I only do devices" line.
"""

import importlib.util
import io
import json
import os
import shutil
import subprocess
import threading
import wave

import devices
import intent

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(HERE, "data", "models")
VOSK_DIR = os.path.join(MODELS_DIR, "vosk")
PIPER_ONNX = os.path.join(MODELS_DIR, "piper", "voice.onnx")

# lift the TTS pitch a touch so it sounds warmer. too much = chipmunk.
TTS_PITCH = float(os.environ.get("SMARTHOME_TTS_PITCH", "1.06"))
# piper pace: >1 slower, <1 faster
TTS_PACE = float(os.environ.get("SMARTHOME_TTS_PACE", "1.0"))

FFMPEG = shutil.which("ffmpeg")

# load each model once, on first use. server is threaded so lock it.
_vosk_model = None
_piper_voice = None
_load_lock = threading.Lock()
_piper_lock = threading.Lock()


# --- what's available right now? ---
def _installed(pkg):
    try:
        return importlib.util.find_spec(pkg) is not None
    except (ImportError, ValueError):
        return False


def _vosk_ready():
    return (_installed("vosk")
            and os.path.isfile(os.path.join(VOSK_DIR, "am", "final.mdl")))


def _piper_ready():
    return (_installed("piper")
            and os.path.isfile(PIPER_ONNX) and os.path.isfile(PIPER_ONNX + ".json"))


def status():
    """Tell the front-end which half of the pipeline works."""
    # both paths need ffmpeg
    stt = _vosk_ready() and bool(FFMPEG)
    tts = _piper_ready() and bool(FFMPEG)
    return {
        "stt": stt,
        "tts": tts,
        "ffmpeg": bool(FFMPEG),
        "ready": stt and tts,
        "pitch": TTS_PITCH,
        "hint": _setup_hint(stt, tts),
    }


def _setup_hint(stt, tts):
    if stt and tts:
        return "Offline voice is ready."
    if not FFMPEG:
        return "Install ffmpeg for server-side voice; the browser engine still works."
    if not (_installed("vosk") and _installed("piper")):
        return ("Run  pip install -r requirements.txt  then  python voice_setup.py  "
                "for offline voice. Until then the browser engine is used.")
    missing = []
    if not stt:
        missing.append("speech-to-text")
    if not tts:
        missing.append("text-to-speech")
    return ("Run  python voice_setup.py  to download the "
            + " and ".join(missing) + " model(s). Until then the browser engine is used.")


# --- 1. speech -> text (Vosk) ---
def _get_vosk():
    global _vosk_model
    if _vosk_model is None:
        with _load_lock:
            if _vosk_model is None:
                from vosk import Model, SetLogLevel
                SetLogLevel(-1)              # hush kaldi
                _vosk_model = Model(VOSK_DIR)
    return _vosk_model


def _to_pcm16_mono_16k(audio_bytes):
    """
    Whatever the browser sent -> 16kHz mono s16 PCM, which is what
    Vosk wants. ffmpeg reads almost anything so let it sort the input.
    """
    if not FFMPEG:
        raise RuntimeError("ffmpeg is not installed")
    out = subprocess.run(
        [FFMPEG, "-loglevel", "error", "-i", "pipe:0",
         "-ar", "16000", "-ac", "1", "-f", "s16le", "pipe:1"],
        input=audio_bytes, capture_output=True,
    )
    if out.returncode != 0:
        raise RuntimeError("couldn't read that audio clip - try recording again")
    return out.stdout


# tight vocab for the light/fan/door commands. Vosk is way more accurate
# when it can only pick from the words it needs. Built from intent.py so
# the two dont drift. A free-form pass still runs for everything else.
_GRAMMAR_JSON = None
GRAMMAR_ON = os.environ.get("SMARTHOME_VOICE_GRAMMAR", "1").lower() not in ("0", "false", "no")


def _command_grammar():
    global _GRAMMAR_JSON
    if _GRAMMAR_JSON is None:
        words = set()
        for d in (intent.DEVICE_WORDS,):
            words |= set(d)
        for s in (intent.TURN_ON_WORDS, intent.TURN_OFF_WORDS,
                  intent.OPEN_WORDS, intent.CLOSE_WORDS, intent.EVERYTHING_WORDS):
            words |= set(s)
        words |= {"turn", "switch", "the", "a", "please", "my", "to", "power", "you", "can"}
        _GRAMMAR_JSON = json.dumps([" ".join(sorted(words)), "[unk]"])
    return _GRAMMAR_JSON


class _hush_stderr:
    """Vosk writes 'word missing in vocabulary' straight to fd 2, past
    SetLogLevel. Mute fd 2 while we build the recognizer."""
    def __enter__(self):
        self._old = os.dup(2)
        self._null = os.open(os.devnull, os.O_WRONLY)
        os.dup2(self._null, 2)

    def __exit__(self, *a):
        os.dup2(self._old, 2)
        os.close(self._null)
        os.close(self._old)


def _recognize(pcm, grammar=None, alts=1):
    from vosk import KaldiRecognizer
    with _hush_stderr():
        rec = (KaldiRecognizer(_get_vosk(), 16000, grammar) if grammar
               else KaldiRecognizer(_get_vosk(), 16000))
    if alts > 1:
        rec.SetMaxAlternatives(alts)
    rec.AcceptWaveform(pcm)
    res = json.loads(rec.FinalResult())
    if "alternatives" in res:
        return [(a.get("text") or "").strip() for a in res["alternatives"]]
    return [(res.get("text") or "").strip()]


# words we can act on - used to snap near-misses ("fam" -> "fan")
def _vocab():
    v = set(intent.DEVICE_WORDS)
    for s in (intent.TURN_ON_WORDS, intent.TURN_OFF_WORDS, intent.OPEN_WORDS,
              intent.CLOSE_WORDS, intent.EVERYTHING_WORDS):
        v |= set(s)
    return v


_VOCAB = None


def _repair(text):
    """Snap near-miss words to the closest command word.
    'turn on the lite' -> 'turn on the light', 'fam' -> 'fan'."""
    global _VOCAB
    if _VOCAB is None:
        _VOCAB = _vocab()
    import difflib
    out = []
    for w in text.split():
        if w in _VOCAB or len(w) < 3:
            out.append(w)
            continue
        near = difflib.get_close_matches(w, _VOCAB, n=1, cutoff=0.8)
        out.append(near[0] if near else w)
    return " ".join(out)


def transcribe(audio_bytes):
    """
    Mic audio -> plain lowercase text.

    Two passes: a vocab-locked one tuned for device commands, and a free
    one. If the locked pass gives a real command we trust it, else we
    fall back to the free text so the chatbot hook still gets a shot.
    Returns "" if nothing was heard.
    """
    if not _vosk_ready():
        raise RuntimeError("speech-to-text model missing - run voice_setup.py")

    pcm = _to_pcm16_mono_16k(audio_bytes)

    if GRAMMAR_ON:
        try:
            # 3 best guesses, first real command wins (try a fuzzy repair too)
            for guess in _recognize(pcm, _command_grammar(), alts=3):
                guess = " ".join(w for w in guess.split()
                                 if w not in ("unk", "[unk]")).strip()
                for cand in (guess, _repair(guess)):
                    if cand and intent.parse(cand).get("ok"):
                        return cand
        except Exception:
            pass                     # e.g. a model with no grammar support

    free = _recognize(pcm)[0]
    repaired = _repair(free)
    return repaired if intent.parse(repaired).get("ok") else free


# --- 2. the brain: text -> what to say / do ---
def chatbot_reply(text, who="someone"):
    """
    Hook for a general chatbot - anything that isn't a device command.

    Point SMARTHOME_CHATBOT_URL at an endpoint. We POST {text, user} and
    read {reply} (also accepts answer/text/response). Any error -> None
    and the caller uses a canned line.
    """
    url = os.environ.get("SMARTHOME_CHATBOT_URL")
    if not url:
        return None
    try:
        import urllib.request
        payload = json.dumps({"text": text, "user": who}).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
        for key in ("reply", "answer", "text", "response", "say"):
            if isinstance(data.get(key), str) and data[key].strip():
                return data[key].strip()
    except Exception:
        return None
    return None


def answer(text, who="someone"):
    """
    text -> {reply, house, ok, kind}

        kind = "device"   understood a command and did it
             = "chat"      handed to the chatbot
             = "unknown"   couldnt help
    """
    text = (text or "").strip()
    if not text:
        return {"reply": "I didn't catch that. Try again?", "house": devices.get_state(),
                "ok": False, "kind": "unknown"}

    parsed = intent.parse(text)
    if parsed.get("ok"):
        say, house = devices.apply(parsed, who)
        return {"reply": say, "house": house, "ok": True, "kind": "device"}

    # not a device command - see if a chatbot wants it
    bot = chatbot_reply(text, who)
    if bot:
        return {"reply": bot, "house": devices.get_state(), "ok": True, "kind": "chat"}

    # nothing worked - reuse intent's nudge
    return {"reply": parsed.get("say", "I can turn the light or fan on and off, "
                                       "or lock the door."),
            "house": devices.get_state(), "ok": False, "kind": "unknown"}


# --- 3. text -> speech (Piper + a small pitch lift) ---
def _get_piper():
    global _piper_voice
    if _piper_voice is None:
        with _load_lock:
            if _piper_voice is None:
                from piper import PiperVoice
                _piper_voice = PiperVoice.load(PIPER_ONNX)
    return _piper_voice


def _pitch_shift(wav_bytes, factor):
    """Raise pitch by `factor` without speeding it up (ffmpeg)."""
    if not FFMPEG or abs(factor - 1.0) < 0.01:
        return wav_bytes
    with wave.open(io.BytesIO(wav_bytes)) as w:
        rate = w.getframerate()
    af = f"asetrate={rate}*{factor},aresample={rate},atempo={1/factor:.5f}"
    out = subprocess.run(
        [FFMPEG, "-loglevel", "error", "-i", "pipe:0", "-af", af, "-f", "wav", "pipe:1"],
        input=wav_bytes, capture_output=True,
    )
    return out.stdout if out.returncode == 0 else wav_bytes


def synthesize(text):
    """text -> WAV bytes, plays in any browser."""
    if not _piper_ready():
        raise RuntimeError("text-to-speech model missing - run voice_setup.py")

    from piper import SynthesisConfig
    cfg = SynthesisConfig(length_scale=TTS_PACE, noise_scale=0.667,
                          noise_w_scale=0.85, volume=0.95)
    buf = io.BytesIO()
    with _piper_lock:
        with wave.open(buf, "wb") as w:
            _get_piper().synthesize_wav(text, w, syn_config=cfg)
    return _pitch_shift(buf.getvalue(), TTS_PITCH)


# --- 4. the whole round trip, for POST /api/voice ---
def handle(audio_bytes, who="someone"):
    """
    mic audio -> {text, reply, house, ok, kind, audio_wav}

    audio_wav is the spoken reply as WAV bytes, or None if TTS isnt set
    up (browser speaks it itself then).
    """
    text = transcribe(audio_bytes)
    result = answer(text, who)
    result["text"] = text

    wav = None
    if _piper_ready():
        try:
            wav = synthesize(result["reply"])
        except Exception:
            wav = None
    result["audio_wav"] = wav
    return result


# quick check:  python voice.py "lock the door"
if __name__ == "__main__":
    import sys
    print(json.dumps(status(), indent=2))
    phrase = " ".join(sys.argv[1:]) or "turn on the light"
    print("\nanswer(%r):" % phrase)
    r = answer(phrase, "cli")
    print(json.dumps({k: v for k, v in r.items() if k != "house"}, indent=2))
    if _piper_ready():
        open("voice_test.wav", "wb").write(synthesize(r["reply"]))
        print("\nwrote voice_test.wav")
