/* fetch 封装:cookie 会话同源携带;401 统一踢回登录页(登录接口除外);
   SSE 由调用方拿原始 Response 逐帧解析,不走 JSON。 */

import type {
  AgentStatus,
  AlertRecord,
  AuditLog,
  CaseItem,
  EvalSummary,
  ExcelRecord,
  KnowledgeSearchResult,
  KnowledgeStatus,
  ReportItem,
  SessionDetail,
  SessionSummary,
  ToolJob,
  ToolWorkerStatus,
  TraceItem,
  User,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export class UnauthorizedError extends ApiError {
  constructor() {
    super(401, "登录态已失效");
  }
}

let kicking = false;
function kickToLogin() {
  // 防止并发 401 反复 replace 打断表单交互
  if (kicking) return;
  kicking = true;
  window.location.replace("/");
}

async function request<T>(path: string, init: RequestInit = {}, authOptional = false): Promise<T> {
  const response = await fetch(path, { credentials: "same-origin", ...init });
  if (response.status === 401) {
    if (!authOptional) kickToLogin();
    throw new UnauthorizedError();
  }
  if (!response.ok) throw new ApiError(response.status, await response.text());
  return (await response.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export interface LoginResult {
  user: { role: string };
}

export const api = {
  health: () => fetch("/api/health", { credentials: "same-origin" }).then((r) => r.json()),

  me: () => request<{ user: User }>("/api/auth/me", {}, true),

  login: (username: string, password: string) =>
    request<LoginResult>("/api/auth/login", json("POST", { username, password }), true),

  register: (payload: { username: string; password: string; role: string; invite_code: string }) =>
    request<LoginResult>("/api/auth/register", json("POST", payload), true),

  logout: async () => {
    await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
    window.location.assign("/");
  },

  saveTheme: (theme: "light" | "dark") =>
    request<unknown>("/api/auth/me/theme", json("PUT", { theme })),

  sessions: () => request<{ sessions: SessionSummary[] }>("/api/sessions"),

  session: (id: string) =>
    request<SessionDetail>(`/api/sessions/${encodeURIComponent(id)}`),

  /* SSE:返回原始 Response,由 useChat 逐帧解析 */
  chatStream: (payload: { session_id: string | null; message: string }) =>
    fetch("/api/chat/stream", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  admin: {
    reports: () => request<{ reports: ReportItem[] }>("/api/admin/reports"),
    cases: () => request<{ cases: CaseItem[] }>("/api/admin/cases"),
    traces: () => request<{ traces: TraceItem[] }>("/api/admin/traces"),
    knowledgeStatus: () => request<KnowledgeStatus>("/api/admin/knowledge/status"),
    knowledgeSearch: (q: string) =>
      request<{ results: KnowledgeSearchResult[] }>(
        `/api/admin/knowledge/search?q=${encodeURIComponent(q)}&top_k=3`,
      ),
    knowledgeUpload: (filename: string, content: string) =>
      request<unknown>("/api/admin/knowledge/upload", json("POST", { filename, content })),
    knowledgeRebuild: () => request<unknown>("/api/admin/knowledge/rebuild", { method: "POST" }),
    knowledgeBackup: () => request<unknown>("/api/admin/knowledge/backup", { method: "POST" }),
    toolJobs: () => request<{ jobs: ToolJob[] }>("/api/admin/tool-jobs"),
    toolWorkerStatus: () => request<ToolWorkerStatus>("/api/admin/tool-worker/status"),
    toolWorkerRun: () => request<unknown>("/api/admin/tool-worker/run-once", { method: "POST" }),
    toolJobRetry: (id: string) =>
      request<unknown>(`/api/admin/tool-jobs/${encodeURIComponent(id)}/retry`, { method: "POST" }),
    excelRecords: () => request<{ records: ExcelRecord[] }>("/api/admin/excel-records"),
    alertRecords: () => request<{ records: AlertRecord[] }>("/api/admin/alert-records"),
    evalResults: () => request<{ summary: EvalSummary }>("/api/admin/eval-results"),
    evalRun: () => request<unknown>("/api/admin/eval-results/run", { method: "POST" }),
    auditLogs: () => request<{ logs: AuditLog[] }>("/api/admin/audit-logs"),
    updateReport: (id: string, status: "approved" | "dismissed") =>
      request<unknown>(`/api/admin/reports/${encodeURIComponent(id)}`, json("PATCH", { status })),
    updateCase: (id: string, status: "acknowledged") =>
      request<unknown>(`/api/admin/cases/${encodeURIComponent(id)}`, json("PATCH", { status })),
    addCaseNote: (id: string, note: string) =>
      request<unknown>(`/api/admin/cases/${encodeURIComponent(id)}/notes`, json("POST", { note })),
    agentStatus: () => request<AgentStatus>("/api/agent/status"),
  },
};
