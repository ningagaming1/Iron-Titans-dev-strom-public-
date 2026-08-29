"""
voice.py  ->  offline speech IN and speech OUT for SmartHome

    transcribe(audio_bytes)      raw mic audio  -> text        (Vosk, offline)
    answer(text, who)            text           -> {reply, house, ok, kind}
    synthesize(text)             text           -> WAV bytes    (Piper, offline)
    handle(audio_bytes, who)     the whole loop in one call

Design goals the team asked for:
    * free            - Vosk + Piper are open source, no API keys, no quota
    * offline         - after voice_setup.py has fetched the models, nothing
                        on this path touches the internet
    * "just works"    - every function degrades gracefully. If a model is
                        missing, status() says so and the browser falls back
                        to its own Web Speech engine instead of erroring.
    * human-ish voice - Piper is a neural TTS (already natural), and we nudge
                        the pitch up a touch with ffmpeg so it sounds warmer
                        and less flat.  Tune with SMARTHOME_TTS_PITCH.

Models live in  data/models/  (git-ignored) and are downloaded once:

    python voice_setup.py

The "brain" in answer():
    1. run the text through intent.py  ->  if it's a device command, do it
    2. otherwise, if a chatbot is wired up (chatbot_reply below), ask it
    3. otherwise say a short "I can only do devices" line
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
VOSK_DIR = os.path.join(MODELS_DIR, "vosk")            # extracted model folder
PIPER_ONNX = os.path.join(MODELS_DIR, "piper", "voice.onnx")

# how much to lift the TTS pitch (1.0 = off, 1.06 = a little warmer / more human).
# a small shift only - too much and it turns into a chipmunk.
TTS_PITCH = float(os.environ.get("SMARTHOME_TTS_PITCH", "1.06"))
# Piper speaking pace: >1 slower, <1 faster.
TTS_PACE = float(os.environ.get("SMARTHOME_TTS_PACE", "1.0"))

FFMPEG = shutil.which("ffmpeg")

# lazy singletons - loading a model takes ~1s, so we do it once on first use.
# the server is threaded, so guard model load + Piper inference with a lock.
_vosk_model = None
_piper_voice = None
_load_lock = threading.Lock()
_piper_lock = threading.Lock()


# =============================================================
#  what's available right now?
# =============================================================
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
    """Tell the front-end which half of the pipeline it can use."""
    # both paths pipe audio through ffmpeg (decode in, pitch out)
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


# =============================================================
#  1. speech  ->  text   (Vosk)
# =============================================================
def _get_vosk():
    global _vosk_model
    if _vosk_model is None:
        with _load_lock:
            if _vosk_model is None:
                from vosk import Model, SetLogLevel
                SetLogLevel(-1)              # hush the kaldi banner
                _vosk_model = Model(VOSK_DIR)
    return _vosk_model


def _to_pcm16_mono_16k(audio_bytes):
    """
    Take whatever the browser sent (webm/opus, ogg, wav, mp3, raw...) and
    return 16 kHz mono signed-16-bit PCM, which is what Vosk wants.
    ffmpeg reads almost anything, so we just let it figure the input out.
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


def transcribe(audio_bytes):
    """
    Raw microphone audio  ->  plain text (lower-case, no punctuation).
    Returns "" if nothing intelligible was heard.
    """
    if not _vosk_ready():
        raise RuntimeError("speech-to-text model missing - run voice_setup.py")

    pcm = _to_pcm16_mono_16k(audio_bytes)

    from vosk import KaldiRecognizer
    rec = KaldiRecognizer(_get_vosk(), 16000)
    rec.AcceptWaveform(pcm)
    result = json.loads(rec.FinalResult())
    return (result.get("text") or "").strip()


# =============================================================
#  2. the brain:  text  ->  what to say / do
# =============================================================
def chatbot_reply(text, who="someone"):
    """
    Hook for a general chatbot, for anything that ISN'T a device command
    ("what's the weather", "tell me a joke", ...).

    If you have a chatbot HTTP endpoint, point SMARTHOME_CHATBOT_URL at it.
    We POST {"text": ..., "user": ...} and read {"reply": ...} (also accepts
    "answer" / "text" / "response").  Anything goes wrong -> None, and the
    caller falls back to a canned line.

    This is also the spot to drop in your other project's router.route():
        from router import route            # (needs that project's packages)
        return route(text, {"username": who})
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
    text  ->  {reply, house, ok, kind}

        kind = "device"   we understood a light/fan/door command and did it
             = "chat"      handed off to the chatbot
             = "unknown"   couldn't help
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

    # nothing could help - reuse intent's friendly nudge
    return {"reply": parsed.get("say", "I can turn the light or fan on and off, "
                                       "or lock the door."),
            "house": devices.get_state(), "ok": False, "kind": "unknown"}


# =============================================================
#  3. text  ->  speech   (Piper, then a gentle pitch lift)
# =============================================================
def _get_piper():
    global _piper_voice
    if _piper_voice is None:
        with _load_lock:
            if _piper_voice is None:
                from piper import PiperVoice
                _piper_voice = PiperVoice.load(PIPER_ONNX)
    return _piper_voice


def _pitch_shift(wav_bytes, factor):
    """Raise pitch by `factor` without speeding the speech up (ffmpeg)."""
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
    """text -> WAV bytes (16-bit PCM, plays natively in any browser)."""
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


# =============================================================
#  4. the whole round trip, for POST /api/voice
# =============================================================
def handle(audio_bytes, who="someone"):
    """
    mic audio  ->  {text, reply, house, ok, kind, audio_wav}

    audio_wav is raw WAV bytes for the spoken reply, or None if TTS isn't
    set up (the browser then speaks it with its own engine).
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


# quick manual check:  python voice.py "lock the door"
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
