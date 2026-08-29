/* dashboard.js - the control panel.
   devices are dynamic now: the server hands back a `devices` array and
   this file draws a card per device. voice: browser Web Speech turns
   words into text; if it's not supported the mic is disabled and typing
   still works. either way the server's intent.py decides what it means. */

const $ = (id) => document.getElementById(id);
const API = location.protocol === "file:" ? "http://localhost:8000" : "";

/* session */
let user = null;
try { user = JSON.parse(localStorage.getItem("smarthome_user")); } catch (e) {}
if (!user || !user.username) {
  localStorage.removeItem("smarthome_user");
  location.replace("index.html");
  throw new Error("no session");
}
$("who").textContent = user.username;
$("role").textContent = user.is_admin ? "admin" : "member";
$("avatar").textContent = user.username.charAt(0).toUpperCase();
$("welcomeName").textContent = user.username;

/* server helpers */
async function getJSON(path) {
  try { return await (await fetch(API + path)).json(); }
  catch (e) { return { ok: false, offline: true }; }
}
async function post(path, body) {
  try {
    return await (await fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })).json();
  } catch (e) {
    return { ok: false, offline: true, message: "Can't reach the server - is app.py running?" };
  }
}

/* ===== drawing the house ===== */
/* old activity entries stored an icon *key*; newer ones store the emoji */
const LEGACY_ICONS = { light: "💡", fan: "🌀", lock: "🔒", unlock: "🔓", bulk: "⚡", night: "🌙", info: "•" };
let house = { devices: [], activity: [], light: false, fan: false, door_locked: true };

function isOn(d) {
  if (d.type === "lock") return !d.locked;
  return !!d.on;
}
function stateLabel(d) {
  if (d.type === "lock") return d.locked ? "LOCKED" : "UNLOCKED";
  if (d.type === "dimmer" && d.on) return d.level + "%";
  return d.on ? "ON" : "OFF";
}
function actionLabel(d) {
  if (d.type === "lock") return d.locked ? "Unlock" : "Lock";
  return d.on ? "Turn Off" : "Turn On";
}

function render(h) {
  if (!h) return;
  const prev = house;
  house = h;

  buildDevices(h.devices || [], prev.devices || []);

  const appliances = (h.devices || []).filter((d) => d.type !== "lock");
  const onCount = appliances.filter((d) => d.on).length;
  $("deviceCount").textContent = onCount + " of " + (h.devices || []).length + " on";

  // only the living-room light sets the room's mood
  document.body.classList.toggle("dark", !h.light);

  drawLog(h.activity || []);
}

function buildDevices(list, prevList) {
  const box = $("devices");
  const prevById = {};
  (prevList || []).forEach((d) => { prevById[d.id] = d; });
  box.innerHTML = "";

  if (!list.length) {
    box.innerHTML = '<div class="empty">No devices yet - tap "Add device".</div>';
    return;
  }

  list.forEach((d) => {
    const card = document.createElement("article");
    card.className = "device";
    card.dataset.id = d.id;
    card.dataset.type = d.type;
    card.classList.toggle("on", isOn(d));
    card.classList.toggle("locked", d.type === "lock" && d.locked);

    const rail = document.createElement("span");
    rail.className = "rail";

    const top = document.createElement("div");
    top.className = "device-top";
    const ic = document.createElement("div");
    ic.className = "device-icon";
    ic.textContent = d.icon || "🔌";
    const st = document.createElement("div");
    st.className = "state";
    st.classList.toggle("on", isOn(d) && d.type !== "lock");
    st.classList.toggle("unlocked", d.type === "lock" && !d.locked);
    st.textContent = stateLabel(d);
    top.append(ic, st);

    const h3 = document.createElement("h3");
    h3.textContent = d.name;
    const room = document.createElement("p");
    room.textContent = d.room || " ";

    card.append(rail, top, h3, room);

    if (d.type === "dimmer") {
      const slider = document.createElement("input");
      slider.type = "range";
      slider.className = "dim";
      slider.min = 0; slider.max = 100; slider.step = 5;
      slider.value = d.on ? d.level : 0;
      slider.oninput = () => { valLabel.textContent = slider.value + "%"; };
      slider.onchange = () => setDevice(d.id, Number(slider.value));
      const valLabel = document.createElement("div");
      valLabel.className = "dim-val";
      valLabel.textContent = (d.on ? d.level : 0) + "%";
      card.append(slider, valLabel);
    }

    const btn = document.createElement("button");
    btn.className = "device-act";
    btn.textContent = actionLabel(d);
    btn.onclick = () => {
      if (d.type === "lock") setDevice(d.id, !d.locked);
      else setDevice(d.id, !d.on);
    };
    card.append(btn);

    if (!d.builtin) {
      const del = document.createElement("button");
      del.className = "device-del";
      del.textContent = "✕";
      del.title = "Remove this device";
      del.onclick = () => removeDevice(d.id, d.name);
      card.append(del);
    }

    box.append(card);

    // one-shot animations, only when that device actually changed
    const was = prevById[d.id];
    if (was) {
      if (d.id === "light" && d.on && !was.on) playAnim(card, "flick");
      if (d.type === "lock" && d.locked !== was.locked) playAnim(card, "clunk");
    }
  });
}

function playAnim(el, name) {
  el.classList.remove("anim-flick", "anim-clunk");
  void el.offsetWidth;
  el.classList.add("anim-" + name);
}

function drawLog(items) {
  const box = $("log");
  if (!items.length) { box.innerHTML = '<div class="empty">no activity yet</div>'; return; }
  box.innerHTML = "";
  items.forEach((a) => {
    const row = document.createElement("div");
    row.className = "log-item";
    const left = document.createElement("div");
    left.className = "log-left";
    const ic = document.createElement("div");
    ic.className = "log-icon";
    ic.textContent = LEGACY_ICONS[a.icon] || a.icon || "•";
    const txt = document.createElement("span");
    // bold the last two words - matches the mockup ("... light on")
    const words = (a.text || "").split(" ");
    if (words.length > 2) {
      txt.append(words.slice(0, -2).join(" ") + " ");
      const b = document.createElement("b");
      b.textContent = words.slice(-2).join(" ");
      txt.append(b);
    } else {
      txt.textContent = a.text || "";
    }
    left.append(ic, txt);
    const t = document.createElement("span");
    t.className = "log-time";
    t.textContent = a.at || "";
    row.append(left, t);
    box.append(row);
  });
}

/* status line */
let statusTimer = null;
function setStatus(message, bad) {
  const el = $("status");
  el.textContent = message;
  el.className = "status show" + (bad ? " bad" : "");
  clearTimeout(statusTimer);
  statusTimer = setTimeout(() => { el.className = "status"; }, 3500);
}
function voiceNote(text) { $("voiceNote").textContent = text; }
function micStatus(text) { $("micStatus").textContent = text; }

/* ===== device actions ===== */
async function setDevice(device, value) {
  const data = await post("/api/devices/set", { username: user.username, device, value });
  if (data.offline) return setStatus(data.message, true);
  render(data.house);
}
async function removeDevice(id, name) {
  if (!confirm('Remove "' + name + '"?')) return;
  const data = await post("/api/devices/remove", { username: user.username, device: id });
  if (data.offline || !data.ok) return setStatus(data.message || "Could not remove that.", true);
  render(data.house);
  setStatus(data.message || "");
}
$("allOn").onclick    = () => setDevice("all", true);
$("allOff").onclick   = () => setDevice("all", false);
$("lockDoor").onclick = () => setDevice("door", true);

/* ===== add-device modal ===== */
let addType = "toggle";
let addIcon = "💡";

function openAdd() {
  $("addForm").reset();
  $("addNote").className = "note";
  addType = "toggle"; addIcon = "💡";
  document.querySelectorAll("#dType button").forEach((b) => b.classList.toggle("on", b.dataset.type === "toggle"));
  document.querySelectorAll("#dIcons button").forEach((b, i) => b.classList.toggle("on", i === 0));
  $("addModal").hidden = false;
  $("dName").focus();
}
function closeAdd() { $("addModal").hidden = true; }

$("addDeviceBtn").onclick = openAdd;
$("addCancel").onclick = closeAdd;
$("addModal").onclick = (e) => { if (e.target === $("addModal")) closeAdd(); };

document.querySelectorAll("#dType button").forEach((b) => {
  b.onclick = () => {
    addType = b.dataset.type;
    document.querySelectorAll("#dType button").forEach((x) => x.classList.toggle("on", x === b));
  };
});
document.querySelectorAll("#dIcons button").forEach((b) => {
  b.onclick = () => {
    addIcon = b.textContent;
    document.querySelectorAll("#dIcons button").forEach((x) => x.classList.toggle("on", x === b));
  };
});

$("addForm").onsubmit = async (e) => {
  e.preventDefault();
  const name = $("dName").value.trim();
  const room = $("dRoom").value.trim();
  if (name.length < 2) {
    $("addNote").textContent = "Give the device a name (2+ characters).";
    $("addNote").className = "note show err";
    return;
  }
  const btn = $("addSubmit");
  btn.disabled = true; btn.textContent = "adding...";
  const data = await post("/api/devices/add", {
    username: user.username, name, room, type: addType, icon: addIcon,
  });
  btn.disabled = false; btn.textContent = "Add device";
  if (data.offline || !data.ok) {
    $("addNote").textContent = data.message || "Could not add that device.";
    $("addNote").className = "note show err";
    return;
  }
  closeAdd();
  render(data.house);
  setStatus(data.message || "Device added.");
};

/* typed command */
async function runText(text) {
  text = (text || "").trim();
  if (!text) return;
  $("heard").textContent = '"' + text + '"';
  const data = await post("/api/command", { username: user.username, text });
  if (data.offline) { showListening(null); return setStatus(data.message, true); }
  render(data.house);
  setStatus(data.message || "");
  showListening(null);
  speak(data.message || "");
}
$("cmdForm").onsubmit = (e) => {
  e.preventDefault();
  runText($("cmdInput").value);
  $("cmdInput").value = "";
};

/* clear log + logout */
$("clearLog").onclick = async () => {
  const data = await post("/api/activity/clear", { username: user.username });
  if (!data.offline) render(data.house);
};
$("viewAll").onclick = () => $("log").scrollIntoView({ behavior: "smooth" });
$("logout").onclick = () => {
  localStorage.removeItem("smarthome_user");
  location.replace("index.html");
};

/* tabs */
function showTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".page").forEach((p) => p.classList.toggle("active", p.id === "page-" + name));
  if (name === "invites") loadPending();
}
document.querySelectorAll(".tab").forEach((t) => { t.onclick = () => showTab(t.dataset.tab); });

/* invites */
function inviteBadge(n) {
  const b = $("inviteBadge");
  b.textContent = n;
  b.classList.toggle("show", n > 0);
}
async function loadPending() {
  const box = $("pending");
  const data = await post("/api/pending", { admin: user.username });
  if (!data.ok) { box.innerHTML = '<div class="empty">' + (data.message || "unavailable") + "</div>"; inviteBadge(0); return; }
  inviteBadge(data.pending.length);
  if (!data.pending.length) { box.innerHTML = '<div class="empty">Nobody is waiting right now.</div>'; return; }
  box.innerHTML = "";
  data.pending.forEach((name) => {
    const row = document.createElement("div");
    row.className = "pending";
    const label = document.createElement("span");
    label.textContent = name;
    const btns = document.createElement("div");
    btns.className = "btns";
    const yes = document.createElement("button");
    yes.className = "mini yes"; yes.textContent = "accept";
    yes.onclick = () => decide("/api/approve", name);
    const no = document.createElement("button");
    no.className = "mini no"; no.textContent = "decline";
    no.onclick = () => decide("/api/reject", name);
    btns.append(yes, no);
    row.append(label, btns);
    box.append(row);
  });
}
async function decide(path, name) {
  await post(path, { admin: user.username, username: name });
  loadPending();
}
$("refreshInvites").onclick = loadPending;

/* dev mode toggle */
async function refreshDevMode() {
  const cfg = await getJSON("/api/config");
  const on = !!(cfg && cfg.dev_mode);
  $("devToggle").checked = on;
  $("inviteNote").textContent = on
    ? "Developer mode is ON - new sign-ups are approved automatically, so this list stays empty."
    : "Accept someone and they can log in. Decline drops their request.";
}
$("devToggle").onchange = async () => {
  const data = await post("/api/devmode", { admin: user.username, on: $("devToggle").checked });
  if (data.offline || !data.ok) {
    setStatus(data.message || "Could not change developer mode.", true);
  } else {
    setStatus(data.message || "");
  }
  refreshDevMode();
  loadPending();
};

/* ===== VOICE =====
   two engines, picked automatically:
     "server"  - offline Vosk + Piper on the python side, no internet.
     "browser" - the browser's own Web Speech API. fallback. */
let voiceEngine = "browser";
let serverTTS = false;
let recording = false;
let mediaRec = null;
let lastVoiceStatus = null;

const browserSpeech = () => window.SpeechRecognition || window.webkitSpeechRecognition;

function voiceDiag() {
  const s = lastVoiceStatus || {};
  const rows = [
    "address:          " + location.href,
    "secure context:   " + window.isSecureContext + (window.isSecureContext ? "" : "   <- mic needs this true"),
    "page mic access:  " + !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia),
    "can record audio: " + (typeof MediaRecorder !== "undefined"),
    "browser speech:   " + !!browserSpeech(),
    "engine picked:    " + voiceEngine,
    "server STT ready: " + (s.stt ?? "?"),
    "server TTS ready: " + (s.tts ?? "?"),
    "server note:      " + (s.hint || "?"),
    "",
    navigator.userAgent,
  ];
  alert("VOICE DIAGNOSTICS\n(screenshot this)\n\n" + rows.join("\n"));
}

function micOn(on) {
  recording = on;
  $("mic").classList.toggle("rec", on);
  micStatus(on ? "listening - speak your command" : "Tap to speak");
  if (!on) showListening(null);
}

function showListening(mode) {
  const o = $("listenOverlay");
  if (!o) return;
  if (!mode) { o.hidden = true; return; }
  o.hidden = false;
  o.className = "listen-overlay " + mode;
  o.querySelector(".listen-text").textContent =
    mode === "thinking" ? "Thinking..." : "Listening...";
}

let ttsAudio = null;
async function speak(text) {
  text = (text || "").trim();
  if (!text) return;
  if (ttsAudio) { ttsAudio.pause(); ttsAudio = null; }
  window.speechSynthesis && window.speechSynthesis.cancel();

  if (serverTTS) {
    try {
      const r = await fetch(API + "/api/voice/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (r.ok) {
        const url = URL.createObjectURL(await r.blob());
        ttsAudio = new Audio(url);
        ttsAudio.onended = () => URL.revokeObjectURL(url);
        ttsAudio.play();
        return;
      }
    } catch (e) { /* fall back to the browser voice */ }
  }
  browserSpeak(text);
}

function browserSpeak(text) {
  if (!window.speechSynthesis) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "en-US";
  u.rate = 1.0;
  u.pitch = 1.15;
  const voices = speechSynthesis.getVoices();
  const nice = voices.find((v) => /natural|neural|google|samantha|aria|jenny/i.test(v.name))
            || voices.find((v) => v.lang && v.lang.startsWith("en"));
  if (nice) u.voice = nice;
  speechSynthesis.speak(u);
}
function playB64Wav(b64) {
  if (ttsAudio) { ttsAudio.pause(); ttsAudio = null; }
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: "audio/wav" }));
  ttsAudio = new Audio(url);
  ttsAudio.onended = () => URL.revokeObjectURL(url);
  ttsAudio.play();
}

/* engine 1: server (offline Vosk + Piper) */
let micStream = null;
let listenCtx = null;
let listenRAF = 0;
let hardStop = 0;

function pickMime() {
  const want = ["audio/webm;codecs=opus", "audio/webm",
                "audio/ogg;codecs=opus", "audio/mp4", "audio/aac"];
  for (const t of want) {
    if (window.MediaRecorder && MediaRecorder.isTypeSupported(t)) return t;
  }
  return "";
}

async function startServerMic() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    return setStatus("This browser won't give the page a microphone here. "
                     + "Open the https:// address (python main.py --https).", true);
  }
  try {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch (e) {
    const why = {
      NotAllowedError: "mic permission was denied - allow it for this site, then reload",
      NotFoundError: "no microphone found on this device",
      NotReadableError: "the mic is busy in another app",
      SecurityError: "the page isn't secure - open the https:// address",
      NotSupportedError: "needs https - open the https:// address",
      AbortError: "the mic could not start - try again",
    }[e.name] || (e.name + ": " + (e.message || "mic error"));
    return setStatus("Mic: " + why, true);
  }
  const chunks = [];
  const mime = pickMime();
  try {
    mediaRec = mime ? new MediaRecorder(micStream, { mimeType: mime })
                    : new MediaRecorder(micStream);
  } catch (e) {
    return setStatus("This browser can't record audio - try Chrome or Edge.", true);
  }

  mediaRec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
  mediaRec.onstart = () => {
    micOn(true);
    showListening("listening");
    $("heard").textContent = "listening...";
  };
  mediaRec.onstop = async () => {
    stopListenMeter();
    micStream && micStream.getTracks().forEach((t) => t.stop());
    micOn(false);
    if (!chunks.length) { setStatus("Didn't catch anything - try again.", true); return; }

    showListening("thinking");
    $("heard").textContent = "thinking...";
    const blob = new Blob(chunks, { type: mediaRec.mimeType || mime || "audio/webm" });
    try {
      const r = await fetch(API + "/api/voice?user=" + encodeURIComponent(user.username), {
        method: "POST",
        headers: { "Content-Type": blob.type || "application/octet-stream" },
        body: blob,
      });
      const data = await r.json().catch(() => ({}));
      showListening(null);
      if (!r.ok && !data.text) {
        return setStatus(data.message || "Voice failed on the server.", true);
      }
      $("heard").textContent = data.text ? '"' + data.text + '"' : "(didn't catch that)";
      if (data.house) render(data.house);
      if (data.reply) setStatus(data.reply, data.ok === false);
      if (data.audio_b64) playB64Wav(data.audio_b64);
      else if (data.reply) browserSpeak(data.reply);
    } catch (e) {
      showListening(null);
      setStatus("Can't reach the server - is it still running?", true);
    }
  };

  mediaRec.start();
  listenMeter(micStream);
  hardStop = setTimeout(stopServerMic, 10000);
}

function stopServerMic() {
  clearTimeout(hardStop);
  if (mediaRec && mediaRec.state === "recording") mediaRec.stop();
}

function listenMeter(stream) {
  try {
    listenCtx = new (window.AudioContext || window.webkitAudioContext)();
    listenCtx.resume && listenCtx.resume().catch(() => {});
    const src = listenCtx.createMediaStreamSource(stream);
    const an = listenCtx.createAnalyser();
    an.fftSize = 512;
    src.connect(an);
    const buf = new Uint8Array(an.fftSize);
    let spoke = false;
    let lastLoud = performance.now();
    const tick = () => {
      an.getByteTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v; }
      const rms = Math.sqrt(sum / buf.length);
      const now = performance.now();
      if (rms > 0.02) { spoke = true; lastLoud = now; }
      if (spoke && now - lastLoud > 1600) return stopServerMic();
      if (!spoke && now - lastLoud > 6000) return stopServerMic();
      listenRAF = requestAnimationFrame(tick);
    };
    listenRAF = requestAnimationFrame(tick);
  } catch (e) { /* no analyser - the 10s hard stop still covers it */ }
}
function stopListenMeter() {
  if (listenRAF) cancelAnimationFrame(listenRAF);
  listenRAF = 0;
  if (listenCtx) { listenCtx.close().catch(() => {}); listenCtx = null; }
}

/* engine 2: browser Web Speech API */
function startBrowserMic() {
  const SR = browserSpeech();
  const rec = new SR();
  rec.lang = "en-IN";
  rec.interimResults = true;
  window._rec = rec;
  rec.onstart = () => { micOn(true); showListening("listening"); $("heard").textContent = "listening..."; };
  rec.onend = () => micOn(false);
  rec.onerror = (e) => {
    const msgs = {
      "not-allowed": "Mic permission was denied - allow it for this site, then reload.",
      "service-not-allowed": "This browser's speech service is blocked here - try the https:// address.",
      "no-speech": "Didn't hear anything - tap the mic and try again.",
      "audio-capture": "No microphone found.",
      "network": "The browser speech engine needs internet. For offline voice, use the https:// address so the server engine kicks in.",
    };
    if (e.error !== "aborted") setStatus(msgs[e.error] || ("Voice error: " + e.error), true);
  };
  rec.onresult = (e) => {
    let text = "";
    for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript;
    text = text.trim();
    $("heard").textContent = text ? '"' + text + '"' : "...";
    if (e.results[e.results.length - 1].isFinal && text) { showListening("thinking"); runText(text); }
  };
  try { rec.start(); } catch (e) {
    setStatus("Couldn't start the mic: " + (e.message || e.name), true);
  }
}

$("mic").onclick = () => {
  if (recording) {
    if (voiceEngine === "server") stopServerMic();
    else if (voiceEngine === "browser" && window._rec) window._rec.stop();
    return;
  }
  if (voiceEngine === "server") startServerMic();
  else if (voiceEngine === "browser") startBrowserMic();
};

$("voiceCheck").onclick = voiceDiag;

async function setupVoice() {
  let st = null;
  try { st = await getJSON("/api/voice/status"); } catch (e) {}
  lastVoiceStatus = st;
  serverTTS = !!(st && st.tts);

  if (!window.isSecureContext) {
    voiceEngine = "off";
    $("mic").disabled = true;
    micStatus("voice needs the https:// address");
    voiceNote("The mic only works on https (or on the host computer itself). "
              + "On the host run  python main.py --https , then open the https:// "
              + "address it prints. Typing works here now.");
    return;
  }

  if (st && st.stt && window.MediaRecorder && navigator.mediaDevices) {
    voiceEngine = "server";
    voiceNote("Voice control is ready - tap the mic and speak. (offline engine)");
  } else if (browserSpeech()) {
    voiceEngine = "browser";
    voiceNote(st && st.hint ? st.hint : "Voice control is ready - tap the mic and speak.");
  } else {
    voiceEngine = "off";
    $("mic").disabled = true;
    micStatus("voice needs Chrome or Edge");
    voiceNote("Type your commands instead - that always works.");
  }
}

/* ===== START ===== */
async function refresh() {
  const data = await getJSON("/api/devices");
  if (data && data.house) render(data.house);
}

/* say "Welcome to Sync-Ghar" once, right after a fresh login. auth.js
   drops a sessionStorage flag on the way over. browsers can block audio
   until the first interaction, so we also retry on the first tap/key. */
function maybeGreet() {
  let want = false;
  try { want = sessionStorage.getItem("syncghar_greet") === "1"; } catch (e) {}
  if (!want) return;
  try { sessionStorage.removeItem("syncghar_greet"); } catch (e) {}

  const phrase = "Welcome to Sync-Ghar, " + user.username + ".";
  setStatus(phrase);

  let done = false;
  const fire = () => { if (done) return; done = true; cleanup(); speak(phrase); };
  const cleanup = () => {
    document.removeEventListener("pointerdown", fire);
    document.removeEventListener("keydown", fire);
  };
  document.addEventListener("pointerdown", fire, { once: true });
  document.addEventListener("keydown", fire, { once: true });

  speak(phrase);
  // if that attempt actually produced sound, drop the retry listeners
  setTimeout(() => {
    if ((window.speechSynthesis && speechSynthesis.speaking) || ttsAudio) {
      done = true; cleanup();
    }
  }, 1000);
}

(async () => {
  const s = await post("/api/session", { username: user.username });
  if (s && s.ok === false && !s.offline) {
    localStorage.removeItem("smarthome_user");
    location.replace("index.html");
    return;
  }
})();

(async () => { await setupVoice(); maybeGreet(); })();
refresh();
refreshDevMode();
loadPending();
setInterval(refresh, 5000);
setInterval(loadPending, 8000);
