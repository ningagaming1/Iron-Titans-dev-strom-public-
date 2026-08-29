/* auth.js - login / sign-up page */

const $ = (id) => document.getElementById(id);
const API = location.protocol === "file:" ? "http://localhost:8000" : "";

let devMode = false;
let minPassword = 6;

/* talk to the server */
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

/* already signed in? straight to the dashboard */
try {
  const saved = JSON.parse(localStorage.getItem("smarthome_user"));
  if (saved && saved.username) location.href = "dashboard.html";
  else if (localStorage.getItem("smarthome_user")) localStorage.removeItem("smarthome_user");
} catch (e) {
  localStorage.removeItem("smarthome_user");
}

/* dev mode on? */
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

/* switch between the two forms */
$("toSignup").onclick = () => { $("loginView").classList.add("hidden"); $("signupView").classList.remove("hidden"); };
$("toLogin").onclick  = () => { $("signupView").classList.add("hidden"); $("loginView").classList.remove("hidden"); };

/* show / hide password (eye button - keep the icon, just flip a class) */
document.querySelectorAll("[data-toggle]").forEach((btn) => {
  btn.onclick = () => {
    const f = $(btn.dataset.toggle);
    const show = f.type === "password";
    f.type = show ? "text" : "password";
    btn.classList.toggle("open", show);
    btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
  };
});

/* "forgot password" - there's no email flow, so just point at an admin */
const forgot = $("forgot");
if (forgot) forgot.onclick = () =>
  note("loginNote", "No reset link yet - ask an admin to unlock or re-approve your account.", "err");

/* little arrows that swing to point at the cursor */
(function () {
  const box = $("pointers");
  if (!box) return;
  const spots = [[12, 16], [80, 11], [31, 44], [63, 58], [15, 73],
                 [87, 80], [47, 88], [91, 38], [7, 45], [55, 24]];
  const arrow =
    '<svg viewBox="0 0 24 24" fill="currentColor">' +
    '<path d="M3 12h13.2l-4.9-4.9L13 5.4 20.6 12 13 18.6l-1.7-1.7 4.9-4.9H3z"/></svg>';
  const els = spots.map(([x, y]) => {
    const d = document.createElement("div");
    d.className = "pointer";
    d.style.left = x + "%";
    d.style.top = y + "%";
    d.innerHTML = arrow;
    box.appendChild(d);
    return d;
  });
  let raf = 0, mx = innerWidth / 2, my = innerHeight * 0.4;
  const aim = () => {
    raf = 0;
    els.forEach((el) => {
      const r = el.getBoundingClientRect();
      const a = Math.atan2(my - (r.top + r.height / 2), mx - (r.left + r.width / 2));
      el.style.transform = "rotate(" + a + "rad)";
    });
  };
  addEventListener("mousemove", (e) => {
    mx = e.clientX; my = e.clientY;
    if (!raf) raf = requestAnimationFrame(aim);
  });
  aim();
})();

/* password strength meter (sign-up) */
const PW_WORDS = ["weak", "weak", "fair", "good", "strong"];
function pwScore(p) {
  if (!p) return 0;
  let s = 0;
  if (p.length >= 6) s++;
  if (p.length >= 10) s++;
  if (/[a-z]/.test(p) && /[A-Z]/.test(p)) s++;
  if (/\d/.test(p)) s++;
  if (/[^A-Za-z0-9]/.test(p)) s++;
  if (/^(.)\1+$/.test(p) || /^(0?1234|abcd|qwerty|password|admin)/i.test(p)) s = Math.min(s, 1);
  return Math.min(s, 4);
}
$("suPass").addEventListener("input", () => {
  const p = $("suPass").value;
  const m = $("pwMeter");
  if (!p) { m.hidden = true; return; }
  m.hidden = false;
  const sc = Math.max(pwScore(p), 1);
  m.className = "pw-meter s" + sc;
  $("pwWord").textContent = PW_WORDS[sc];
});

/* login */
const loginLabel = $("loginBtnLabel");

/* after a wrong password the server makes you wait - count it down on
   the button so it's obvious why the form won't submit. */
let cooldownTimer = null;
function startLoginCooldown(secs) {
  clearInterval(cooldownTimer);
  const btn = $("loginBtn");
  let left = Math.max(1, Math.ceil(secs));
  btn.disabled = true;
  const tick = () => {
    if (left <= 0) {
      clearInterval(cooldownTimer);
      btn.disabled = false;
      loginLabel.textContent = "Let me in";
      return;
    }
    loginLabel.textContent = "wait " + left + "s";
    left--;
  };
  tick();
  cooldownTimer = setInterval(tick, 1000);
}

$("loginForm").onsubmit = async (e) => {
  e.preventDefault();
  if ($("loginBtn").disabled) return;
  const username = $("loginUser").value.trim();
  const password = $("loginPass").value;
  if (!username || !password) return note("loginNote", "Fill in both boxes.", "err");

  const btn = $("loginBtn");
  btn.disabled = true; loginLabel.textContent = "checking...";
  const data = await post("/api/login", { username, password });

  if (!data.ok) {
    note("loginNote", data.message, "err");
    if (data.retry_after) startLoginCooldown(data.retry_after);
    else { btn.disabled = false; loginLabel.textContent = "Let me in"; }
    return;
  }

  loginLabel.textContent = "Let me in";
  localStorage.setItem("smarthome_user", JSON.stringify(data.user));
  // tell the dashboard to say the welcome line once, this tab only
  try { sessionStorage.setItem("syncghar_greet", "1"); } catch (e) {}
  location.href = "dashboard.html";
};

/* sign up / request account */
$("signupForm").onsubmit = async (e) => {
  e.preventDefault();
  const username = $("suUser").value.trim();
  const p1 = $("suPass").value;
  const p2 = $("suPass2").value;

  if (username.length < 3) return note("suNote", "Username needs at least 3 letters.", "err");
  if (p1.length < minPassword) return note("suNote", "Password needs at least " + minPassword + " character(s).", "err");
  if (!devMode && pwScore(p1) < 2)
    return note("suNote", "That password is too weak - add length, a capital letter, a number or a symbol.", "err");
  if (p1 !== p2) return note("suNote", "The two passwords don't match.", "err");

  const btn = $("suBtn");
  const label = btn.textContent;
  btn.disabled = true; btn.textContent = "sending...";
  const data = await post("/api/signup", { username, password: p1 });
  btn.disabled = false; btn.textContent = label;

  if (!data.ok) return note("suNote", data.message, "err");
  $("signupForm").reset();
  $("pwMeter").hidden = true;
  note("suNote", data.message, "ok");
  if (devMode) $("loginUser").value = username;
};
