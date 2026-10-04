/* 管理端数据引擎:一次快照拉全九类数据 + 全部写操作。
   三概念的值班室/导播间/守望塔共享同一份数据与动作,只差外壳。 */

import { useCallback, useState } from "react";
import { api } from "../lib/api";
import type {
  AdminSnapshot,
  KnowledgeSearchResult,
  ToolRecord,
} from "../lib/types";

const EMPTY: AdminSnapshot = {
  reports: [],
  cases: [],
  traces: [],
  knowledge: { database_chunks: 0, retrieval: "", vector_available: false, sources: [] },
  jobs: [],
  worker: { worker_threads: 0 },
  records: [],
  evals: {},
  audits: [],
};

export function useAdminData() {
  const [snapshot, setSnapshot] = useState<AdminSnapshot>(EMPTY);
  const [agentSummary, setAgentSummary] = useState<string[]>([]);
  const [detail, setDetail] = useState<{ title: string; body: unknown } | null>(null);
  const [knowledgeResults, setKnowledgeResults] = useState<KnowledgeSearchResult[]>([]);

  const showDetail = useCallback((title: string, body: unknown) => {
    setDetail({ title, body });
  }, []);

  const closeDetail = useCallback(() => setDetail(null), []);

  const refreshAll = useCallback(async () => {
    const [reports, cases, traces, knowledge, jobs, worker, excel, alerts, evals, audits, agent] =
      await Promise.all([
        api.admin.reports(),
        api.admin.cases(),
        api.admin.traces(),
        api.admin.knowledgeStatus(),
        api.admin.toolJobs(),
        api.admin.toolWorkerStatus(),
        api.admin.excelRecords(),
        api.admin.alertRecords(),
        api.admin.evalResults(),
        api.admin.auditLogs(),
        api.admin.agentStatus(),
      ]);
    setSnapshot({
      reports: reports.reports ?? [],
      cases: cases.cases ?? [],
      traces: traces.traces ?? [],
      knowledge,
      jobs: jobs.jobs ?? [],
      worker,
      records: (
        [
          ...(excel.records ?? []).map((r) => ({ ...r, type: "excel" as const })),
          ...(alerts.records ?? []).map((r) => ({ ...r, type: "alert" as const })),
        ] as ToolRecord[]
      ).sort((a, b) => String(b.created_at).localeCompare(String(a.created_at))).slice(0, 80),
      evals: evals.summary ?? {},
      audits: audits.logs ?? [],
    });
    setAgentSummary([
      `编排引擎 ${agent.runtimeHarness.name} · 调度 ${agent.agentFramework.scheduler}`,
      `存储 ${agent.memory.primary} · 工具 ${agent.toolBackend} · 队列 ${agent.toolQueue.mode}`,
      agent.agents.map((a) => a.aliasOf ? `${a.name} → ${a.aliasOf}` : a.name).join(" / "),
    ]);
  }, []);

  const act = useCallback(
    async (run: () => Promise<unknown>, detailTitle: string, after?: () => Promise<void> | void) => {
      const result = await run();
      showDetail(detailTitle, result ?? { ok: true });
      await after?.();
      await refreshAll();
    },
    [refreshAll, showDetail],
  );

  const searchKnowledge = useCallback(async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) return;
    const data = await api.admin.knowledgeSearch(trimmed);
    setKnowledgeResults(data.results ?? []);
  }, []);

  const metrics = {
    reports: snapshot.reports.length,
    high: snapshot.reports.filter((r) => r.risk_level === "high").length,
    cases: snapshot.cases.length,
    jobs: snapshot.jobs.length,
    records: snapshot.records.length,
    audits: snapshot.audits.length,
  };

  return { snapshot, metrics, agentSummary, detail, showDetail, closeDetail, knowledgeResults, searchKnowledge, refreshAll, act };
}
