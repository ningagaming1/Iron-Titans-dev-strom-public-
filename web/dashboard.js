/* -----------------------------------------------------------
   dashboard.js - the control panel.

   Voice path:
     * browser speech -> the browser's own Web Speech API turns
                         your words into text
     * not supported  -> mic is disabled, typing still works

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
  const prev = house;
  house = h;

  card("light", h.light);
  card("fan", h.fan);

  // door: bolt icon + label follow the lock state
  $("doorState").textContent = h.door_locked ? "LOCKED" : "UNLOCKED";
  $("doorState").classList.toggle("on", h.door_locked);
  $("doorBtn").textContent = h.door_locked ? "Unlock Door" : "Lock Door";
  $("doorIcon").textContent = h.door_locked ? "🔒" : "🔓";
  $("doorCard").classList.toggle("locked", h.door_locked);

  // one-shot animations - fire ONLY when that device actually changed,
  // so the 5s auto-refresh doesn't keep re-triggering them.
  if (h.light !== prev.light && h.light) playAnim("lightCard", "flick");
  if (h.door_locked !== prev.door_locked) playAnim("doorCard", "clunk");
  // the fan's spin is a continuous CSS animation tied to #fanCard.on

  const applianceCount = (h.light ? 1 : 0) + (h.fan ? 1 : 0);
  $("deviceCount").textContent = applianceCount + " on";

  // the LIGHT is what lights the room - the fan and door don't change
  // the mood, so turning on the fan no longer brightens the whole page.
  document.body.classList.toggle("dark", !h.light);

  drawLog(h.activity || []);
}
function card(name, on) {
  $(name + "State").textContent = on ? "ON" : "OFF";
  $(name + "State").classList.toggle("on", on);
  $(name + "Btn").textContent = on ? "Turn Off" : "Turn On";
  $(name + "Card").classList.toggle("on", on);
}
function playAnim(cardId, name) {
  const el = $(cardId);
  if (!el) return;
  el.classList.remove("anim-flick", "anim-clunk");
  void el.offsetWidth;               // restart the animation
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

/* ---- developer mode toggle ---- */
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

/* ===========================================================
   VOICE
=========================================================== */
let voiceMode = "off";            // "browser" | "off"
const browserSpeech = () => window.SpeechRecognition || window.webkitSpeechRecognition;

function micOn(on) {
  $("mic").classList.toggle("rec", on);
  micStatus(on ? "listening... (tap to stop)" : "tap the mic or type");
}

/* ---- browser speech: Web Speech API ---- */
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
  if (voiceMode === "browser") browserMic();
};

function setupVoice() {
  if (browserSpeech()) {
    voiceMode = "browser";
    voiceNote("Voice: your browser's speech engine.");
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
})();

setupVoice();
refresh();
refreshDevMode();
loadPending();
setInterval(refresh, 5000);
setInterval(loadPending, 8000);
