"""
voice_setup.py  ->  download the offline speech models, once.

    python voice_setup.py            # get both models if missing
    python voice_setup.py --force    # re-download even if present

Puts everything under  data/models/  (git-ignored):

    data/models/vosk/            ~40 MB  - speech to text
    data/models/piper/voice.*    ~63 MB  - text to speech (natural voice)

Both are open source and free. After this runs, the whole voice path
works with no internet.

Needs the Python packages first:   pip install -r requirements.txt
And ffmpeg on PATH (Arch:  sudo pacman -S ffmpeg).
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

VOSK_ZIP_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"

# a warm, natural US-English voice. swap the three URLs for another Piper
# voice if you prefer - https://rhasspy.github.io/piper-samples/
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


def setup_vosk(force):
    ok = os.path.isfile(os.path.join(VOSK_DIR, "am", "final.mdl"))
    if ok and not force:
        print("  speech-to-text  : already present, skipping")
        return
    if os.path.isdir(VOSK_DIR):
        shutil.rmtree(VOSK_DIR)
    raw = _download(VOSK_ZIP_URL, "speech-to-text model (~40 MB)")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        top = z.namelist()[0].split("/")[0]        # vosk-model-small-en-us-0.15/
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
    ap = argparse.ArgumentParser(description="Download SmartHome's offline voice models.")
    ap.add_argument("--force", action="store_true", help="re-download even if present")
    args = ap.parse_args()

    os.makedirs(MODELS, exist_ok=True)
    print("SmartHome voice setup")
    print("=" * 40)

    if not shutil.which("ffmpeg"):
        print("  note: ffmpeg not found on PATH - install it or server-side voice")
        print("        will stay off (the browser engine still works).")

    try:
        import vosk  # noqa: F401
        import piper  # noqa: F401
    except ImportError as e:
        print(f"\n  missing package: {e.name}")
        print("  run:  pip install -r requirements.txt\n")
        sys.exit(1)

    setup_vosk(args.force)
    setup_piper(args.force)

    print("=" * 40)
    print("Done. Start the app and the mic will use the offline engine.")


if __name__ == "__main__":
    main()
