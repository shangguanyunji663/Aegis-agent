const loginForm = document.querySelector("#login-form");
const registerForm = document.querySelector("#register-form");
const usernameInput = document.querySelector("#login-username");
const passwordInput = document.querySelector("#login-password");
const regUsername = document.querySelector("#reg-username");
const regPassword = document.querySelector("#reg-password");
const regRole = document.querySelector("#reg-role");
const regInvite = document.querySelector("#reg-invite");
const inviteLine = document.querySelector("#invite-line");
const toggleAuth = document.querySelector("#toggle-auth");
const authError = document.querySelector("#auth-error");
const health = document.querySelector("#health");
const agentStatus = document.querySelector("#agent-status");
const greet = document.querySelector("#greet");
const greetDate = document.querySelector("#greet-date");

function showError(message) {
  authError.textContent = message;
  authError.classList.toggle("hidden", !message);
}

function redirectByRole(role) {
  window.location.assign(role === "admin" || role === "teacher" ? "/admin" : "/student");
}

function switchMode(mode) {
  const toRegister = mode === "register";
  registerForm.classList.toggle("hidden", !toRegister);
  loginForm.classList.toggle("hidden", toRegister);
  toggleAuth.textContent = toRegister ? "已有账号?返回登录" : "没有账号?注册一个";
  showError("");
}

function greeting() {
  const h = new Date().getHours();
  if (h < 5) return "夜深了";
  if (h < 11) return "早上好";
  if (h < 13) return "中午好";
  if (h < 18) return "下午好";
  return "晚上好";
}

function setGreeting() {
  const now = new Date();
  const week = ["日", "一", "二", "三", "四", "五", "六"][now.getDay()];
  greet.textContent = `${greeting()}，欢迎回来`;
  greetDate.textContent = `${now.getMonth() + 1} 月 ${now.getDate()} 日 周${week}`;
}

async function refreshHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    const up = data.status === "UP";
    health.textContent = up ? "服务正常" : (data.status || "检测中");
    health.className = `status-pill ${up ? "ok" : "bad"}`;
  } catch {
    health.textContent = "服务异常";
    health.className = "status-pill bad";
  }
}

async function handleLogin(event) {
  event.preventDefault();
  showError("");
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({
      username: usernameInput.value.trim(),
      password: passwordInput.value,
    }),
  });
  if (!response.ok) {
    showError("登录失败，请检查账号。");
    return;
  }
  const data = await response.json();
  redirectByRole(data.user.role);
}

async function handleRegister(event) {
  event.preventDefault();
  showError("");
  const role = regRole.value;
  const response = await fetch("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({
      username: regUsername.value.trim(),
      password: regPassword.value,
      role,
      invite_code: role === "teacher" ? regInvite.value.trim() : "",
    }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    showError(data.detail || "注册失败，请检查输入。");
    return;
  }
  const data = await response.json();
  redirectByRole(data.user.role);
}

loginForm.addEventListener("submit", handleLogin);
registerForm.addEventListener("submit", handleRegister);
regRole.addEventListener("change", () => {
  inviteLine.classList.toggle("hidden", regRole.value !== "teacher");
});
toggleAuth.addEventListener("click", () => switchMode(registerForm.classList.contains("hidden") ? "register" : "login"));
toggleAuth.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") toggleAuth.click();
});
refreshHealth();
setGreeting();
setInterval(refreshHealth, 60000);
agentStatus.textContent = "就绪";
