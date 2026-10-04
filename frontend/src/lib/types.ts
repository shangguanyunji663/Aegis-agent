/* 后端 API 的类型定义。SSE 事件、风险分级、管理端实体都在这里收口,
   心理场景的事件流比一般聊天复杂(风险/路由/工具/升级),不允许 any 混流。 */

export type Role = "student" | "teacher" | "admin";
export type RiskLevel = "low" | "medium" | "high";

export interface User {
  username: string;
  role: Role;
}

export interface HealthPayload {
  status: string;
}

export interface AgentStatusModels {
  base_provider: "mock" | "openai" | "ollama" | string;
  base_model: string;
}

export interface AgentStatus {
  models: AgentStatusModels;
  runtimeHarness: { name: string };
  agentFramework: { scheduler: string };
  memory: { primary: string };
  toolBackend: "internal" | "mcp" | string;
  toolQueue: { mode: string };
  agents: { name: string; aliasOf?: string }[];
}

/* ---------- 会话与对话 ---------- */

export interface SessionSummary {
  id: string;
  title: string;
}

export interface ChatMessage {
  role: "USER" | "ASSISTANT";
  content: string;
}

export interface SessionDetail {
  session: {
    id: string;
    messages: ChatMessage[];
  };
}

export type ChatStreamEvent =
  | { event: "start"; session_id: string }
  | { event: "route"; risk_level: RiskLevel }
  | { event: "skill"; name: string }
  | { event: "report" }
  | { event: "token"; content: string }
  | { event: "error" }
  | { event: "done"; response?: { session_id?: string; answer?: string } };

/* ---------- 管理端 ---------- */

export type ReportStatus = "pending" | "approved" | "dismissed";
export type CaseStatus = "open" | "acknowledged";
export type JobStatus = "pending" | "running" | "success" | "dead";

export interface ReportItem {
  id: string;
  risk_level: RiskLevel;
  status: ReportStatus;
  summary?: string;
  message?: string;
}

export interface CaseItem {
  id: string;
  risk_level: RiskLevel;
  status: CaseStatus;
  summary?: string;
  handoff_summary?: string;
  notes?: { note: string }[];
}

export interface TraceItem {
  message_id: string;
  intent: string;
  risk_level: RiskLevel;
  answer?: string;
}

export interface KnowledgeStatus {
  database_chunks: number;
  retrieval: string;
  vector_available: boolean;
  sources: string[];
}

export interface KnowledgeSearchResult {
  source: string;
  score: number;
  snippet: string;
}

export interface ToolJob {
  id: string;
  kind: string;
  status: JobStatus;
  attempts: number;
  max_attempts: number;
}

export interface ToolWorkerStatus {
  worker_threads: number;
}

export interface ExcelRecord {
  type: "excel";
  id: string;
  status: string;
  file_path: string;
  created_at: string;
}

export interface AlertRecord {
  type: "alert";
  id: string;
  status: string;
  channel: string;
  recipient?: string;
  created_at: string;
}

export type ToolRecord = ExcelRecord | AlertRecord;

export interface EvalSummary {
  routing_accuracy?: number;
  risk_accuracy?: number;
  retrieval_hit_rate?: number;
  skill_accuracy?: number;
  safety_pass_rate?: number;
  multi_turn_accuracy?: number;
  [key: string]: number | undefined;
}

export interface AuditLog {
  action: string;
  actor_username: string;
  target_type: string;
  target_id: string;
}

export interface AdminSnapshot {
  reports: ReportItem[];
  cases: CaseItem[];
  traces: TraceItem[];
  knowledge: KnowledgeStatus;
  jobs: ToolJob[];
  worker: ToolWorkerStatus;
  records: ToolRecord[];
  evals: EvalSummary;
  audits: AuditLog[];
}
