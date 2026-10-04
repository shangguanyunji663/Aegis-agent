/* 后端英文枚举 → 教师可读中文文案;未收录的值原样展示。 */

import type { CaseStatus, JobStatus, ReportStatus, RiskLevel } from "./types";

export const RISK_LABEL: Record<RiskLevel, string> = {
  high: "高风险",
  medium: "中风险",
  low: "低风险",
};

export const REPORT_STATUS_LABEL: Record<ReportStatus, string> = {
  pending: "待审批",
  approved: "已批准",
  dismissed: "已驳回",
};

export const CASE_STATUS_LABEL: Record<CaseStatus, string> = {
  open: "待跟进",
  acknowledged: "跟进中",
};

export const JOB_STATUS_LABEL: Record<JobStatus, string> = {
  pending: "等待执行",
  running: "执行中",
  success: "成功",
  dead: "多次失败待处理",
};

export const KIND_LABEL: Record<string, string> = {
  create_alert: "预警记录",
  send_email: "邮件通知",
  write_ledger: "风险台账",
  create_handoff_summary: "交接摘要",
  follow_up_suggestion: "跟进建议",
  lookup_resource: "资源查询",
};

export const INTENT_LABEL: Record<string, string> = {
  companion: "陪伴",
  counseling: "咨询",
  research: "查资料",
  risk: "风险求助",
};

export const ACTION_LABEL: Record<string, string> = {
  update_report: "审批报告",
  update_case_status: "更新个案状态",
  add_case_note: "添加个案备注",
  retry_tool_job: "重试工具任务",
  rebuild_knowledge: "重建知识库",
  backup_knowledge: "备份知识库",
  run_evaluation: "运行评测",
  dispatch_tool_worker: "派发工具任务",
};

export const TARGET_LABEL: Record<string, string> = {
  report: "风险报告",
  case: "个案",
  tool_job: "工具任务",
  knowledge_index: "知识库",
  evaluation: "评测",
};

export const AGENT_LABEL: Record<string, string> = {
  MemoryAgent: "记忆智能体",
  SupervisorAgent: "督导智能体",
  LeadAgent: "分诊智能体",
  RiskGuardianAgent: "风险守护智能体",
  KnowledgeAgent: "知识智能体",
  CounselorAgent: "咨询智能体",
  CompanionAgent: "陪伴智能体",
};

export const TOOL_BACKEND_LABEL: Record<string, string> = {
  internal: "内置队列",
  mcp: "MCP 后端",
};

export const QUEUE_LABEL: Record<string, string> = {
  "background-worker": "后台队列",
  inline: "同步执行",
};

export const PROVIDER_LABEL: Record<string, string> = {
  mock: "演示模型",
  openai: "在线模型",
  ollama: "本地模型",
};

export const EVAL_KEY_LABEL: Record<string, string> = {
  routing_accuracy: "路由准确率",
  risk_accuracy: "风险准确率",
  retrieval_hit_rate: "检索命中率",
  skill_accuracy: "技能准确率",
  safety_pass_rate: "安全通过率",
  multi_turn_accuracy: "多轮准确率",
};

export function greeting(): string {
  const h = new Date().getHours();
  if (h < 5) return "夜深了";
  if (h < 11) return "早上好";
  if (h < 13) return "中午好";
  if (h < 18) return "下午好";
  return "晚上好";
}

export function dateLine(now = new Date()): string {
  const week = ["日", "一", "二", "三", "四", "五", "六"][now.getDay()];
  return `${now.getMonth() + 1} 月 ${now.getDate()} 日 周${week}`;
}

export function clockLine(now = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(now.getHours())}:${pad(now.getMinutes())}`;
}
