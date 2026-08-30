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
  greet: $("#greet"),
  greetDate: $("#greet-date"),
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

/* ===== 界面中文化(第十八轮):后端英文枚举 → 教师可读文案;未收录的值原样显示 ===== */
const RISK_LABEL = { high: "高风险", medium: "中风险", low: "低风险" };
const REPORT_STATUS_LABEL = { pending: "待审批", approved: "已批准", dismissed: "已驳回" };
const CASE_STATUS_LABEL = { open: "待跟进", acknowledged: "跟进中" };
const JOB_STATUS_LABEL = { pending: "等待执行", running: "执行中", success: "成功", dead: "多次失败待处理" };
const INTENT_LABEL = { companion: "陪伴", counseling: "咨询", research: "查资料", risk: "风险求助" };
const KIND_LABEL = {
  create_alert: "预警记录", send_email: "邮件通知", write_ledger: "风险台账",
  create_handoff_summary: "交接摘要", follow_up_suggestion: "跟进建议", lookup_resource: "资源查询",
};
const ACTION_LABEL = {
  update_report: "审批报告", update_case_status: "更新个案状态", add_case_note: "添加个案备注",
  retry_tool_job: "重试工具任务", rebuild_knowledge: "重建知识库", backup_knowledge: "备份知识库",
  run_evaluation: "运行评测", dispatch_tool_worker: "派发工具任务",
};
const TARGET_LABEL = { report: "风险报告", case: "个案", tool_job: "工具任务", knowledge_index: "知识库", evaluation: "评测" };
const AGENT_LABEL = {
  MemoryAgent: "记忆智能体", SupervisorAgent: "督导智能体", LeadAgent: "分诊智能体",
  RiskGuardianAgent: "风险守护智能体", KnowledgeAgent: "知识智能体",
  CounselorAgent: "咨询智能体", CompanionAgent: "陪伴智能体",
};
const TOOL_BACKEND_LABEL = { internal: "内置队列", mcp: "MCP 后端" };
const QUEUE_LABEL = { "background-worker": "后台队列", inline: "同步执行" };
const PROVIDER_LABEL = { mock: "演示模型", openai: "在线模型", ollama: "本地模型" };

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
  els.greet.textContent = greeting();
  els.greetDate.textContent = `${now.getMonth() + 1} 月 ${now.getDate()} 日 周${week}`;
}

function healthPill(status) {
  const up = status === "UP";
  setPill(els.health, up ? "服务正常" : (status || "检测中"), up ? "ok" : "bad");
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

// 风险分级 tone:报告/个案/trace 行按 risk_level 追加左侧色条与标题着色(见 styles.css .risk-*)
const riskTone = (level) => (level === "high" ? "risk-high" : level === "medium" ? "risk-medium" : "risk-low");

function row(title, subtitle, data, actions = "", tone = "") {
  const el = document.createElement("div");
  el.className = `report-row ${tone}`.trim();
  el.innerHTML = `<strong>${escapeHtml(title)}</strong><span>${escapeHtml(subtitle || "")}</span>${actions}`;
  el.addEventListener("click", () => showDetail(title, data));
  return el;
}

async function loadMe() {
  const data = await (await api("/api/auth/me")).json();
  if (data.user.role !== "admin" && data.user.role !== "teacher") {
    window.location.replace("/student");
    return;
  }
  els.activeAccount.textContent = data.user.username;
  setGreeting();
}

async function loadHealthAndAgent() {
  const health = await (await fetch("/api/health")).json();
  healthPill(health.status);
  const status = await (await api("/api/agent/status")).json();
  setPill(els.modelState, `${PROVIDER_LABEL[status.models.base_provider] || status.models.base_provider} · ${status.models.base_model}`, "secondary");
  els.agentStatus.className = "stack";
  els.agentStatus.innerHTML = `
    <div class="knowledge-line">编排引擎:${escapeHtml(status.runtimeHarness.name)} · 调度:${escapeHtml(status.agentFramework.scheduler)}</div>
    <div class="knowledge-line">存储:${escapeHtml(status.memory.primary)} · 工具:${escapeHtml(TOOL_BACKEND_LABEL[status.toolBackend] || status.toolBackend)} · 队列:${escapeHtml(QUEUE_LABEL[status.toolQueue.mode] || status.toolQueue.mode)}</div>
    <div class="source-list">${status.agents.map((agent) => `<span>${escapeHtml(AGENT_LABEL[agent.name] || agent.name)}${agent.aliasOf ? " → " + escapeHtml(AGENT_LABEL[agent.aliasOf] || agent.aliasOf) : ""}</span>`).join("")}</div>
  `;
}

async function loadReports() {
  const data = await (await api("/api/admin/reports")).json();
  renderList(els.reports, data.reports || [], "暂无报告", (report) => {
    const actions = report.status === "pending"
      ? `<div class="row-actions"><button class="mini-btn approve" data-action="report" data-id="${report.id}" data-status="approved">批准</button><button class="mini-btn dismiss" data-action="report" data-id="${report.id}" data-status="dismissed">驳回</button></div>`
      : "";
    return row(`${report.id} · ${RISK_LABEL[report.risk_level] || report.risk_level} · ${REPORT_STATUS_LABEL[report.status] || report.status}`, report.summary || report.message, report, actions, riskTone(report.risk_level));
  });
  els.metricReports.textContent = String((data.reports || []).length);
  els.metricHigh.textContent = String((data.reports || []).filter((item) => item.risk_level === "high").length);
}

async function loadCases() {
  const data = await (await api("/api/admin/cases")).json();
  renderList(els.cases, data.cases || [], "暂无个案", (item) => {
    const latest = item.notes?.length ? item.notes[item.notes.length - 1].note : "暂无备注";
    const actions = `<div class="row-actions"><button class="mini-btn" data-action="case" data-id="${item.id}" data-status="acknowledged">确认接案</button><button class="mini-btn" data-action="case-note" data-id="${item.id}">添加备注</button></div>`;
    return row(`${item.id} · ${RISK_LABEL[item.risk_level] || item.risk_level} · ${CASE_STATUS_LABEL[item.status] || item.status}`, `${item.summary || item.handoff_summary || ""} · ${latest}`, item, actions, riskTone(item.risk_level));
  });
  els.metricCases.textContent = String((data.cases || []).length);
}

async function loadTraces() {
  const data = await (await api("/api/admin/traces")).json();
  renderList(els.traces, data.traces || [], "暂无对话回放", (item) =>
    row(`${item.message_id} · ${INTENT_LABEL[item.intent] || item.intent} · ${RISK_LABEL[item.risk_level] || item.risk_level}`, item.answer || "", item, "", riskTone(item.risk_level))
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
  showDetail("知识上传结果", data);
  els.knowledgeContent.value = "";
  await loadKnowledge();
}

async function loadToolJobs() {
  const data = await (await api("/api/admin/tool-jobs")).json();
  renderList(els.jobs, data.jobs || [], "暂无任务", (job) => {
    const actions = job.status !== "success" ? `<div class="row-actions"><button class="mini-btn" data-action="retry-job" data-id="${job.id}">重试</button></div>` : "";
    return row(`${job.id} · ${KIND_LABEL[job.kind] || job.kind} · ${JOB_STATUS_LABEL[job.status] || job.status}`, `已执行 ${job.attempts}/${job.max_attempts} 次`, job, actions);
  });
  els.metricTools.textContent = String((data.jobs || []).length);
}

async function loadToolRecords() {
  const [worker, excelData, alertData] = await Promise.all([
    (await api("/api/admin/tool-worker/status")).json(),
    (await api("/api/admin/excel-records")).json(),
    (await api("/api/admin/alert-records")).json(),
  ]);
  els.workerState.textContent = `后台自动执行 · ${worker.worker_threads} 线程`;
  const rows = [
    ...(excelData.records || []).map((item) => ({ type: "excel", ...item })),
    ...(alertData.records || []).map((item) => ({ type: "alert", ...item })),
  ].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at))).slice(0, 80);
  renderList(els.records, rows, "暂无记录", (item) => {
    const kindLabel = item.type === "excel" ? "风险台账" : "预警记录";
    const subtitle = item.type === "excel"
      ? `${JOB_STATUS_LABEL[item.status] || item.status} · ${item.file_path}`
      : `${JOB_STATUS_LABEL[item.status] || item.status} · ${item.channel} · ${item.recipient || "本地日志"}`;
    return row(`${kindLabel} · ${item.id}`, subtitle, item);
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
  renderList(els.audits, auditData.logs || [], "暂无审计", (item) => row(`${ACTION_LABEL[item.action] || item.action} · ${item.actor_username}`, `${TARGET_LABEL[item.target_type] || item.target_type} · ${item.target_id}`, item));
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
    if (target.dataset.status === "approved") activateTab("support", "cases", { persist: false });
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
    const note = window.prompt("输入跟进备注");
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
$("#rebuild-knowledge").addEventListener("click", async () => { showDetail("知识库重建结果", await (await api("/api/admin/knowledge/rebuild", { method: "POST" })).json()); await loadKnowledge(); });
$("#backup-knowledge").addEventListener("click", async () => showDetail("知识库备份结果", await (await api("/api/admin/knowledge/backup", { method: "POST" })).json()));
$("#run-tool-worker").addEventListener("click", async () => {
  showDetail("工具任务执行结果", await (await api("/api/admin/tool-worker/run-once", { method: "POST" })).json());
  activateTab("workspace", "jobs", { persist: false });
  await Promise.all([loadToolJobs(), loadToolRecords()]);
});
$("#run-eval").addEventListener("click", async () => { showDetail("综合评测结果", await (await api("/api/admin/eval-results/run", { method: "POST" })).json()); activateTab("workspace", "eval", { persist: false }); await loadEvalAndAudit(); });
document.body.addEventListener("click", handleClick);

/* ===== 三列统一页签:每张卡一次只显示一个板块,记忆上次选择(第十七/十八轮) ===== */
const TAB_KEYS = { support: "aegis:tab-support", review: "aegis:tab-review", workspace: "aegis:rail-tab" };

function activateTab(scope, name, { persist = true } = {}) {
  const group = document.querySelector(`[data-tabs="${scope}"]`);
  if (!group) return;
  let matched = false;
  group.querySelectorAll(".seg-tab").forEach((b) => {
    const on = b.dataset.segTab === name;
    if (on) matched = true;
    b.classList.toggle("active", on);
    b.setAttribute("aria-pressed", on ? "true" : "false");
  });
  if (!matched) return;
  group.querySelectorAll(".seg-panel").forEach((p) => {
    p.classList.toggle("active", p.dataset.segPanel === name);
  });
  if (persist) localStorage.setItem(TAB_KEYS[scope], name);
}

document.querySelectorAll("[data-tabs]").forEach((group) => {
  const scope = group.dataset.tabs;
  group.querySelectorAll(".seg-tab").forEach((b) =>
    b.addEventListener("click", () => activateTab(scope, b.dataset.segTab))
  );
  const fallback = group.querySelector(".seg-tab.active")?.dataset.segTab;
  activateTab(scope, localStorage.getItem(TAB_KEYS[scope]) || fallback, { persist: false });
});

/* 折叠机制已被三列页签取代:清理历史遗留的 aegis:panel:* 偏好键 */
Object.keys(localStorage)
  .filter((key) => key.startsWith("aegis:panel:"))
  .forEach((key) => localStorage.removeItem(key));

loadMe().then(refreshAll).catch(() => window.location.replace("/"));
setGreeting();
setInterval(async () => {
  try {
    const health = await (await fetch("/api/health")).json();
    healthPill(health.status);
  } catch { /* 保持当前状态,下个周期再试 */ }
}, 60000);
