/* 共享工作台:左列表筛选 + 中审阅文档 + 右工具区(国内 agent 控制台三段式)。
   三个概念共用这套 DOM,隐喻由概念令牌与页眉表达;
   数据与动作全部来自 useAdminData,此处不含任何 fetch。 */

import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { useAdminData } from "../hooks/useAdminData";
import "./console.css";
import {
  ACTION_LABEL,
  CASE_STATUS_LABEL,
  EVAL_KEY_LABEL,
  INTENT_LABEL,
  JOB_STATUS_LABEL,
  KIND_LABEL,
  REPORT_STATUS_LABEL,
  RISK_LABEL,
  TARGET_LABEL,
} from "../lib/labels";
import type { CaseItem, ReportItem, ToolJob, TraceItem } from "../lib/types";

type PrimaryTab = "cases" | "reports" | "traces" | "jobs" | "audits";

interface Selection {
  kind: PrimaryTab;
  id: string;
}

const TABS: { key: PrimaryTab; label: string }[] = [
  { key: "cases", label: "个案" },
  { key: "reports", label: "风险报告" },
  { key: "traces", label: "对话回放" },
  { key: "jobs", label: "工具任务" },
  { key: "audits", label: "审计" },
];

function Badge({ tone, children }: { tone: string; children: string }) {
  return <span className={`cns-badge ${tone}`}>{children}</span>;
}

const riskTone = (level: string) => (level === "high" ? "high" : level === "medium" ? "medium" : "low");

export function AdminConsole() {
  const {
    snapshot,
    metrics,
    agentSummary,
    knowledgeResults,
    searchKnowledge,
    refreshAll,
    act,
  } = useAdminData();

  const [tab, setTab] = useState<PrimaryTab>("cases");
  const [selected, setSelected] = useState<Selection | null>(null);
  const [showJson, setShowJson] = useState(false);
  const [query, setQuery] = useState("");
  const [filename, setFilename] = useState("");
  const [content, setContent] = useState("");
  const [noteDraft, setNoteDraft] = useState<{ id: string; text: string } | null>(null);
  const [armDismiss, setArmDismiss] = useState<string | null>(null);

  const pick = (kind: PrimaryTab, id: string) => {
    setSelected({ kind, id });
    setNoteDraft(null);
    setArmDismiss(null);
    setShowJson(false);
  };

  useEffect(() => {
    refreshAll().catch(() => { /* 401 由 api 层统一处理 */ });
  }, [refreshAll]);

  const rows = useMemo(() => {
    switch (tab) {
      case "cases":
        return snapshot.cases.map((c) => ({
          id: c.id,
          title: c.id,
          sub: c.summary || c.handoff_summary || "暂无摘要",
          badges: [
            { tone: riskTone(c.risk_level), text: RISK_LABEL[c.risk_level] },
            { tone: c.status === "open" ? "quiet" : "ok", text: CASE_STATUS_LABEL[c.status] },
          ],
        }));
      case "reports":
        return snapshot.reports.map((r) => ({
          id: r.id,
          title: r.id,
          sub: r.summary || r.message || "",
          badges: [
            { tone: riskTone(r.risk_level), text: RISK_LABEL[r.risk_level] },
            { tone: r.status === "pending" ? "medium" : "ok", text: REPORT_STATUS_LABEL[r.status] },
          ],
        }));
      case "traces":
        return snapshot.traces.map((t) => ({
          id: t.message_id,
          title: t.message_id,
          sub: t.answer || "",
          badges: [
            { tone: "quiet", text: INTENT_LABEL[t.intent] ?? t.intent },
            { tone: riskTone(t.risk_level), text: RISK_LABEL[t.risk_level] },
          ],
        }));
      case "jobs":
        return snapshot.jobs.map((j) => ({
          id: j.id,
          title: `${KIND_LABEL[j.kind] ?? j.kind} ${j.id}`,
          sub: `已执行 ${j.attempts}/${j.max_attempts} 次`,
          badges: [{ tone: j.status === "success" ? "ok" : j.status === "dead" ? "hot" : "medium", text: JOB_STATUS_LABEL[j.status] }],
        }));
      case "audits":
        return snapshot.audits.map((a, i) => ({
          id: `${a.action}-${i}`,
          title: ACTION_LABEL[a.action] ?? a.action,
          sub: `${a.actor_username} · ${TARGET_LABEL[a.target_type] ?? a.target_type} ${a.target_id}`,
          badges: [],
        }));
    }
  }, [tab, snapshot]);

  const activeItem = useMemo(() => {
    if (!selected) return null;
    switch (selected.kind) {
      case "cases":
        return { kind: selected.kind, item: snapshot.cases.find((x) => x.id === selected.id) ?? null };
      case "reports":
        return { kind: selected.kind, item: snapshot.reports.find((x) => x.id === selected.id) ?? null };
      case "traces":
        return { kind: selected.kind, item: snapshot.traces.find((x) => x.message_id === selected.id) ?? null };
      case "jobs":
        return { kind: selected.kind, item: snapshot.jobs.find((x) => x.id === selected.id) ?? null };
      default:
        return null;
    }
  }, [selected, snapshot]);

  function renderStage() {
    if (!selected || !activeItem?.item) {
      const pending = snapshot.reports.filter((r) => r.status === "pending");
      return (
        <div className="cns-stage-body">
          <div className="cns-doc-section">
            <p className="cns-doc-label">NOW · 正在发生</p>
            {pending.length === 0 ? (
              <p className="cns-mini-note">没有待审批的报告。左侧列表随时可查历史个案与回放。</p>
            ) : (
              pending.slice(0, 3).map((r) => (
                <button key={r.id} type="button" className="cns-row" style={{ width: "100%" }} onClick={() => pick("reports", r.id)}>
                  <span className="cns-row-top">
                    <b className="cns-row-title">{r.id}</b>
                    <Badge tone={riskTone(r.risk_level)}>{RISK_LABEL[r.risk_level]}</Badge>
                  </span>
                  <span className="cns-row-sub">{r.summary || r.message || ""}</span>
                </button>
              ))
            )}
          </div>
          <div className="cns-doc-section">
            <p className="cns-doc-label">RECENT · 最近动态</p>
            {snapshot.audits.slice(0, 5).map((a, i) => (
              <p key={i} className="cns-mini-note">
                {ACTION_LABEL[a.action] ?? a.action} · {a.actor_username} · {TARGET_LABEL[a.target_type] ?? a.target_type} {a.target_id}
              </p>
            ))}
          </div>
        </div>
      );
    }

    const raw = JSON.stringify(activeItem.item, null, 2);
    if (selected.kind === "cases") {
      const c = activeItem.item as CaseItem;
      return (
        <div className="cns-stage-body">
          <div className="cns-doc-head">
            <span className="cns-doc-title">{c.id}</span>
            <Badge tone={riskTone(c.risk_level)}>{RISK_LABEL[c.risk_level]}</Badge>
            <Badge tone={c.status === "open" ? "quiet" : "ok"}>{CASE_STATUS_LABEL[c.status]}</Badge>
          </div>
          <div className="cns-doc-section">
            <p className="cns-doc-label">SUMMARY · 交接摘要</p>
            <p className="cns-doc-text">{c.summary || c.handoff_summary || "暂无摘要"}</p>
          </div>
          <div className="cns-doc-section">
            <p className="cns-doc-label">NOTES · 跟进备注</p>
            {c.notes?.length ? (
              c.notes.map((n, i) => <p key={i} className="cns-doc-text">· {n.note}</p>)
            ) : (
              <p className="cns-mini-note">还没有备注。</p>
            )}
          </div>
          <div className="cns-actions">
            {c.status === "open" && (
              <button type="button" className="cns-btn primary" onClick={() => act(() => api.admin.updateCase(c.id, "acknowledged"), "已确认接案")}>
                确认接案
              </button>
            )}
            {noteDraft?.id === c.id ? (
              <>
                <textarea
                  className="cns-input"
                  style={{ flex: 1, minHeight: 56 }}
                  placeholder="写下跟进备注…"
                  value={noteDraft.text}
                  autoFocus
                  onChange={(e) => setNoteDraft({ id: c.id, text: e.target.value })}
                />
                <button
                  type="button"
                  className="cns-btn primary"
                  disabled={!noteDraft.text.trim()}
                  onClick={async () => {
                    await act(() => api.admin.addCaseNote(c.id, noteDraft.text.trim()), "已添加备注");
                    setNoteDraft(null);
                  }}
                >
                  保存备注
                </button>
                <button type="button" className="cns-btn mute" onClick={() => setNoteDraft(null)}>
                  取消
                </button>
              </>
            ) : (
              <button type="button" className="cns-btn" onClick={() => setNoteDraft({ id: c.id, text: "" })}>
                添加备注
              </button>
            )}
            <button type="button" className="cns-btn mute" onClick={() => setShowJson((v) => !v)}>
              {showJson ? "收起原始数据" : "原始 JSON"}
            </button>
          </div>
          {showJson && <pre className="cns-json" style={{ marginTop: 12 }}>{raw}</pre>}
        </div>
      );
    }
    if (selected.kind === "reports") {
      const r = activeItem.item as ReportItem;
      return (
        <div className="cns-stage-body">
          <div className="cns-doc-head">
            <span className="cns-doc-title">{r.id}</span>
            <Badge tone={riskTone(r.risk_level)}>{RISK_LABEL[r.risk_level]}</Badge>
            <Badge tone={r.status === "pending" ? "medium" : "ok"}>{REPORT_STATUS_LABEL[r.status]}</Badge>
          </div>
          <div className="cns-doc-section">
            <p className="cns-doc-label">SUMMARY · 风险摘要</p>
            <p className="cns-doc-text">{r.summary || r.message || "暂无内容"}</p>
          </div>
          {r.status === "pending" && (
            <div className="cns-actions">
              <button type="button" className="cns-btn primary" onClick={() => act(() => api.admin.updateReport(r.id, "approved"), "已批准")}>
                批准跟进
              </button>
              <button
                type="button"
                className={`cns-btn ${armDismiss === r.id ? "danger" : "mute"}`}
                onClick={() => {
                  if (armDismiss === r.id) {
                    void act(() => api.admin.updateReport(r.id, "dismissed"), "已驳回");
                    setArmDismiss(null);
                  } else {
                    setArmDismiss(r.id);
                  }
                }}
              >
                {armDismiss === r.id ? "确认驳回?" : "驳回"}
              </button>
              <button type="button" className="cns-btn mute" onClick={() => setShowJson((v) => !v)}>
                {showJson ? "收起原始数据" : "原始 JSON"}
              </button>
            </div>
          )}
          {showJson && <pre className="cns-json" style={{ marginTop: 12 }}>{raw}</pre>}
        </div>
      );
    }
    if (selected.kind === "traces") {
      const t = activeItem.item as TraceItem;
      return (
        <div className="cns-stage-body">
          <div className="cns-doc-head">
            <span className="cns-doc-title">{t.message_id}</span>
            <Badge tone="quiet">{INTENT_LABEL[t.intent] ?? t.intent}</Badge>
            <Badge tone={riskTone(t.risk_level)}>{RISK_LABEL[t.risk_level]}</Badge>
          </div>
          <div className="cns-doc-section">
            <p className="cns-doc-label">REPLAY · 回放</p>
            <p className="cns-doc-text">{t.answer || "暂无回放内容"}</p>
          </div>
        </div>
      );
    }
    const j = activeItem.item as ToolJob;
    return (
      <div className="cns-stage-body">
        <div className="cns-doc-head">
          <span className="cns-doc-title">{j.id}</span>
          <Badge tone={j.status === "success" ? "ok" : j.status === "dead" ? "hot" : "medium"}>
            {JOB_STATUS_LABEL[j.status]}
          </Badge>
        </div>
        <div className="cns-doc-section">
          <p className="cns-doc-label">JOB · 任务信息</p>
          <p className="cns-doc-text">
            {KIND_LABEL[j.kind] ?? j.kind} · 已执行 {j.attempts}/{j.max_attempts} 次
          </p>
        </div>
        {j.status !== "success" && (
          <div className="cns-actions">
            <button type="button" className="cns-btn primary" onClick={() => act(() => api.admin.toolJobRetry(j.id), "已重试")}>
              重试
            </button>
          </div>
        )}
        {showJson && <pre className="cns-json" style={{ marginTop: 12 }}>{raw}</pre>}
      </div>
    );
  }

  return (
    <>
      <div className="cns-stats">
        <button type="button" className="cns-stat" onClick={() => setTab("reports")}><b className="num">{metrics.reports}</b> 报告</button>
        <button type="button" className="cns-stat hot" onClick={() => { setTab("reports"); }}><b className="num">{metrics.high}</b> 高风险</button>
        <button type="button" className="cns-stat" onClick={() => setTab("cases")}><b className="num">{metrics.cases}</b> 个案</button>
        <button type="button" className="cns-stat" onClick={() => setTab("jobs")}><b className="num">{metrics.jobs}</b> 任务</button>
        <button type="button" className="cns-stat" onClick={() => setTab("audits")}><b className="num">{metrics.audits}</b> 审计</button>
        <span className="cns-stat-divider" />
        <button type="button" className="cns-stat" onClick={() => void refreshAll()}>刷新</button>
      </div>

      <main className="cns">
        <section className="cns-pane">
          <div className="cns-pane-head">
            <div className="cns-tabs" role="tablist">
              {TABS.map((t) => (
                <button
                  key={t.key}
                  type="button"
                  role="tab"
                  aria-selected={t.key === tab}
                  className={`cns-tab ${t.key === tab ? "on" : ""}`}
                  onClick={() => { setTab(t.key); setSelected(null); }}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          <div className="cns-list">
            {rows.length === 0 ? (
              <div className="cns-empty">
                这里还是空的。
                <br />
                有新的个案或报告时,会第一时间出现在「正在发生」。
              </div>
            ) : (
              rows.map((row) => (
                <button
                  key={row.id}
                  type="button"
                  className={`cns-row ${selected?.id === row.id ? "on" : ""}`}
                  onClick={() => pick(tab, row.id)}
                >
                  <span className="cns-row-top">
                    <b className="cns-row-title">{row.title}</b>
                    {row.badges.map((b) => <Badge key={b.text} tone={b.tone}>{b.text}</Badge>)}
                  </span>
                  <span className="cns-row-sub">{row.sub}</span>
                </button>
              ))
            )}
          </div>
        </section>

        <section className="cns-pane">
          <div className="cns-pane-head">
            <span className="cns-pane-title">REVIEW · 审阅台</span>
            {selected ? <span className="cns-badge quiet">{selected.id}</span> : null}
          </div>
          {renderStage()}
        </section>

        <section className="cns-pane cns-tools-pane">
          <div className="cns-pane-head">
            <span className="cns-pane-title">TOOLS · 工具区</span>
          </div>
          <div className="cns-tools">
            <div className="cns-tool">
              <p className="cns-tool-title">知识库 · {snapshot.knowledge.database_chunks} chunks</p>
              <input className="cns-input" placeholder="关键词检索" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && void searchKnowledge(query)} />
              {knowledgeResults.slice(0, 3).map((r) => (
                <p key={`${r.source}-${r.score}`} className="cns-mini-note">{r.source} · {r.score}: {r.snippet.slice(0, 48)}…</p>
              ))}
              <div className="cns-mini-row" style={{ margin: "7px 0" }}>
                <button type="button" className="cns-mini" onClick={() => void searchKnowledge(query)}>检索</button>
                <button type="button" className="cns-mini" onClick={() => void act(() => api.admin.knowledgeRebuild(), "知识库重建结果")}>重建索引</button>
                <button type="button" className="cns-mini" onClick={() => void act(() => api.admin.knowledgeBackup(), "知识库备份结果")}>备份</button>
              </div>
              <input className="cns-input" placeholder="文件名,如:睡眠知识.md" value={filename} onChange={(e) => setFilename(e.target.value)} />
              <textarea className="cns-input" placeholder="粘贴文章内容(Markdown 或纯文本)" value={content} onChange={(e) => setContent(e.target.value)} />
              <button
                type="button"
                className="cns-mini"
                onClick={() => {
                  if (!filename.trim() || !content.trim()) return;
                  void act(() => api.admin.knowledgeUpload(filename.trim(), content.trim()), "知识收录结果");
                  setContent("");
                }}
              >
                收录新页
              </button>
              <div className="cns-chips">
                {snapshot.knowledge.sources.slice(0, 6).map((s) => <span key={s} className="cns-chip">{s}</span>)}
              </div>
            </div>

            <div className="cns-tool">
              <p className="cns-tool-title">协作状态 · {snapshot.worker.worker_threads} 线程</p>
              {agentSummary.map((line) => <p key={line} className="cns-mini-note">{line}</p>)}
            </div>

            <div className="cns-tool">
              <p className="cns-tool-title">评测</p>
              <p className="cns-mini-note">内置测试题,不使用真实学生数据。</p>
              <div className="cns-mini-row" style={{ marginTop: 7 }}>
                <button type="button" className="cns-mini" onClick={() => void act(() => api.admin.toolWorkerRun(), "工具任务执行结果")}>派发任务</button>
                <button type="button" className="cns-mini" onClick={() => void act(() => api.admin.evalRun(), "综合评测结果")}>运行评测</button>
              </div>
              {Object.keys(snapshot.evals).length > 0 && (
                <div className="cns-tiles">
                  {Object.entries(snapshot.evals).map(([key, value]) => (
                    <div key={key} className="cns-tile">
                      <b>{String(value ?? 0)}</b>
                      <span>{EVAL_KEY_LABEL[key] ?? key}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {snapshot.records.length > 0 && (
              <div className="cns-tool">
                <p className="cns-tool-title">执行记录 · 最近</p>
                {snapshot.records.slice(0, 6).map((r) => (
                  <p key={`${r.type}-${r.id}`} className="cns-mini-note">
                    {r.type === "excel" ? "台账" : "预警"} {r.id} · {r.status}
                  </p>
                ))}
              </div>
            )}
          </div>
        </section>
      </main>
    </>
  );
}
