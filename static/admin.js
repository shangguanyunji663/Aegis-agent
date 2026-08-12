const $ = (selector) => document.querySelector(selector);
const els = {
  health: $("#health"),
  modelState: $("#model-state"),
  activeAccount: $("#active-account"),
  logout: $("#logout-btn"),
  refresh: $("#refresh-admin"),
  metricReports: $("#metric-reports"),
  metricHigh: $("#metric-high"),
  metricCases: $("#metric-cases"),
  metricTools: $("#metric-tools"),
  metricToolRecords: $("#metric-tool-records"),
  metricAudits: $("#metric-audits"),
  agentStatus: $("#agent-status-box"),
  reports: $("#reports-list"),
  cases: $("#cases-list"),
  traces: $("#trace-list"),
  detailTitle: $("#detail-title"),
  detailJson: $("#detail-json"),
  jobs: $("#tool-jobs-list"),
  records: $("#tool-records-list"),
  workerState: $("#tool-worker-state"),
  evals: $("#eval-results"),
  audits: $("#audit-list"),
  knowledgeStatus: $("#knowledge-status"),
  knowledgeQuery: $("#knowledge-query"),
  knowledgeResults: $("#knowledge-search-results"),
  knowledgeFilename: $("#knowledge-filename"),
  knowledgeContent: $("#knowledge-content"),
};

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";
  return div.innerHTML;
}

async function api(path, options = {}) {
  const response = await fetch(path, { credentials: "same-origin", ...options });
  if (response.status === 401) window.location.replace("/");
  if (response.status === 403) window.location.replace("/student");
  if (!response.ok) throw new Error(await response.text());
  return response;
}

function setPill(el, text, tone = "") {
  el.textContent = text;
  el.className = `status-pill ${tone}`.trim();
}

function showDetail(title, data) {
  els.detailTitle.textContent = title;
  els.detailJson.textContent = JSON.stringify(data ?? {}, null, 2);
}

function renderList(target, items, emptyText, render) {
  target.innerHTML = "";
  if (!items?.length) {
    target.className = "stack empty";
    target.textContent = emptyText;
    return;
  }
  target.className = "stack";
  items.forEach((item) => target.append(render(item)));
}

function row(title, subtitle, data, actions = "") {
  const el = document.createElement("div");
  el.className = "report-row";
  el.innerHTML = `<strong>${escapeHtml(title)}</strong><span>${escapeHtml(subtitle || "")}</span>${actions}`;
  el.addEventListener("click", () => showDetail(title, data));
  return el;
}

async function loadMe() {
  const data = await (await api("/api/auth/me")).json();
  if (data.user.role !== "admin") {
    window.location.replace("/student");
    return;
  }
  els.activeAccount.textContent = data.user.username;
}

async function loadHealthAndAgent() {
  const health = await (await fetch("/api/health")).json();
  setPill(els.health, health.status || "UP");
  const status = await (await api("/api/agent/status")).json();
  setPill(els.modelState, `${status.models.base_provider}/${status.agentFramework.active}`, "secondary");
  els.agentStatus.className = "stack";
  els.agentStatus.innerHTML = `
    <div class="knowledge-line">Harness: ${escapeHtml(status.runtimeHarness.name)} · ${escapeHtml(status.agentFramework.scheduler)}</div>
    <div class="knowledge-line">Memory: ${escapeHtml(status.memory.primary)} · Tools: ${escapeHtml(status.toolBackend)} · Queue: ${escapeHtml(status.toolQueue.mode)}</div>
    <div class="source-list">${status.agents.map((agent) => `<span>${escapeHtml(agent.name)}${agent.aliasOf ? " -> " + escapeHtml(agent.aliasOf) : ""}</span>`).join("")}</div>
  `;
}

async function loadReports() {
  const data = await (await api("/api/admin/reports")).json();
  renderList(els.reports, data.reports || [], "暂无报告", (report) => {
    const actions = report.status === "pending"
      ? `<div class="row-actions"><button class="mini-btn approve" data-action="report" data-id="${report.id}" data-status="approved">Approve</button><button class="mini-btn dismiss" data-action="report" data-id="${report.id}" data-status="dismissed">Dismiss</button></div>`
      : "";
    return row(`${report.id} · ${report.risk_level} · ${report.status}`, report.summary || report.message, report, actions);
  });
  els.metricReports.textContent = String((data.reports || []).length);
  els.metricHigh.textContent = String((data.reports || []).filter((item) => item.risk_level === "high").length);
}

async function loadCases() {
  const data = await (await api("/api/admin/cases")).json();
  renderList(els.cases, data.cases || [], "暂无个案", (item) => {
    const latest = item.notes?.length ? item.notes[item.notes.length - 1].note : "暂无备注";
    const actions = `<div class="row-actions"><button class="mini-btn" data-action="case" data-id="${item.id}" data-status="acknowledged">Acknowledge</button><button class="mini-btn" data-action="case-note" data-id="${item.id}">Add Note</button></div>`;
    return row(`${item.id} · ${item.risk_level} · ${item.status}`, `${item.summary || item.handoff_summary || ""} · ${latest}`, item, actions);
  });
  els.metricCases.textContent = String((data.cases || []).length);
}

async function loadTraces() {
  const data = await (await api("/api/admin/traces")).json();
  renderList(els.traces, data.traces || [], "暂无 trace", (item) =>
    row(`${item.message_id} · ${item.intent} · ${item.risk_level}`, item.answer || "", item)
  );
}

async function loadKnowledge() {
  const data = await (await api("/api/admin/knowledge/status")).json();
  els.knowledgeStatus.className = "stack";
  els.knowledgeStatus.innerHTML = `
    <div class="knowledge-metric"><strong>${escapeHtml(data.database_chunks ?? 0)}</strong><span>chunks</span></div>
    <div class="knowledge-line">${escapeHtml(data.retrieval || "retrieval")} · vector=${escapeHtml(String(data.vector_available))}</div>
    <div class="source-list">${(data.sources || []).map((source) => `<span>${escapeHtml(source)}</span>`).join("")}</div>
  `;
}

async function searchKnowledge() {
  const q = els.knowledgeQuery.value.trim();
  if (!q) return;
  const data = await (await api(`/api/admin/knowledge/search?q=${encodeURIComponent(q)}&top_k=3`)).json();
  renderList(els.knowledgeResults, data.results || [], "没有命中", (item) =>
    row(`${item.source} · ${item.score}`, item.snippet, item)
  );
}

async function uploadKnowledge() {
  const filename = els.knowledgeFilename.value.trim();
  const content = els.knowledgeContent.value.trim();
  if (!filename || !content) return;
  const data = await (await api("/api/admin/knowledge/upload", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename, content }),
  })).json();
  showDetail("Knowledge upload", data);
  els.knowledgeContent.value = "";
  await loadKnowledge();
}

async function loadToolJobs() {
  const data = await (await api("/api/admin/tool-jobs")).json();
  renderList(els.jobs, data.jobs || [], "暂无任务", (job) => {
    const actions = job.status !== "success" ? `<div class="row-actions"><button class="mini-btn" data-action="retry-job" data-id="${job.id}">Retry</button></div>` : "";
    return row(`${job.id} · ${job.kind} · ${job.status}`, `attempts ${job.attempts}/${job.max_attempts}`, job, actions);
  });
  els.metricTools.textContent = String((data.jobs || []).length);
}

async function loadToolRecords() {
  const [worker, excelData, alertData] = await Promise.all([
    (await api("/api/admin/tool-worker/status")).json(),
    (await api("/api/admin/excel-records")).json(),
    (await api("/api/admin/alert-records")).json(),
  ]);
  els.workerState.textContent = `${worker.mode} · ${worker.worker_threads} threads`;
  const rows = [
    ...(excelData.records || []).map((item) => ({ type: "excel", ...item })),
    ...(alertData.records || []).map((item) => ({ type: "alert", ...item })),
  ].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at))).slice(0, 80);
  renderList(els.records, rows, "暂无记录", (item) => {
    const subtitle = item.type === "excel"
      ? `${item.status} · ${item.file_path}`
      : `${item.status} · ${item.channel} · ${item.recipient || "local"}`;
    return row(`${item.type} · ${item.id}`, subtitle, item);
  });
  els.metricToolRecords.textContent = String(rows.length);
}

async function loadEvalAndAudit() {
  const [evalData, auditData] = await Promise.all([
    (await api("/api/admin/eval-results")).json(),
    (await api("/api/admin/audit-logs")).json(),
  ]);
  const summary = evalData.summary || {};
  els.evals.className = "stack";
  els.evals.innerHTML = Object.keys(summary).length
    ? `<div class="eval-grid">${["routing_accuracy", "risk_accuracy", "retrieval_hit_rate", "skill_accuracy", "safety_pass_rate", "multi_turn_accuracy"].map((key) => `<div class="eval-metric"><strong>${escapeHtml(summary[key] ?? 0)}</strong><span>${escapeHtml(key)}</span></div>`).join("")}</div>`
    : "暂无评测";
  renderList(els.audits, auditData.logs || [], "暂无审计", (item) => row(`${item.action} · ${item.actor_username}`, `${item.target_type} · ${item.target_id}`, item));
  els.metricAudits.textContent = String((auditData.logs || []).length);
}

async function refreshAll() {
  await Promise.all([loadHealthAndAgent(), loadReports(), loadCases(), loadTraces(), loadKnowledge(), loadToolJobs(), loadToolRecords(), loadEvalAndAudit()]);
}

async function handleClick(event) {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (target.dataset.action === "report") {
    await api(`/api/admin/reports/${encodeURIComponent(target.dataset.id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: target.dataset.status }),
    });
    await Promise.all([loadReports(), loadCases(), loadToolJobs(), loadEvalAndAudit()]);
  }
  if (target.dataset.action === "case") {
    await api(`/api/admin/cases/${encodeURIComponent(target.dataset.id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: target.dataset.status }),
    });
    await loadCases();
  }
  if (target.dataset.action === "case-note") {
    const note = window.prompt("输入备注");
    if (!note) return;
    await api(`/api/admin/cases/${encodeURIComponent(target.dataset.id)}/notes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note }),
    });
    await loadCases();
  }
  if (target.dataset.action === "retry-job") {
    await api(`/api/admin/tool-jobs/${encodeURIComponent(target.dataset.id)}/retry`, { method: "POST" });
    await loadToolJobs();
  }
}

async function logout() {
  await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
  window.location.assign("/");
}

els.logout.addEventListener("click", logout);
els.refresh.addEventListener("click", refreshAll);
$("#search-knowledge").addEventListener("click", searchKnowledge);
$("#upload-knowledge").addEventListener("click", uploadKnowledge);
$("#rebuild-knowledge").addEventListener("click", async () => { showDetail("Knowledge rebuild", await (await api("/api/admin/knowledge/rebuild", { method: "POST" })).json()); await loadKnowledge(); });
$("#backup-knowledge").addEventListener("click", async () => showDetail("Knowledge backup", await (await api("/api/admin/knowledge/backup", { method: "POST" })).json()));
$("#run-tool-worker").addEventListener("click", async () => {
  showDetail("Tool worker", await (await api("/api/admin/tool-worker/run-once", { method: "POST" })).json());
  await Promise.all([loadToolJobs(), loadToolRecords()]);
});
$("#run-eval").addEventListener("click", async () => { showDetail("Eval run", await (await api("/api/admin/eval-results/run", { method: "POST" })).json()); await loadEvalAndAudit(); });
document.body.addEventListener("click", handleClick);

loadMe().then(refreshAll).catch(() => window.location.replace("/"));
