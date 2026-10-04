/* 群群岛屿 · 学生端「航海日志」:左海图 / 中日志 / 右罗盘方位。
   对话是航海日志:用户是船讯,小暖是灯塔回信;风险用旗语表达。 */

import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { useChat } from "../../hooks/useChat";
import { useSystemStatus } from "../../hooks/useSystemStatus";
import { RISK_LABEL } from "../../lib/labels";
import { AtlasBar } from "./AtlasBar";
import "./atlas.css";

const BEARINGS = [
  { mark: "N", title: "压力失眠", text: "我最近考试压力很大,晚上总是睡不着。" },
  { mark: "E", title: "焦虑不安", text: "我感觉很焦虑,考试前完全静不下来。" },
  { mark: "S", title: "情绪低落", text: "我最近情绪很低落,不太想和别人说话。" },
  { mark: "W", title: "关系困扰", text: "我想聊聊最近和家人的矛盾。" },
];

function RiskFlag({ level }: { level: "low" | "medium" | "high" | undefined }) {
  if (!level) return null;
  return (
    <>
      <span className={`flag ${level}`} aria-hidden="true" />
      风向 · {RISK_LABEL[level]}
    </>
  );
}

export function AtlasStudent() {
  const status = useSystemStatus(true);
  const { sessions, sessionId, turns, phase, error, send, openSession, newSession } = useChat();
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [turns, phase]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const text = draft;
    if (!text.trim()) return;
    setDraft("");
    void send(text);
  }

  function keydown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      (event.currentTarget.form as HTMLFormElement).requestSubmit();
    }
  }

  return (
    <>
      <AtlasBar healthOk={status.healthOk} healthText={status.healthText} modelText={status.modelText} />

      <div className="at-deck">
        <aside className="at-chart-panel">
          <span className="at-panel-label">海图 · 我的岛屿</span>
          <button type="button" className="at-set-sail" onClick={newSession}>
            新的航程
          </button>
          <div className="at-isles">
            {sessions.length === 0 ? (
              <p className="at-quiet">
                海图还是空白。
                <br />
                第一座岛等你命名。
              </p>
            ) : (
              sessions.map((session) => (
                <button
                  key={session.id}
                  type="button"
                  className={`at-isle ${session.id === sessionId ? "on" : ""}`}
                  onClick={() => void openSession(session.id)}
                >
                  <span className="isle-dot" aria-hidden="true" />
                  <span>
                    <b>{session.title || "无名小岛"}</b>
                    <small>ISLE {session.id.slice(0, 6).toUpperCase()}</small>
                  </span>
                </button>
              ))
            )}
          </div>

          <div className="at-mayday">
            <b>MAYDAY · 需要立即帮助</b>
            <br />
            <span className="flag high" aria-hidden="true" />
            心理援助热线 <span className="num">12356</span>
            <br />
            <span className="flag high" aria-hidden="true" />
            紧急情况 <span className="num">120</span>
            <br />
            <span className="flag medium" aria-hidden="true" />
            或联系辅导员 / 心理中心
          </div>
        </aside>

        <section className="at-logbook-main">
          <div className="at-log-head">
            <div>
              <h2>航海日志</h2>
              <p className="sub">
                {sessionId ? `VOYAGE ${sessionId.slice(0, 8).toUpperCase()}` : "未启航"} ·{" "}
                {phase === "idle" ? "ANCHORED" : phase === "waiting" ? "SIGNALING" : "REPLYING"}
              </p>
            </div>
            <div className="at-coords" aria-hidden="true">
              {sessionId ? `30°14′N 120°09′E` : `— — —`}
              <br />
              心屿海域
            </div>
          </div>

          <div className="at-entries" ref={scrollRef} aria-live="polite">
            {turns.length === 0 ? (
              <div className="at-horizon">
                <b>海面很静</b>
                把想说的话写进日志,灯塔的守望者小暖会回信。
                <br />
                不知从何说起时,看看右侧的罗盘方位。
              </div>
            ) : (
              turns.map((turn) => (
                <article key={turn.id} className={`at-entry ${turn.role === "user" ? "crew" : "keeper"}`}>
                  <p className="role-line">{turn.role === "user" ? "船讯 · 我" : "灯塔回信 · 小暖"}</p>
                  <p className="words">
                    {turn.content}
                    {phase === "speaking" && turn === turns.at(-1) ? <span className="at-caret" aria-hidden="true" /> : null}
                  </p>
                  {turn.role === "assistant" && turn.content ? (
                    <div className="witness">
                      <RiskFlag level={turn.risk} />
                      {turn.retrieved ? "· 已查航海图鉴" : ""}
                      {turn.reported ? "· 已通知守望塔" : ""}
                    </div>
                  ) : null}
                </article>
              ))
            )}
            {phase === "waiting" && (
              <p className="at-horizon" style={{ margin: 0 }}>
                灯塔收到信号,正在回信
                <span className="at-caret" aria-hidden="true" />
              </p>
            )}
          </div>

          <form className="at-record" onSubmit={submit}>
            <textarea
              ref={inputRef}
              rows={2}
              placeholder="把这一页写给灯塔…"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={keydown}
            />
            <div className="at-record-foot">
              <span className="hint">ENTER 记入日志 · SHIFT+ENTER 换行</span>
              {error ? <span className="at-fail">{error}</span> : null}
              <button type="submit" className="at-log-btn" disabled={phase !== "idle"}>
                记入日志
              </button>
            </div>
          </form>
        </section>

        <aside className="at-compass-col">
          <span className="at-panel-label">罗盘 · 方位速选</span>
          {BEARINGS.map((bearing) => (
            <button
              key={bearing.mark}
              type="button"
              className="at-bearing"
              onClick={() => { setDraft(bearing.text); inputRef.current?.focus(); }}
            >
              <span className="bearing-mark" aria-hidden="true">{bearing.mark}</span>
              <span>
                <b>{bearing.title}</b>
                <span>点一下,帮你把话补完整</span>
              </span>
            </button>
          ))}
          <div className="at-calm-card">
            <b>平浪 60 秒</b>
            <ol>
              <li>双脚放稳,慢慢呼气,确认此刻是安全的。</li>
              <li>说出看到的 5 个物体、听到的 3 种声音。</li>
              <li>给情绪打 0-10 分,只需观察,不急着解决。</li>
            </ol>
          </div>
        </aside>
      </div>
    </>
  );
}
