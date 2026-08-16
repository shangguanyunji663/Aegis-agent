const state = { sessionId: null, sending: false, user: null };
const $ = (selector) => document.querySelector(selector);

const els = {
  health: $("#health"),
  modelState: $("#model-state"),
  activeAccount: $("#active-account"),
  logout: $("#logout-btn"),
  newSession: $("#new-session"),
  history: $("#history-list"),
  messages: $("#messages"),
  chatForm: $("#chat-form"),
  messageInput: $("#message-input"),
  sendButton: $("#send-btn"),
  sessionBadge: $("#session-badge"),
  streamStatus: $("#stream-status"),
};

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";
  return div.innerHTML;
}

async function api(path, options = {}) {
  const response = await fetch(path, { credentials: "same-origin", ...options });
  if (response.status === 401) window.location.replace("/");
  if (!response.ok) throw new Error(await response.text());
  return response;
}

function setPill(el, text, tone = "secondary") {
  el.textContent = text;
  el.className = `status-pill ${tone}`;
}

async function loadMe() {
  const data = await (await api("/api/auth/me")).json();
  if (data.user.role === "admin") {
    window.location.replace("/admin");
    return;
  }
  state.user = data.user;
  els.activeAccount.textContent = data.user.username;
}

async function loadHealth() {
  try {
    const health = await (await fetch("/api/health")).json();
    setPill(els.health, health.status || "UP");
    const status = await (await api("/api/agent/status")).json();
    setPill(els.modelState, status.models.base_provider === "mock" ? "mock 演示" : status.models.base_model);
  } catch {
    setPill(els.health, "DOWN");
  }
}

async function loadSessions() {
  const data = await (await api("/api/sessions")).json();
  els.history.innerHTML = "";
  if (!data.sessions?.length) {
    els.history.innerHTML = `<div class="history-empty">还没有对话</div>`;
    return;
  }
  data.sessions.forEach((session) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `history-item ${session.id === state.sessionId ? "active" : ""}`;
    item.innerHTML = `<span class="history-dot"></span><span>${escapeHtml(session.title || "新对话")}</span>`;
    item.addEventListener("click", () => loadConversation(session.id));
    els.history.append(item);
  });
}

async function loadConversation(sessionId) {
  const data = await (await api(`/api/sessions/${encodeURIComponent(sessionId)}`)).json();
  state.sessionId = data.session.id;
  els.messages.innerHTML = "";
  data.session.messages.forEach((message) => addMessage(message.role === "USER" ? "user" : "assistant", message.content));
  setPill(els.sessionBadge, `session ${state.sessionId.slice(0, 8)}`);
  await loadSessions();
}

function clearWelcome() {
  const intro = els.messages.querySelector(".intro");
  if (intro) intro.remove();
}

function addMessage(role, content = "") {
  clearWelcome();
  const row = document.createElement("article");
  row.className = `split-message ${role}`;
  row.innerHTML = `<div class="message-role">${role === "user" ? "我" : "Aegis"}</div><div class="message-bubble">${escapeHtml(content)}</div>`;
  els.messages.append(row);
  els.messages.scrollTop = els.messages.scrollHeight;
  return row.querySelector(".message-bubble");
}

function parseSse(buffer, onEvent) {
  const parts = buffer.split("\n\n");
  const rest = parts.pop() || "";
  parts.forEach((part) => {
    const dataLine = part.split("\n").find((line) => line.startsWith("data:"));
    if (!dataLine) return;
    onEvent(JSON.parse(dataLine.replace("data:", "").trim()));
  });
  return rest;
}

async function sendMessage(event) {
  event.preventDefault();
  const text = els.messageInput.value.trim();
  if (!text || state.sending) return;
  state.sending = true;
  els.sendButton.disabled = true;
  els.messageInput.value = "";
  setPill(els.sessionBadge, "THINKING", "secondary");
  setPill(els.streamStatus, "streaming", "secondary");
  addMessage("user", text);
  const assistant = addMessage("assistant", "");
  assistant.innerHTML = '<span class="typing-dots"><span></span><span></span><span></span></span>';
  const meta = document.createElement("div");
  meta.className = "stream-meta";
  assistant.parentElement.append(meta);
  let answer = "";
  try {
    const response = await api("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId, message: text }),
    });
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = parseSse(buffer, (payload) => {
        if (payload.event === "start") state.sessionId = payload.session_id;
        if (payload.event === "route") {
          meta.textContent = `风险评估：${{ low: "低", medium: "中", high: "高" }[payload.risk_level] || payload.risk_level} · 正在准备回复`;
        }
        if (payload.event === "skill" && payload.name === "search_knowledge") {
          meta.textContent = "已检索心理知识库，正在组织回复";
        }
        if (payload.event === "report") {
          meta.textContent = "已生成安全报告，等待管理员跟进";
        }
        if (payload.event === "token") {
          answer += payload.content || "";
          assistant.textContent = answer;
          els.messages.scrollTop = els.messages.scrollHeight;
        }
        if (payload.event === "error") {
          setPill(els.streamStatus, "重试中", "secondary");
        }
        if (payload.event === "done") {
          state.sessionId = payload.response?.session_id || state.sessionId;
          const finalAnswer = payload.response?.answer;
          if (finalAnswer) {
            // 终稿覆盖:低风险直播内容以安全复核后的最终回复为准
            answer = finalAnswer;
            assistant.textContent = finalAnswer;
          }
          meta.remove();
          setPill(els.sessionBadge, "DONE");
        }
      });
    }
    setPill(els.streamStatus, "done");
    await loadSessions();
  } catch (error) {
    assistant.textContent = `发送失败：${error.message}`;
    meta.remove();
    setPill(els.streamStatus, "error", "secondary");
  } finally {
    state.sending = false;
    els.sendButton.disabled = false;
    els.messageInput.focus();
  }
}

async function logout() {
  await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
  window.location.assign("/");
}

function resetSession() {
  state.sessionId = null;
  els.messages.innerHTML = `<div class="intro"><div class="intro-title">新会话已开始</div><p>你可以继续输入新的问题。</p></div>`;
  setPill(els.sessionBadge, "READY");
}

document.querySelectorAll("[data-quick]").forEach((button) => {
  button.addEventListener("click", () => {
    els.messageInput.value = button.dataset.quick;
    els.messageInput.focus();
  });
});
els.chatForm.addEventListener("submit", sendMessage);
els.logout.addEventListener("click", logout);
els.newSession.addEventListener("click", resetSession);
els.messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    els.chatForm.requestSubmit();
  }
});

loadMe().then(() => Promise.all([loadHealth(), loadSessions()])).catch(() => window.location.replace("/"));
