/* -----------------------------------------------------------
   auth.js - the login / sign-up page behaviour.
----------------------------------------------------------- */

const $ = (id) => document.getElementById(id);
const API = location.protocol === "file:" ? "http://localhost:8000" : "";

let devMode = false;
let minPassword = 6;

/* ---- talk to the server ---- */
async function post(path, body) {
  try {
    const r = await fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return await r.json();
  } catch (e) {
    return { ok: false, message: "Can't reach the server. Run  python app.py  first." };
  }
}

function note(id, message, kind) {
  const n = $(id);
  n.textContent = message;
  n.className = "note show " + (kind === "ok" ? "ok" : "err");
}

/* ---- already signed in? go to the dashboard ---- */
try {
  const saved = JSON.parse(localStorage.getItem("smarthome_user"));
  if (saved && saved.username) location.href = "dashboard.html";
  else if (localStorage.getItem("smarthome_user")) localStorage.removeItem("smarthome_user");
} catch (e) {
  localStorage.removeItem("smarthome_user");
}

/* ---- is developer mode on? ---- */
(async () => {
  try {
    const cfg = await (await fetch(API + "/api/config")).json();
    devMode = !!cfg.dev_mode;
  } catch (e) {}
  if (devMode) {
    minPassword = 1;
    $("devBadge").classList.add("show");
    $("loginSub").textContent = "Dev mode: anyone who signed up can log in - no approval needed.";
    $("suTitle").textContent = "Create an account";
    $("suSub").textContent = "Dev mode is on, so this account works straight away.";
    $("suBtn").textContent = "Create account";
  }
})();

/* ---- switch between the two forms ---- */
$("toSignup").onclick = () => { $("loginView").classList.add("hidden"); $("signupView").classList.remove("hidden"); };
$("toLogin").onclick  = () => { $("signupView").classList.add("hidden"); $("loginView").classList.remove("hidden"); };

/* ---- show / hide password ---- */
document.querySelectorAll("[data-toggle]").forEach((btn) => {
  btn.onclick = () => {
    const f = $(btn.dataset.toggle);
    const showing = f.type === "text";
    f.type = showing ? "password" : "text";
    btn.textContent = showing ? "show password" : "hide password";
  };
});

/* ---- login ---- */
$("loginForm").onsubmit = async (e) => {
  e.preventDefault();
  const username = $("loginUser").value.trim();
  const password = $("loginPass").value;
  if (!username || !password) return note("loginNote", "Fill in both boxes.", "err");

  const btn = $("loginBtn");
  btn.disabled = true; btn.textContent = "checking...";
  const data = await post("/api/login", { username, password });
  btn.disabled = false; btn.textContent = "Let me in";

  if (!data.ok) return note("loginNote", data.message, "err");

  localStorage.setItem("smarthome_user", JSON.stringify(data.user));
  location.href = "dashboard.html";
};

/* ---- sign up / request account ---- */
$("signupForm").onsubmit = async (e) => {
  e.preventDefault();
  const username = $("suUser").value.trim();
  const p1 = $("suPass").value;
  const p2 = $("suPass2").value;

  if (username.length < 3) return note("suNote", "Username needs at least 3 letters.", "err");
  if (p1.length < minPassword) return note("suNote", "Password needs at least " + minPassword + " character(s).", "err");
  if (p1 !== p2) return note("suNote", "The two passwords don't match.", "err");

  const btn = $("suBtn");
  const label = btn.textContent;
  btn.disabled = true; btn.textContent = "sending...";
  const data = await post("/api/signup", { username, password: p1 });
  btn.disabled = false; btn.textContent = label;

  if (!data.ok) return note("suNote", data.message, "err");
  $("signupForm").reset();
  note("suNote", data.message, "ok");
  if (devMode) $("loginUser").value = username;
};
