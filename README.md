# SmartHome

A small smart-home demo: sign up, get approved by an admin, then control a
light, a fan and the front door from one page &mdash; by clicking, by typing,
or **by voice**. No database, no framework: plain Python standard library +
JSON files.

```
python main.py            # seeds on first run, self-tests, starts the server
# open http://localhost:8000     admin / admin123
```

## What's where

| file | job |
|------|-----|
| `main.py` | one command to run it all: env check &rarr; seed if empty &rarr; self-test every module &rarr; start server |
| `app.py` | the web server (stdlib `http.server`): serves `web/` and the JSON API |
| `login2.py` | accounts: request &rarr; admin approves &rarr; login. Lockout after 5 misses, dev-mode toggle |
| `signup.py` | the password scrambler (`password_funct` / `password_matches`) &mdash; SHA-256 iterated *rounds* times + a Fibonacci fingerprint |
| `devices.py` | the one shared "house" and its activity log |
| `intent.py` | plain text &rarr; a command: `parse("turn on the light")` &rarr; `{action, targets}` |
| `voice.py` | **offline speech in and out** (see below) |
| `voice_setup.py` | one-time download of the speech models |
| `seed.py` | wipe the databases, create the starter admin |
| `web/` | the two pages + `dashboard.js` (the control panel) |
| `archive/` | old code, **not used** &mdash; see `archive/README.md` |

Data lives in `data/` as JSON: `users/users.json` (approved), `users/pending.json`
(waiting), `devices.json` (the house). All created automatically.

## Voice

The mic works in two modes, picked automatically:

1. **Offline engine (preferred)** &mdash; [Vosk](https://alphacephei.com/vosk/)
   for speech&rarr;text and [Piper](https://github.com/rhasspy/piper) for
   text&rarr;speech, both running locally on the Python side. Free, no API keys,
   **no internet needed**, and Piper's voice is neural so it sounds natural
   (we also lift the pitch a little &mdash; `SMARTHOME_TTS_PITCH`, default `1.06`).
2. **Browser engine (fallback)** &mdash; the browser's own Web Speech API, used
   automatically when the offline models aren't installed.

### Turn on the offline engine

```
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python voice_setup.py          # ~100 MB of models, one time
sudo pacman -S ffmpeg                     # if you don't have it

.venv/bin/python main.py                  # run with the venv from now on
```

`main.py` prints whether the offline engine is live. Without it, everything
still works &mdash; the browser just does the talking and listening.

### The pipeline

```
mic  ->  POST /api/voice  ->  Vosk (speech->text)
                          ->  intent.py -> devices.py         (light / fan / door)
                              or chatbot_reply()              (anything else)
                          ->  Piper (text->speech)  ->  browser plays the reply
```

`voice.py` &rarr; `chatbot_reply()` is the hook for a general chatbot: set
`SMARTHOME_CHATBOT_URL` to an endpoint that takes `{text, user}` and returns
`{reply}`, or drop your own router in there. Until then, non-device phrases get
a short "I can only do devices" answer.

## API

`POST /api/signup` `/api/login` `/api/session` &middot;
`POST /api/pending` `/api/approve` `/api/reject` `/api/devmode` (admin) &middot;
`GET /api/devices` &middot; `POST /api/devices/set` `/api/command` `/api/activity/clear` &middot;
`GET /api/voice/status` &middot; `POST /api/voice` (raw audio) `/api/voice/tts` (`{text}` &rarr; wav)

## Handy

```
python main.py --reset      # wipe + reseed
python main.py --check      # self-tests only, no server
python main.py --port 9000
python voice.py "lock the door"        # test the brain + TTS from the CLI
SMARTHOME_DEV_MODE=1 python main.py     # sign-ups auto-approved
```
