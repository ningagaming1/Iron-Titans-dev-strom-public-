/* -----------------------------------------------------------
   dashboard.js - the control panel.

   Voice path:
     * default        -> record a clip, send to /api/voice,
                         which uses Google Speech-to-Text
     * no API key     -> fall back to the browser's own speech
     * neither works  -> mic is disabled, typing still works

   Whatever produces the text, the server's intent.py decides
   what it means and devices.py flips the switch.
----------------------------------------------------------- */

const $ = (id) => document.getElementById(id);
const API = location.protocol === "file:" ? "http://localhost:8000" : "";

/* ---------- session ---------- */
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

/* ---------- server helpers ---------- */
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

/* ---------- drawing the house ---------- */
const ICONS = { light: "💡", fan: "🌀", lock: "🔒", unlock: "🔓", bulk: "⚡", night: "🌙", info: "•" };
let house = { light: false, fan: false, door_locked: true, activity: [] };

function render(h) {
  if (!h) return;
  house = h;
  card("light", h.light);
  card("fan", h.fan);
  $("doorState").textContent = h.door_locked ? "LOCKED" : "UNLOCKED";
  $("doorState").classList.toggle("on", h.door_locked);
  $("doorBtn").textContent = h.door_locked ? "Unlock Door" : "Lock Door";

  const applianceCount = (h.light ? 1 : 0) + (h.fan ? 1 : 0);
  $("deviceCount").textContent = applianceCount + " on";

  // every appliance off -> the house is asleep -> dark mode
  document.body.classList.toggle("dark", applianceCount === 0);

  drawLog(h.activity || []);
}
function card(name, on) {
  $(name + "State").textContent = on ? "ON" : "OFF";
  $(name + "State").classList.toggle("on", on);
  $(name + "Btn").textContent = on ? "Turn Off" : "Turn On";
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
    ic.textContent = ICONS[a.icon] || "•";
    const txt = document.createElement("span");
    txt.textContent = a.text;
    left.append(ic, txt);
    const t = document.createElement("span");
    t.className = "log-time";
    t.textContent = a.at || "";
    row.append(left, t);
    box.append(row);
  });
}

/* ---------- status line ---------- */
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

/* ---------- device buttons ---------- */
async function setDevice(device, value) {
  const data = await post("/api/devices/set", { username: user.username, device, value });
  if (data.offline) return setStatus(data.message, true);
  render(data.house);
}
$("lightBtn").onclick = () => setDevice("light", !house.light);
$("fanBtn").onclick   = () => setDevice("fan", !house.fan);
$("doorBtn").onclick  = () => setDevice("door", !house.door_locked);
$("allOn").onclick    = () => setDevice("all", true);
$("allOff").onclick   = () => setDevice("all", false);
$("lockDoor").onclick = () => setDevice("door", true);

/* ---------- typed command ---------- */
async function runText(text) {
  text = (text || "").trim();
  if (!text) return;
  $("heard").textContent = '"' + text + '"';
  const data = await post("/api/command", { username: user.username, text });
  if (data.offline) return setStatus(data.message, true);
  render(data.house);
  setStatus(data.message || "");
}
$("cmdForm").onsubmit = (e) => {
  e.preventDefault();
  runText($("cmdInput").value);
  $("cmdInput").value = "";
};

/* ---------- clear log + logout ---------- */
$("clearLog").onclick = async () => {
  const data = await post("/api/activity/clear", { username: user.username });
  if (!data.offline) render(data.house);
};
$("logout").onclick = () => {
  localStorage.removeItem("smarthome_user");
  location.replace("index.html");
};

/* ---------- tabs ---------- */
function showTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".page").forEach((p) => p.classList.toggle("active", p.id === "page-" + name));
  if (name === "invites") loadPending();
}
document.querySelectorAll(".tab").forEach((t) => { t.onclick = () => showTab(t.dataset.tab); });

/* ---------- invites ---------- */
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

/* ===========================================================
   VOICE
=========================================================== */
let voiceMode = "off";            // "google" | "browser" | "off"
const browserSpeech = () => window.SpeechRecognition || window.webkitSpeechRecognition;

function micOn(on) {
  $("mic").classList.toggle("rec", on);
  micStatus(on ? "listening... (tap to stop)" : "tap the mic or type");
}

/* ---- Google path: record a clip, send to /api/voice ---- */
let recorder = null;
let chunks = [];

async function googleMic() {
  if (recorder && recorder.state === "recording") { recorder.stop(); return; }

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    setStatus("Microphone blocked. Click the mic/lock icon in the address bar, allow it, then reload.", true);
    return;
  }

  chunks = [];
  recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
  recorder.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
  recorder.onstart = () => { micOn(true); $("heard").textContent = "listening..."; };
  recorder.onstop = async () => {
    micOn(false);
    stream.getTracks().forEach((t) => t.stop());
    $("heard").textContent = "thinking...";
    const b64 = await blobToBase64(new Blob(chunks, { type: "audio/webm" }));
    const data = await post("/api/voice", { username: user.username, audio: b64 });

    if (!data.ok) {
      $("heard").textContent = "-";
      setStatus(data.message || "Voice failed.", true);
      if (data.need_key && browserSpeech()) {
        voiceMode = "browser";
        voiceNote("No Google key - switched to the browser's speech engine.");
      }
      return;
    }
    $("heard").textContent = data.heard ? '"' + data.heard + '"' : "-";
    render(data.house);
    setStatus(data.message || "");
  };

  recorder.start();
  // stop on its own after 5s so one tap is enough
  setTimeout(() => { if (recorder && recorder.state === "recording") recorder.stop(); }, 5000);
}

function blobToBase64(blob) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(String(reader.result).split(",")[1] || "");
    reader.readAsDataURL(blob);
  });
}

/* ---- browser fallback: Web Speech API ---- */
function browserMic() {
  const SR = browserSpeech();
  const rec = new SR();
  rec.lang = "en-IN";
  rec.interimResults = true;
  rec.onstart = () => { micOn(true); $("heard").textContent = "listening..."; };
  rec.onend = () => micOn(false);
  rec.onerror = (e) => {
    const msgs = {
      "not-allowed": "Microphone blocked. Allow it in the address bar, then reload.",
      "no-speech": "Didn't hear anything - tap the mic and try again.",
      "audio-capture": "No microphone found.",
      "network": "The browser speech engine needs an internet connection.",
    };
    if (e.error !== "aborted") setStatus(msgs[e.error] || ("Voice error: " + e.error), true);
  };
  rec.onresult = (e) => {
    let text = "";
    for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript;
    text = text.trim();
    $("heard").textContent = text ? '"' + text + '"' : "...";
    if (e.results[e.results.length - 1].isFinal && text) runText(text);
  };
  try { rec.start(); } catch (e) {}
}

$("mic").onclick = () => {
  if (voiceMode === "google") googleMic();
  else if (voiceMode === "browser") browserMic();
};

async function setupVoice() {
  const cfg = await getJSON("/api/config");
  const canRecord = !!(navigator.mediaDevices &&
                       window.MediaRecorder &&
                       MediaRecorder.isTypeSupported("audio/webm"));

  if (cfg && cfg.voice && canRecord) {
    voiceMode = "google";
    voiceNote("Voice: Google Speech-to-Text");
  } else if (browserSpeech()) {
    voiceMode = "browser";
    voiceNote(cfg && cfg.voice
      ? "Voice: browser engine (this browser can't record audio for Google)."
      : "Voice: browser engine. Set GOOGLE_API_KEY to use Google Speech-to-Text.");
  } else {
    voiceMode = "off";
    $("mic").disabled = true;
    micStatus("voice needs Chrome or Edge");
    voiceNote("Type your commands instead - that always works.");
  }
}

/* ===========================================================
   START
=========================================================== */
async function refresh() {
  const data = await getJSON("/api/devices");
  if (data && data.house) render(data.house);
}

(async () => {
  const s = await post("/api/session", { username: user.username });
  if (s && s.ok === false && !s.offline) {
    localStorage.removeItem("smarthome_user");
    location.replace("index.html");
    return;
  }
  const cfg = await getJSON("/api/config");
  if (cfg && cfg.dev_mode) {
    $("inviteNote").textContent =
      "Developer mode is ON, so new sign-ups are let in automatically - this list stays empty. " +
      "Turn DEV_MODE off in login2.py to use invites for real.";
  }
})();

setupVoice();
refresh();
loadPending();
setInterval(refresh, 5000);
setInterval(loadPending, 8000);
