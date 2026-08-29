"""
theory.py - how Sync-Ghar works, in plain words, for the team.

This file doesn't run anything. It's a written walkthrough of every
part of the project so a new teammate can read it top to bottom and
understand what each file does and why. Run `python theory.py` for a
short section index.

Read this once, keep the code open next to it, and you'll be able to
find your way around in an afternoon.


================================================================
0. THE 60-SECOND VERSION
================================================================

Sync-Ghar is a tiny website for controlling a pretend house: a light,
a fan, and a front-door lock. You can control them three ways:

    1. click the buttons on the dashboard
    2. type a command  ("turn off the fan")
    3. say a command out loud

There is a login system with admin approval, so not just anyone can
walk in. Everything runs on one computer - no cloud, no paid services,
no internet needed once the voice models are downloaded.

The whole thing is built from Python's standard library (no web
framework) plus two small open-source voice tools (Vosk and Piper).
State is stored in plain JSON files you can open in a text editor.


================================================================
1. THE SHAPE OF THE PROJECT
================================================================

    main.py          the "run everything" script - start here
    app.py           the web server (serves pages + answers the API)
    login2.py        accounts: sign up, approve, log in, lockout
    signup.py        turns a password into something safe to store
    devices.py       the state of the house (light / fan / door)
    intent.py        turns "turn off the fan" into a clear instruction
    voice.py         offline speech-in (Vosk) and speech-out (Piper)
    voice_setup.py   one-time download of the voice models
    discovery.py     find other Sync-Ghar servers on the wifi (--find)
    seed.py          wipe the data and create the first admin
    tts.py           a standalone speech helper (NOT used by the app)

    web/
      index.html     the login / sign-up page
      dashboard.html the control panel
      auth.js        login page logic
      dashboard.js   dashboard logic (buttons, polling, microphone)
      style.css      all the styling, light + dark theme

    data/
      users/users.json     approved accounts
      users/pending.json    accounts waiting for approval
      users/settings.json   remembers the developer-mode switch
      devices.json          the one shared house
      models/               downloaded Vosk + Piper files (git-ignored)

    archive/
      adminconnection.py    an OLD login attempt - kept for reference,
                            must never be run (see section 13)


================================================================
2. PLAIN-ENGLISH GLOSSARY
================================================================

Server            A program that waits for requests and sends back
                  answers. Our server is app.py. It listens on
                  "port 8000" of your own machine.

Port              A numbered door on a computer. Web browsers talk to
                  http://localhost:8000 -> "this machine, door 8000".

localhost         "this same computer". Nothing leaves the machine.

HTTP request      What a browser sends when it wants a page or data.
                  Two kinds we use:
                    GET  - "give me this"        (loading a page)
                    POST - "here is some data"   (logging in, etc.)

API               A set of URLs that return data instead of a page.
                  Ours all start with /api/ and return JSON.

JSON              A text format for data that looks like Python dicts
                  and lists:  {"light": true, "fan": false}
                  Both Python and JavaScript read and write it easily.

Hash              A one-way scramble of some text. Easy to go text ->
                  hash, practically impossible to go back. We store the
                  hash of a password, never the password itself.

Front-end         The part that runs in the browser (HTML/CSS/JS).
Back-end          The part that runs in Python (app.py and friends).

localStorage      A small notepad the browser keeps per website. We use
                  it to remember "you are logged in as X" between page
                  loads. It lives only in that one browser.

Polling           Asking again on a timer. The dashboard asks the
                  server "what's the house state now?" every 5 seconds,
                  so two laptops stay roughly in sync.

STT / TTS         Speech-To-Text (hear words -> get text) and
                  Text-To-Speech (text -> spoken audio).

Model             A big data file a voice tool needs to do its job.
                  We download these once into data/models/.


================================================================
3. WHAT HAPPENS WHEN YOU LOAD THE PAGE  (the request lifecycle)
================================================================

    1. You open http://localhost:8000 in a browser.
    2. The browser sends a GET request to app.py.
    3. app.py sees the path "/" and sends back web/index.html.
    4. The browser reads that HTML, which asks for /style.css and
       /auth.js - two more GET requests, two more files sent back.
    5. auth.js runs. It checks localStorage: are you already logged
       in? If yes, it jumps straight to dashboard.html.
    6. You type a username + password and hit the button.
    7. auth.js sends a POST request to /api/login with your details
       as JSON.
    8. app.py hands that to login2.login(), which checks the files in
       data/users/ and returns (ok, message, user).
    9. app.py sends that back as JSON.
   10. If ok, auth.js saves the user into localStorage and loads the
       dashboard. If not, it shows the error message.

Every feature follows this same shape: browser -> POST /api/... ->
app.py routes it to the right module -> module does the work and
maybe writes a JSON file -> app.py sends JSON back -> the browser
updates what's on screen.


================================================================
4. main.py  -  the "one command" launcher
================================================================

WHAT IT'S FOR
    So nobody has to remember five setup steps. `python main.py` does
    the checks, seeds the database on the very first run, tests every
    module, then starts the web server.

WHAT IT DOES, IN ORDER
    1. Voice virtual-env hop. If there's a .venv folder with the voice
       packages installed, main.py re-launches itself using that
       Python, so plain `python main.py` still gets working speech.
    2. Environment check - right Python version? all the project files
       and web/ assets present? If not, it stops with a clear message.
    3. Database check - if data/users/users.json has no accounts, it
       runs seed.py to create the starter admin. If accounts already
       exist, it leaves them alone.
    4. Self-test - imports every module and runs quick checks:
       password round-trip, intent parsing, flipping devices, the
       sign-up -> approve -> login flow. These run against a COPY of
       data/ in a temp folder, so your real data is never touched.
    5. Start the server (the same one app.py starts).

USEFUL FLAGS
    python main.py --reset     wipe the data, reseed, then start
    python main.py --check     run the self-tests and quit (no server)
    python main.py --port 9000 use a different port
    python main.py --https     serve over https so other wifi devices
                               can use the mic too (see section 17)
    python main.py --debug     show full error details if something breaks


================================================================
5. app.py  -  the web server
================================================================

WHAT IT'S FOR
    This is the bridge between the browser and the Python code. It
    does two jobs:
      a) serve the files in web/ (the pages, styling, scripts)
      b) answer the /api/ URLs with JSON

HOW IT'S BUILT
    It uses http.server from Python's standard library - no Flask, no
    Django. "ThreadingHTTPServer" means it can handle a few requests
    at once, so two laptops can use the app together.

    There's one class, Handler, with:
      do_GET   - handles page loads and read-only data
      do_POST  - handles everything that changes something

THE API (every path starts with /api/)
    POST /api/signup        create a pending account request
    POST /api/login         check a username + password
    POST /api/session       does this account still exist?
    POST /api/pending       (admin) list who's waiting for approval
    POST /api/approve       (admin) approve someone
    POST /api/reject        (admin) drop someone's request
    POST /api/devmode       (admin) toggle developer mode
    GET  /api/config        is developer mode on?
    GET  /api/devices       the whole house state
    POST /api/devices/set   flip one device (or "all")
    POST /api/command       typed text -> intent -> house
    POST /api/activity/clear wipe the activity log
    GET  /api/voice/status  is the offline voice engine ready?
    POST /api/voice         raw microphone audio -> text -> house ->
                            spoken reply (this one sends audio, not JSON)
    POST /api/voice/tts     text -> a WAV audio file of that text

NOTES
    - app.py doesn't decide any rules itself. It reads the request,
      calls the right module, and passes the answer back. The actual
      logic lives in login2.py, devices.py, intent.py, voice.py.
    - "admin" actions check login2.is_admin() first and refuse if
      you're not on the approved list.


================================================================
6. login2.py  -  accounts, approval, and login
================================================================

WHAT IT'S FOR
    Deciding who is allowed in. There are two lists (two JSON files):

      data/users/pending.json   signed up, waiting for an admin.
                                CANNOT log in yet.
      data/users/users.json     approved. CAN log in. In this project,
                                every approved person is also an admin
                                (there are no "normal users" - keep
                                that in mind, it's a deliberate
                                simplification for the hackathon).

THE FLOW
    request_account(name, pw)  -> writes a record into pending.json
    approve(name)              -> moves that record to users.json
    reject(name)               -> deletes it from pending.json
    login(name, pw)            -> only ever reads users.json

    There is no "roles" table. Your permission level is simply which
    file your name is in.

DEVELOPER MODE
    A switch that skips the waiting list. While it's ON, a new sign-up
    goes straight into users.json and can log in immediately. Handy
    while building; turn it OFF to test the real approval flow.

    Where the setting comes from, in priority order:
      1. the SMARTHOME_DEV_MODE environment variable (1/true/yes/on)
      2. data/users/settings.json (remembered from the last toggle)
      3. the default in the code (OFF)

    An admin can flip it live on the Invites tab, or by POSTing to
    /api/devmode. set_dev_mode() writes the choice into settings.json.

LOGIN RULES (what login() checks, in order)
    - name is in pending.json    -> "still waiting for approval"
    - name isn't known at all     -> "wrong username or password"
      (same vague message on purpose - don't reveal which names exist)
    - account is locked           -> refuse, UNLESS the password given
                                     is the stored recovery hash
    - still in a cooldown          -> refuse until it passes. A wrong
                                     password starts a wait that DOUBLES
                                     each miss (5s, 10s, 20s, ...), stored
                                     as cooldown_until on the record so a
                                     page reload can't skip it. Set the
                                     first step with SMARTHOME_LOGIN_COOLDOWN
                                     (0 turns it off).
    - password is wrong           -> count the miss, arm the cooldown.
                                     After 5 misses (MAX_TRIES) the
                                     account locks instead.
    - password is right           -> success; reset the miss counter,
                                     clear any lock and cooldown, stamp
                                     last_login, hand back a safe copy of
                                     the record (no password bits in it).

    app.py adds "retry_after" (seconds) to the /api/login reply when a
    cooldown is in effect, and auth.js counts it down on the button.

THE "RECOVERY HASH"
    If an account locks, you can paste the stored password hash from
    users.json into the password box to get back in. This is a
    convenience for our build, NOT real security - anyone who can read
    the file could do it. Fine for a local toy, would be removed for
    anything real.

STORAGE HELPERS
    _load(path) / _save(path, data) read and write a JSON file. If a
    file is missing or corrupted, _load returns an empty dict instead
    of crashing - important on the very first run.


================================================================
7. signup.py  -  the password scrambler
================================================================

WHAT IT'S FOR
    One job: turn a real password into something safe to store. We
    never save the real password anywhere, not even in the waiting
    list - login2.request_account() scrambles it before writing.

password_funct(password, rounds=None) does three things:
    1. Pick a number of "rounds". On sign-up this is random (4 to
       100). On a later login check, we pass the SAME number back in
       so we get the same result.
    2. Run SHA-256 on the password that many times in a row. SHA-256
       is a standard one-way hash.
    3. Also walk the Fibonacci sequence that many steps and hash the
       number you land on. This is a second, independent fingerprint.

    Returns (rounds, fib_check, password_hash). All three get saved
    with the user.

WHY IT'S DONE THIS WAY
    - The random `rounds` acts like a "salt": two people with the same
      password get different stored hashes, because their round counts
      differ.
    - Doing 4-100 hash passes makes each check a little slow on
      purpose, which slows down anyone trying to guess passwords in
      bulk.
    - The Fibonacci hash is a small extra check - both fingerprints
      must match on login.

password_matches(typed_pw, rounds, fib_check, password_hash)
    Re-runs password_funct with the saved rounds and compares both
    fingerprints. Both equal -> correct password.

HONEST NOTE
    This is a learning exercise. A real app would use bcrypt or
    argon2, which are designed by cryptographers for exactly this.
    Don't copy this scheme into production.


================================================================
8. devices.py  -  the state of the house
================================================================

WHAT IT'S FOR
    Holding what the house looks like right now, and saving it so it
    survives a restart. There is ONE house, shared by everyone - if
    you flip the light on one laptop and refresh another, it moved.

    NOTE: devices are dynamic now - the house holds a LIST of device
    dicts, not three fixed booleans, and anyone can add / remove their
    own. The current shape and the full picture are in
    docs/ARCHITECTURE.md (section 3). The gist below still holds.

WHERE IT LIVES
    data/devices.json, roughly:
        {
          "devices": [
            {"id":"light","name":"Living Room Light","type":"toggle","on":false},
            {"id":"door","name":"Main Door","type":"lock","locked":true},
            {"id":"desk-lamp","name":"Desk Lamp","type":"dimmer","on":true,"level":40}
          ],
          "activity": [ ...last 12 actions... ]
        }
    type is "toggle" (on), "lock" (locked) or "dimmer" (on + level 0-100).
    light / fan / door are "builtin" and can't be removed; get_state()
    also mirrors them onto the old flat keys so nothing older breaks.

THE FUNCTIONS app.py CALLS
    get_state()                   the whole house, for drawing the page
    set_device(id, value, who)    drive one device (or "all")
    all_devices(on, who)          flip every toggle + dimmer (not locks)
    add_device(spec, who)         create a device from {name,room,type,icon}
    remove_device(id, who)        delete a device the user added
    apply(intent_dict, who)       take an instruction from intent.py
                                  and carry it out
    catalog()                     device metadata for intent.py + voice
    clear_activity(who)           empty the activity log
    reset()                       back to the starting state (seed.py
                                  uses this)

THE ACTIVITY LOG
    Every change adds one line to the top of house["activity"] via
    _log(): who did what, an icon name, and a HH:MM timestamp (local
    clock - friendlier during a demo than UTC). The list is trimmed to
    the last 12 entries.

HOW A SAVE WORKS
    _save() writes the ENTIRE file every time. Simple, and totally
    fine at this size. If two laptops save at the exact same moment,
    the last one wins - acceptable for a demo, not for real hardware.


================================================================
9. intent.py  -  turning a sentence into an instruction
================================================================

WHAT IT'S FOR
    This is the "understanding" step. It reads a sentence and decides
    what the person wants. It does NOT touch any device - it just
    returns a description of the request.

    There is no machine learning here. It's keyword matching plus a
    few rules. That's on purpose: for a fixed set of commands, this is
    more reliable than a big model, and you can read the whole thing.

THE WORD LISTS (near the top of the file)
    DEVICE_WORDS      "lamp", "bulb", "light"  -> "light"
                      "cooler", "fan"          -> "fan"
                      "gate", "lock", "door"   -> "door"
    TURN_ON_WORDS     on, start, begin, enable, activate
    TURN_OFF_WORDS    off, stop, disable, shut, kill
    OPEN_WORDS        open, unlock, unlatch
    CLOSE_WORDS       close, lock, shut, latch
    EVERYTHING_WORDS  everything, all, every

parse(text) returns a dict that ALWAYS has "ok" and "say":
    ok       True if it understood, False if not
    action   "on" / "off" / "lock" / "unlock"  (None if not understood)
    targets  which devices, e.g. ["light", "fan"]
    say      a short friendly sentence to show or speak, in EVERY case
             including failures ("Which device? Try 'turn off the fan'.")

THE RULES
    - Strip out punctuation, lowercase, split into words.
    - Find any device words. "everything" means light + fan (not the
      door - you don't want "turn everything off" unlocking the door).
    - If the only device is the door, look for lock/unlock words.
    - Otherwise (light / fan) work out on vs off. If the sentence says
      both, or neither, return ok=False with a question.

    parse("could you switch off the fan")
      -> {"ok": True, "action": "off", "targets": ["fan"],
          "say": "Turning the fan off"}

devices.apply() is what takes this dict and actually flips things.


================================================================
10. voice.py  -  offline speech in and out
================================================================

WHAT IT'S FOR
    The whole voice pipeline on the Python side. It's optional - if
    the models or ffmpeg aren't installed, the app quietly falls back
    to the browser's own speech engine.

    Two open-source tools do the heavy lifting, both free, both run
    entirely on your machine:
      Vosk   - Speech-To-Text (your voice -> words)
      Piper  - Text-To-Speech (words -> a natural-sounding voice)

    It also needs `ffmpeg` (a command-line audio tool) to convert the
    microphone recording into the format Vosk wants, and to nudge the
    Piper voice's pitch.

status()
    Reports what's actually available: {stt, tts, ffmpeg, ready,
    pitch, hint}. The front-end calls this to decide which voice
    engine to use, and shows the "hint" text to explain any gap.

transcribe(audio_bytes)  ->  text
    1. ffmpeg converts the browser's recording to 16kHz mono audio.
    2. A "grammar-locked" pass: Vosk is told it may ONLY recognise the
       words our commands use (that word list is built automatically
       from intent.py, so the two can never drift apart). This is a
       huge accuracy win for "turn on the light" style phrases.
       - It asks for the 3 best guesses and takes the first that
         parses as a real command.
       - It also tries a fuzzy repair: snap near-miss words to known
         ones ("fam" -> "fan") using difflib.
    3. If none of that produced a command, a normal free-form pass
       runs, so a general question still gets transcribed.

answer(text, who)  ->  {reply, house, ok, kind}
    The "brain". In order:
      1. Run the text through intent.parse(). If it's a device
         command -> do it, return kind="device".
      2. Otherwise, if SMARTHOME_CHATBOT_URL is set, POST the text
         there and use its reply -> kind="chat". (This is the hook to
         plug in a separate chatbot / assistant later.)
      3. Otherwise a canned "I can do lights, fan and the door" line
         -> kind="unknown".

synthesize(text)  ->  WAV audio bytes
    Piper turns the text into speech, then ffmpeg raises the pitch a
    touch (SMARTHOME_TTS_PITCH, default 1.06) so it sounds warmer and
    less flat. The result is a plain WAV any browser can play.

handle(audio_bytes, who)  ->  everything
    The full round trip for POST /api/voice: transcribe -> answer ->
    synthesize the reply. Returns the text it heard, the reply, the
    new house state, and the reply audio (or None if TTS isn't set up,
    in which case the browser speaks it instead).

TUNING KNOBS (environment variables)
    SMARTHOME_TTS_PITCH     voice pitch (1.0 = off, 1.06 = default)
    SMARTHOME_TTS_PACE      speaking speed (>1 slower, <1 faster)
    SMARTHOME_VOICE_GRAMMAR set to 0 to disable the grammar lock
    SMARTHOME_CHATBOT_URL   endpoint for non-command questions


================================================================
11. voice_setup.py  -  download the models, once
================================================================

WHAT IT'S FOR
    The Vosk and Piper model files are large and are NOT in git. This
    script downloads them into data/models/ one time.

    python voice_setup.py            get both models if missing
    python voice_setup.py --force    re-download even if present
    python voice_setup.py --big      larger, more accurate STT model

WHAT YOU NEED FIRST
    pip install -r requirements.txt   (installs the vosk + piper packages)
    ffmpeg on your PATH               (Arch: sudo pacman -S ffmpeg)

WHAT IT FETCHES
    data/models/vosk/          ~40 MB  speech-to-text (English)
    data/models/piper/voice.*  ~63 MB  text-to-speech (a warm US voice)

    --big swaps in a 128 MB Vosk model that's better at free-form
    speech but can't use the command grammar, so it's only worth it
    once a chatbot is wired in.

    After this runs, the entire voice path works with no internet.


================================================================
12. seed.py  -  start from a clean slate
================================================================

WHAT IT'S FOR
    Wipe the databases and create one starter admin so somebody can
    log in and approve everyone else.

        python seed.py

    Creates:  username: admin   password: admin123
    (Change FIRST_ADMIN / FIRST_PASSWORD at the top before a real demo.)

    It also calls devices.reset() so the house starts blank: light and
    fan off, door locked, no activity history.

    main.py runs this automatically the first time it sees an empty
    users.json, so you usually don't call it by hand unless you want a
    reset (or use `python main.py --reset`).


================================================================
13. tts.py  -  a standalone speech helper (NOT wired into the app)
================================================================

WHAT IT IS
    An earlier, self-contained Text-To-Speech module with its own
    TextToSpeech class. It supports two engines:
      offline -> pyttsx3   (works instantly, robotic voice)
      online  -> gTTS      (needs internet, Google's nicer voice)

WHY IT'S SEPARATE
    The live app uses voice.py (Vosk + Piper) for speech, not this
    file. tts.py is kept because it's a clean, simple example of the
    "text -> audio" step and was useful while prototyping. If you're
    working on the app's voice features, look at voice.py, not here.


================================================================
14. web/  -  the browser side
================================================================

index.html + auth.js  (the login / sign-up page)
    - Splits into two views: "Welcome back" (login) and "Ask for an
      account" (sign-up). Buttons swap between them; no page reload.
    - On load, auth.js checks localStorage - if you're already logged
      in it jumps to the dashboard.
    - It calls GET /api/config to see if developer mode is on, and if
      so shows a badge and relaxes the password rules.
    - Sign-up has a password strength meter (weak/fair/good/strong)
      computed in the browser from length and character variety.
    - The little arrows on the green panel swing to point at your
      mouse - pure decoration (atan2 on mousemove).
    - On successful login it stores the user in localStorage as
      "smarthome_user" and loads dashboard.html.

dashboard.html + dashboard.js  (the control panel)
    - First thing it does: read "smarthome_user" from localStorage. No
      session -> bounce back to the login page.
    - render(house) draws the three device cards, the activity feed,
      and the "N on" count. It only animates a device when that device
      actually changed, so the 5-second refresh doesn't keep
      re-triggering animations.
    - The page goes dark when the light is off (the room is dark) -
      that's the body.dark class, which style.css uses to swap colours.
    - Buttons call POST /api/devices/set. The typed box calls
      POST /api/command.
    - Polling: GET /api/devices every 5s, the pending list every 8s.
      This is how two browsers stay in sync without websockets.

    VOICE on the front-end - it picks one of two engines automatically:
      "server"  - records with MediaRecorder, sends the audio to
                  POST /api/voice, gets back text + a spoken reply.
                  Used when /api/voice/status says the offline engine
                  is ready.
      "browser" - the browser's built-in Web Speech API turns your
                  words into text locally, then the text goes to
                  /api/command. Used as a fallback (needs Chrome/Edge).
      "off"     - no speech support at all -> the mic button disables
                  itself and you type instead.

    A small audio meter watches the microphone level and auto-stops
    recording about 1.6 seconds after you stop talking (with a 10s
    hard cap). The red "Listening..." / amber "Thinking..." pop-up is
    the showListening() function.

style.css  (all the styling)
    - A warm "paper and ink" theme: cream background, dark brown text,
      one terracotta accent colour, forest green on the brand panel.
    - Colours are defined once as CSS variables on :root. body.dark
      just redefines those variables, so the whole page re-themes when
      the light turns off.
    - body.auth (the login page) has an extra cozy background: warm
      lamp/hearth glows plus a faint quilt-stitch texture.
    - Each device has its own motion: the light flickers then glows,
      the fan blades spin, the door bolt "clunks" across.


================================================================
15. data/  -  where state lives
================================================================

    data/users/users.json     approved accounts. Each record has:
                              username, rounds, fib_check, password
                              (the hash), is_locked, failed_attempts,
                              cooldown_until, approved_by, approved_at,
                              last_login.
    data/users/pending.json   same shape, minus the login-tracking
                              fields, plus requested_at.
    data/users/settings.json  {"dev_mode": true/false} - git-ignored.
    data/devices.json         the single shared house (section 8).
    data/models/              downloaded Vosk + Piper files, git-ignored.

    All of these are plain JSON. You can open them in an editor to see
    exactly what the app thinks is true, and `git diff` shows what
    changed. That's a big part of why there's no real database.


================================================================
16. archive/adminconnection.py  -  DO NOT RUN
================================================================

    This was an earlier, standalone login experiment. It's kept only
    for reference and is deliberately outside the project root.

    It is dangerous to run because it expects a DIFFERENT, incompatible
    layout for users.json:
        adminconnection.py wants: {admins: [], users: {}, signup_requests: {}}
        the live app wants:       {username: {rounds, fib_check, ...}}

    Worse, its load_data() auto-migrates and OVERWRITES users.json the
    moment it's imported - which would corrupt the real accounts file.
    That's why it lives in archive/ with its own README warning.

    If you ever see an import of `adminconnection` in the live code,
    that's a bug - remove it.


================================================================
17. RUNNING IT ACROSS YOUR WIFI  (one host, many devices)
================================================================

THE IDEA
    Run the app on ONE computer (the "host"). Everyone else - phones,
    other laptops - opens it in a browser over the same wifi and
    controls the same house. They stay in sync because every
    dashboard polls the server every few seconds (section 14).

IT ALREADY LISTENS EVERYWHERE
    app.serve() binds to ("", port), and "" means "every network
    interface", not just localhost. So the moment the server is up,
    other devices can already reach it - there was never a setting to
    flip. What was missing was just *telling you the address*.

    On startup the server now prints something like:

        On this computer:   http://localhost:8000
        On phones / laptops on the same wifi:
            http://192.168.1.24:8000

    Type that 192.168.x.x address into the other device's browser.
    (_lan_ips() in app.py finds it by opening a throwaway UDP socket
    toward 8.8.8.8 and reading back which local address the OS chose -
    no packets are actually sent.)

WHAT WORKS OVER PLAIN HTTP
    Buttons, typed commands, the activity feed, login, the invites
    tab - everything except the microphone.

WHY THE MIC NEEDS HTTPS
    Browsers only allow a page to use the microphone if the page is a
    "secure context": that means https://, OR plain http on localhost.
    A phone loading http://192.168.1.24:8000 is neither, so the mic
    button disables itself there (dashboard.js checks
    window.isSecureContext). Buttons and typing still work.

    To get voice on the other devices too:

        python main.py --https

    This makes a self-signed certificate once (data/lan-cert.pem, via
    the `openssl` command) and serves over https. The cert lists this
    machine's IPs as "Subject Alternative Names" - Android Chrome
    rejects a cert without them.

    Each device shows a "your connection is not private" warning the
    first time - expected for a self-signed cert. Tap Advanced ->
    proceed. After that the mic button works and will ask for
    microphone permission (allow it).

MIC STILL NOT WORKING ON ANDROID - CHECKLIST
    1. Are you on the https:// address, not http://?  The page must
       show https in the address bar.
    2. Did you accept the certificate warning (Advanced -> proceed)?
       If Android won't let you proceed, delete data/lan-*.pem on the
       host and restart with --https so the cert is regenerated for
       your current wifi IP.
    3. When you tap the mic, does Android ask for microphone
       permission? Allow it. If it never asks, you probably denied it
       before: Android Settings -> Apps -> Chrome -> Permissions ->
       Microphone, or the site settings (padlock/‹i› in the address
       bar -> Permissions).
    4. The dashboard now shows the real reason under the mic when it
       fails ("Mic: mic permission was denied", "needs https", etc.) -
       read that line, it says what's wrong.
    5. Chrome, not a random in-app browser. The Facebook / Instagram
       in-app browser and some others block getUserMedia entirely.
    6. If you literally cannot use https: Android Chrome has
       chrome://flags -> "Insecure origins treated as secure" -> add
       http://<host-ip>:8000 -> Relaunch. Then plain http works too.
       (Desktop Chrome has the same flag.)

FINDING THE SERVER WITHOUT TYPING AN IP  (discovery.py)
    Typing 10.180.x.x by hand is annoying. So the server also runs a
    "beacon": a tiny UDP socket (port 8001) that just listens.

    On another laptop that has this repo:

        python main.py --find

    That shouts one short message to the whole network ("anyone a
    Sync-Ghar server?"). Every server that hears it shouts back its
    name and address, and --find prints them:

        Found 1 Sync-Ghar server(s):
            http://10.180.40.222:8000   - pranjal-laptop

    How the pieces line up:
      discovery.py       Beacon (the listener) + discover() (the shouter)
      app.serve()        starts a Beacon unless you pass --no-discovery
      GET /api/discover  runs discover() and returns the list as JSON,
                         in case you want to show it in the web UI
      python discovery.py   same as --find, standalone

    Note: a browser can't do this itself (JavaScript can't send UDP
    broadcasts), so discovery is a terminal tool. Once --find gives you
    the URL, you still open that URL in the browser normally.

    Discovery needs UDP port 8001 open on the host, same firewall note
    as below.

IF IT WON'T CONNECT FROM ANOTHER DEVICE
    - Both devices must be on the SAME wifi (and not a "guest" network
      that isolates clients).
    - A firewall on the host can block port 8000 (and UDP 8001 for
      discovery). On Arch, if you run one:  sudo ufw allow 8000
      and  sudo ufw allow 8001/udp
    - Corporate / campus wifi often blocks device-to-device traffic
      entirely. A phone hotspot is an easy way around that for a demo.

SECURITY REALITY CHECK
    There is still no real authentication (section 1 / the auth model
    is "the browser says who it is and the server believes it"). On a
    trusted home wifi that's fine for a demo. Do not put this on the
    open internet.


================================================================
18. COMMON QUESTIONS
================================================================

Q: I changed a .py file and nothing happened.
   Stop the server (Ctrl+C) and run `python main.py` again. There's no
   auto-reload.

Q: The mic button is greyed out.
   Either you're not on Chrome/Edge, or getUserMedia was blocked.
   Typing always works. For the offline engine, run voice_setup.py and
   make sure ffmpeg is installed.

Q: "Address already in use" on startup.
   Another copy of the server is still running.
   `pkill -f app.py` then try again, or `python main.py --port 9000`.

Q: I forgot the admin password.
   `python main.py --reset` wipes everything back to admin / admin123.
   (This also clears all other accounts and the house state.)

Q: Where do I add a new device (say, a heater)?
   You don't touch the code - tap "Add device" on the dashboard, pick a
   name, room, type (on/off, lock or dimmer) and an icon. It's saved for
   everyone and voice/typing pick it up by name.
   To add a whole new device *type*, see docs/ARCHITECTURE.md section 7.

Q: Why is every approved user an admin?
   A hackathon shortcut - it removed a whole "roles" system we didn't
   have time for. Real roles are on the roadmap.
"""

SECTIONS = [
    "0.  The 60-second version",
    "1.  The shape of the project",
    "2.  Plain-English glossary",
    "3.  The request lifecycle (what happens on page load)",
    "4.  main.py   - the launcher",
    "5.  app.py    - the web server + API",
    "6.  login2.py - accounts, approval, login",
    "7.  signup.py - the password scrambler",
    "8.  devices.py - the state of the house",
    "9.  intent.py - sentence -> instruction",
    "10. voice.py  - offline speech in and out",
    "11. voice_setup.py - download the models",
    "12. seed.py   - start from a clean slate",
    "13. tts.py    - standalone helper (not used by the app)",
    "14. web/      - the browser side",
    "15. data/     - where state lives",
    "16. archive/adminconnection.py - do not run",
    "17. Running it across your wifi (one host, many devices)",
    "18. Common questions",
]

if __name__ == "__main__":
    print(__doc__.strip().split("\n")[0])
    print("\nOpen this file in an editor and read the section you need:\n")
    for line in SECTIONS:
        print("   " + line)
    print("\n(It's all in the docstring at the top of theory.py.)")
