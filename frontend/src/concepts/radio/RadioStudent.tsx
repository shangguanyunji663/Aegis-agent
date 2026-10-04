/* 夜航电台 · 学生端「接线台」:预设电台 / 接线记录 / 中控台。
   对话是一份接线日志;回复流式时声波起舞、ON AIR 灯亮。 */

import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { useChat } from "../../hooks/useChat";
import { useSystemStatus } from "../../hooks/useSystemStatus";
import { RISK_LABEL } from "../../lib/labels";
import { RadioBar } from "./RadioBar";
import "./radio.css";

const PRESETS = [
  { freq: "FM 88.5", title: "压力失眠", text: "我最近考试压力很大,晚上总是睡不着。" },
  { freq: "FM 91.2", title: "焦虑不安", text: "我感觉很焦虑,考试前完全静不下来。" },
  { freq: "FM 94.7", title: "情绪低落", text: "我最近情绪很低落,不太想和别人说话。" },
  { freq: "FM 99.1", title: "关系困扰", text: "我想聊聊最近和家人的矛盾。" },
];

const STATE_TEXT: Record<string, string> = {
  idle: "STANDBY · 待机",
  waiting: "CONNECTING · 正在接线",
  speaking: "ON AIR · 电波播送中",
};

export function RadioStudent() {
  const status = useSystemStatus(true);
  const { sessions, sessionId, turns, phase, error, send, openSession } = useChat();
  const [draft, setDraft] = useState("");
  const logRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
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
      <RadioBar onAir={phase !== "idle"} healthOk={status.healthOk} healthText={status.healthText} modelText={status.modelText} />

      <div className="rg-studio">
        <aside className="rg-rail">
          <div>
            <p className="rg-block-label">PRESETS · 预设电台</p>
            <div className="rg-presets" style={{ marginTop: 10 }}>
              {PRESETS.map((preset) => (
                <button
                  key={preset.freq}
                  type="button"
                  className="rg-preset"
                  onClick={() => { setDraft(preset.text); inputRef.current?.focus(); }}
                >
                  <span className="freq">{preset.freq}</span>
                  <b>{preset.title}</b>
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
            <p className="rg-block-label">CALL LOG · 接线记录</p>
            <div className="rg-logs" style={{ marginTop: 10 }}>
              {sessions.length === 0 ? (
                <p className="rg-quiet" style={{ padding: "18px 12px" }}>
                  还没有接线记录。
                  <br />
                  说点什么,或选左侧预设。
                </p>
              ) : (
                sessions.map((session) => (
                  <button
                    key={session.id}
                    type="button"
                    className={`rg-logline ${session.id === sessionId ? "on" : ""}`}
                    onClick={() => void openSession(session.id)}
                  >
                    <span className="t">{session.id === sessionId ? "NOW" : "LOG"}</span>
                    <span>
                      <b>{session.title || "未命名接线"}</b>
                      <small>CH {session.id.slice(0, 6).toUpperCase()}</small>
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>

          <div className="rg-sos">
            <b>EMERGENCY</b>
            <br />
            热线 <span className="num">12356</span> · 紧急 <span className="num">120</span>
            <br />
            或联系辅导员 / 心理中心
          </div>
        </aside>

        <section className="rg-main">
          <div className="rg-main-head">
            <span className="freq">{sessionId ? `CH ${sessionId.slice(0, 6).toUpperCase()}` : "CH ———"}</span>
            <span className="state">{STATE_TEXT[phase]}</span>
            <div className={`rg-wave ${phase === "speaking" ? "live" : ""}`} aria-hidden="true">
              {Array.from({ length: 22 }, (_, i) => (
                <i key={i} />
              ))}
            </div>
          </div>

          <div className="rg-transcript" ref={logRef} aria-live="polite">
            {turns.length === 0 ? (
              <div className="rg-standby">
                <b>波段已就绪</b>
                这条频率整夜有人守着。
                <br />
                说点什么,或从左侧预设电台开始。
              </div>
            ) : (
              turns.map((turn) => (
                <article key={turn.id} className={`rg-entry ${turn.role === "user" ? "caller" : ""}`}>
                  <span className="stamp">
                    {turn.at ?? "--:--"}
                    <br />
                    {turn.role === "user" ? "YOU" : "小暖"}
                  </span>
                  <div>
                    <p className="who">{turn.role === "user" ? "CALLER / 你" : "HOST / 小暖"}</p>
                    <p className="say">
                      {turn.content}
                      {phase === "speaking" && turn === turns.at(-1) ? <span className="rg-caret" aria-hidden="true" /> : null}
                    </p>
                    {turn.role === "assistant" && turn.content ? (
                      <div className="sig">
                        {turn.risk ? <span className={`rg-sig ${turn.risk}`}>RISK {RISK_LABEL[turn.risk]}</span> : null}
                        {turn.retrieved ? <span className="rg-sig info">知识库 ON AIR</span> : null}
                        {turn.reported ? <span className="rg-sig high">已转导播间</span> : null}
                      </div>
                    ) : null}
                  </div>
                </article>
              ))
            )}
            {phase === "waiting" && (
              <p className="rg-standby" style={{ margin: 0 }}>
                正在接线,请稍候<i style={{ fontStyle: "normal", animation: "rg-pulse 1.2s steps(1) infinite" }}> ▮</i>
              </p>
            )}
          </div>

          <form className="rg-transmit" onSubmit={submit}>
            <textarea
              ref={inputRef}
              rows={2}
              placeholder="// 对着话筒说点什么…"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={keydown}
            />
            <div className="rg-transmit-foot">
              <span className="hint">ENTER 发射 · SHIFT+ENTER 换行</span>
              {error ? <span className="rg-send-fail">{error}</span> : null}
              <button type="submit" className="rg-send" disabled={phase !== "idle"}>
                发送 TRANSMIT
              </button>
            </div>
          </form>
        </section>
      </div>
    </>
  );
}
