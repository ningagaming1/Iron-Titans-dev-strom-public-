/* dashboard.js - the control panel.
   voice: browser Web Speech turns words into text; if it's not
   supported the mic is disabled and typing still works. either way
   the server's intent.py decides what it means. */

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

/* drawing the house */
const ICONS = { light: "💡", fan: "🌀", lock: "🔒", unlock: "🔓", bulk: "⚡", night: "🌙", info: "•" };
let house = { light: false, fan: false, door_locked: true, activity: [] };

function render(h) {
  if (!h) return;
  const prev = house;
  house = h;

  card("light", h.light);
  card("fan", h.fan);

  // door: icon + label follow the lock state
  $("doorState").textContent = h.door_locked ? "LOCKED" : "UNLOCKED";
  $("doorState").classList.toggle("on", h.door_locked);
  $("doorBtn").textContent = h.door_locked ? "Unlock Door" : "Lock Door";
  $("doorIcon").textContent = h.door_locked ? "🔒" : "🔓";
  $("doorCard").classList.toggle("locked", h.door_locked);

  // one-shot animations - only when that device actually changed, so the
  // 5s auto-refresh doesnt keep re-firing them. (fan spin is pure CSS.)
  if (h.light !== prev.light && h.light) playAnim("lightCard", "flick");
  if (h.door_locked !== prev.door_locked) playAnim("doorCard", "clunk");

  const applianceCount = (h.light ? 1 : 0) + (h.fan ? 1 : 0);
  $("deviceCount").textContent = applianceCount + " on";

  // only the light changes the room's mood
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
  void el.offsetWidth;               // force a reflow so the anim restarts
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

/* device buttons */
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
                 used when /api/voice/status says ready.
     "browser" - the browser's own Web Speech API. fallback. */
let voiceEngine = "browser";      // "server" | "browser" | "off"
let serverTTS = false;            // can the server speak replies?
let recording = false;
let mediaRec = null;

const browserSpeech = () => window.SpeechRecognition || window.webkitSpeechRecognition;

function micOn(on) {
  recording = on;
  $("mic").classList.toggle("rec", on);
  micStatus(on ? "listening - speak your command" : "tap the mic or type");
  if (!on) showListening(null);
}

/* the "listening" pop-up */
function showListening(mode) {          // "listening" | "thinking" | null
  const o = $("listenOverlay");
  if (!o) return;
  if (!mode) { o.hidden = true; return; }
  o.hidden = false;
  o.className = "listen-overlay " + mode;
  o.querySelector(".listen-text").textContent =
    mode === "thinking" ? "Thinking..." : "Listening...";
}

/* speak a reply out loud */
let ttsAudio = null;
async function speak(text) {
  text = (text || "").trim();
  if (!text) return;
  // stop anything already talking
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
  u.pitch = 1.15;                 // a bit higher, sounds warmer
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
  try {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
  } catch (e) {
    return setStatus("Microphone blocked. Click the camera/mic icon in the "
                     + "address bar, allow it, then reload.", true);
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
  listenMeter(micStream);                 // auto-stop when you stop talking
  hardStop = setTimeout(stopServerMic, 10000);   // or after 10s regardless
}

function stopServerMic() {
  clearTimeout(hardStop);
  if (mediaRec && mediaRec.state === "recording") mediaRec.stop();
}

/* watch the mic level: stop shortly after speech ends, or after silence */
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
      // wait for a 1.6s gap after speech so the last word isnt clipped
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
    if (e.results[e.results.length - 1].isFinal && text) { showListening("thinking"); runText(text); }
  };
  try { rec.start(); } catch (e) {}
}

/* the mic button: start or stop */
$("mic").onclick = () => {
  if (recording) {                       // tap again = stop early
    if (voiceEngine === "server") stopServerMic();
    else if (voiceEngine === "browser" && window._rec) window._rec.stop();
    return;
  }
  if (voiceEngine === "server") startServerMic();
  else if (voiceEngine === "browser") startBrowserMic();
};

async function setupVoice() {
  let st = null;
  try { st = await getJSON("/api/voice/status"); } catch (e) {}
  serverTTS = !!(st && st.tts);

  if (st && st.stt && window.MediaRecorder && navigator.mediaDevices) {
    voiceEngine = "server";
    voiceNote("Voice: offline engine (Vosk + Piper) - no internet needed.");
  } else if (browserSpeech()) {
    voiceEngine = "browser";
    voiceNote(st && st.hint ? st.hint : "Voice: your browser's speech engine.");
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
