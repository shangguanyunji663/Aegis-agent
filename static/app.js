const loginForm = document.querySelector("#login-form");
const usernameInput = document.querySelector("#login-username");
const passwordInput = document.querySelector("#login-password");
const authError = document.querySelector("#auth-error");
const health = document.querySelector("#health");
const agentStatus = document.querySelector("#agent-status");

function showError(message) {
  authError.textContent = message;
  authError.classList.toggle("hidden", !message);
}

async function refreshHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    health.textContent = data.status || "UP";
  } catch {
    health.textContent = "DOWN";
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
  window.location.assign(data.user.role === "admin" ? "/admin" : "/student");
}

loginForm.addEventListener("submit", handleLogin);
refreshHealth();
agentStatus.textContent = "ready";
