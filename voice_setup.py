"""
voice_setup.py - download the offline speech models, once.

    python voice_setup.py            # get both models if missing
    python voice_setup.py --force    # re-download anyway
    python voice_setup.py --big      # bigger, more accurate STT model

Everything lands in data/models/ (git-ignored): vosk ~40MB for
speech-to-text, piper ~63MB for text-to-speech. Both free, and after
this the voice path needs no internet.

Needs the packages first (pip install -r requirements.txt) and ffmpeg
on PATH (Arch: sudo pacman -S ffmpeg).
"""

import argparse
import io
import os
import shutil
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(HERE, "data", "models")
VOSK_DIR = os.path.join(MODELS, "vosk")
PIPER_DIR = os.path.join(MODELS, "piper")

# small (40MB) is the default - with voice.py's grammar it nails the
# light/fan/door commands. --big (128MB) does free speech better but
# cant use the grammar.
VOSK_MODELS = {
    "small": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
    "big":   "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22-lgraph.zip",
}

# a warm US-English voice. swap the URLs for another piper voice if you
# want - https://rhasspy.github.io/piper-samples/
PIPER_BASE = ("https://huggingface.co/rhasspy/piper-voices/resolve/main/"
              "en/en_US/lessac/medium/en_US-lessac-medium.onnx")
PIPER_FILES = {
    "voice.onnx": PIPER_BASE + "?download=true",
    "voice.onnx.json": PIPER_BASE + ".json?download=true",
}


def _download(url, label):
    print(f"  downloading {label} ...", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "smarthome-voice-setup"})
    with urllib.request.urlopen(req, timeout=60) as r:
        total = int(r.headers.get("Content-Length", 0))
        chunks, got, shown = [], 0, -5
        while True:
            block = r.read(1 << 16)
            if not block:
                break
            chunks.append(block)
            got += len(block)
            pct = got * 100 // total if total else 0
            if pct >= shown + 5:
                shown = pct
                print(f"    {pct:3d}%  ({got // 1024} / {total // 1024 or '?'} KiB)", flush=True)
    return b"".join(chunks)


def setup_vosk(force, size="small"):
    ok = os.path.isfile(os.path.join(VOSK_DIR, "am", "final.mdl"))
    if ok and not force:
        print("  speech-to-text  : already present, skipping (--force to replace)")
        return
    if os.path.isdir(VOSK_DIR):
        shutil.rmtree(VOSK_DIR)
    raw = _download(VOSK_MODELS[size], f"speech-to-text model ({size})")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        top = z.namelist()[0].split("/")[0]        # the vosk-model-... folder
        z.extractall(MODELS)
    os.rename(os.path.join(MODELS, top), VOSK_DIR)
    print("  speech-to-text  : done ->", os.path.relpath(VOSK_DIR, HERE))


def setup_piper(force):
    have = (os.path.isfile(os.path.join(PIPER_DIR, "voice.onnx"))
            and os.path.isfile(os.path.join(PIPER_DIR, "voice.onnx.json")))
    if have and not force:
        print("  text-to-speech  : already present, skipping")
        return
    os.makedirs(PIPER_DIR, exist_ok=True)
    for name, url in PIPER_FILES.items():
        data = _download(url, f"text-to-speech {name}")
        with open(os.path.join(PIPER_DIR, name), "wb") as f:
            f.write(data)
    print("  text-to-speech  : done ->", os.path.relpath(PIPER_DIR, HERE))


def main():
    ap = argparse.ArgumentParser(description="Download Sync-Ghar's offline voice models.")
    ap.add_argument("--force", action="store_true", help="re-download even if present")
    ap.add_argument("--big", action="store_true",
                    help="bigger STT model (128 MB) - better free speech, "
                         "but the command grammar is skipped")
    args = ap.parse_args()

    os.makedirs(MODELS, exist_ok=True)
    print("Sync-Ghar voice setup")
    print("=" * 40)

    if not shutil.which("ffmpeg"):
        print("  note: no ffmpeg on PATH - server voice stays off")
        print("        (the browser engine still works).")

    try:
        import vosk  # noqa: F401
        import piper  # noqa: F401
    except ImportError as e:
        print(f"\n  missing package: {e.name}")
        print("  run:  pip install -r requirements.txt\n")
        sys.exit(1)

    setup_vosk(args.force, "big" if args.big else "small")
    setup_piper(args.force)

    print("=" * 40)
    print("Done. Start the app and the mic will use the offline engine.")


if __name__ == "__main__":
    main()
