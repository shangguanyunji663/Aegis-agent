/* 信笺概念 · 学生端「信桌」:左信匣 / 中信纸 / 右便签。
   对话没有气泡:用户手写体,小暖打印体回信,流式即打字机逐字。 */

import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { useAuth } from "../../lib/auth";
import { useChat } from "../../hooks/useChat";
import { useSystemStatus } from "../../hooks/useSystemStatus";
import { dateLine } from "../../lib/labels";
import { RISK_LABEL } from "../../lib/labels";
import { Masthead } from "./Header";
import "./letter.css";

const TOPICS = [
  { title: "压力失眠", text: "我最近考试压力很大,晚上总是睡不着。" },
  { title: "焦虑不安", text: "我感觉很焦虑,考试前完全静不下来。" },
  { title: "情绪低落", text: "我最近情绪很低落,不太想和别人说话。" },
  { title: "关系困扰", text: "我想聊聊最近和家人的矛盾。" },
];

const CHIPS = [
  { title: "最近的压力", text: "我最近考试压力很大,晚上总是睡不着。" },
  { title: "有点低落", text: "我最近情绪很低落,不太想和别人说话。" },
  { title: "睡不好", text: "我最近总是睡不着,白天也没什么精神。" },
  { title: "随便聊聊", text: "随便聊聊吧,我今天有点烦。" },
];

export function LetterStudent() {
  const { user } = useAuth();
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

  const activeSession = sessions.find((s) => s.id === sessionId);
  const lastTurn = turns.at(-1);
  const lastRisk = lastTurn?.risk;

  return (
    <>
      <Masthead
        title="心屿邮政 · 小暖收发室"
        subtitle={`倾诉小站 · ${dateLine()}`}
        healthText={status.healthText}
        healthOk={status.healthOk}
        modelText={status.modelText}
        actions={
          <span className="lz-user">
            <strong>{user?.username}</strong>
            <span>学生信桌</span>
          </span>
        }
      />

      <div className="ls-worktop">
        <aside className="ls-drawer">
          <span className="ls-drawer-label">信匣 · 往来</span>
          <button type="button" className="ls-new" onClick={newSession}>
            新写一封
          </button>
          <div className="ls-letters">
            {sessions.length === 0 ? (
              <div className="ls-empty">
                信匣还是空的。
                <br />
                写下第一封信吧。
              </div>
            ) : (
              sessions.map((session) => (
                <button
                  key={session.id}
                  type="button"
                  className={`ls-envelope ${session.id === sessionId ? "on" : ""}`}
                  onClick={() => void openSession(session.id)}
                >
                  <strong>{session.title || "未命名信件"}</strong>
                  <small>NO.{session.id.slice(0, 6).toUpperCase()}</small>
                </button>
              ))
            )}
          </div>

          <div className="ls-postcard">
            <h3>需要立即帮助?</h3>
            心理援助热线 <span className="num">12356</span>
            <br />
            紧急情况 <span className="num">120</span>
            <br />
            或联系辅导员 / 心理中心
          </div>
        </aside>

        <section className="ls-sheet">
          <div className="ls-letterhead">
            <div>
              <h2>{activeSession ? activeSession.title || "未命名信件" : "新的一封信"}</h2>
              <p className="sub">
                {sessionId ? `SESSION ${sessionId.slice(0, 8).toUpperCase()}` : "尚未寄出"} ·{" "}
                {phase === "idle" ? "READY" : phase === "waiting" ? "WAITING" : "WRITING"}
              </p>
            </div>
            <span className={`ls-postmark ${lastRisk ?? ""}`} aria-hidden="true">
              {dateLine()}
              <br />
              {lastRisk ? `风险·${RISK_LABEL[lastRisk]}` : "心屿邮政"}
            </span>
          </div>

          <div className="ls-scroll" ref={scrollRef} aria-live="polite">
            {turns.length === 0 && (
              <div className="ls-blank">
                <p className="salutation">致小暖:</p>
                <p>
                  想到什么就写什么。压力、睡眠、关系,或任何让你卡住的事——这里的每一句都会被认真读。
                </p>
              </div>
            )}

            {turns.map((turn) =>
              turn.role === "user" ? (
                <div className="ls-turn" key={turn.id}>
                  <p className="turn-tag">致 小暖</p>
                  <p className="ls-hand">{turn.content}</p>
                </div>
              ) : (
                <div className="ls-turn" key={turn.id}>
                  <p className="turn-tag">小暖 复</p>
                  <div className="ls-typed">
                    {turn.content}
                    {phase === "speaking" && turn === turns.at(-1) ? <span className="ls-caret" aria-hidden="true" /> : null}
                    {turn.content ? (
                      <p className="ls-sign">
                        —— 小暖
                      </p>
                    ) : null}
                    {turn.content ? (
                      <div className="ls-meta-row">
                        {turn.risk ? (
                          <span className={`ls-mini-stamp ${turn.risk}`}>风险 · {RISK_LABEL[turn.risk]}</span>
                        ) : null}
                        {turn.retrieved ? <span className="ls-mini-stamp info">已检索知识库</span> : null}
                        {turn.reported ? <span className="ls-mini-stamp high">已转交值班室</span> : null}
                      </div>
                    ) : null}
                  </div>
                </div>
              ),
            )}

            {phase === "waiting" && (
              <p className="ls-waiting">
                小暖正在展信
                <i>…</i>
              </p>
            )}
          </div>

          <form className="ls-write" onSubmit={submit}>
            <textarea
              ref={inputRef}
              rows={3}
              placeholder="落笔即可,写给你自己也可以…"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={keydown}
            />
            <div className="ls-write-foot">
              <span className="hint">Enter 寄出 · Shift+Enter 换行</span>
              {error ? <span className="ls-send-fail">{error}</span> : null}
              <button type="submit" className="lg-wax" disabled={phase !== "idle"}>
                <span className="seal-dot" aria-hidden="true">封</span>
                <b>封缄寄出</b>
              </button>
            </div>
          </form>
        </section>

        <aside className="ls-notes">
          <span className="ls-notes-label">便签 · 想到就点</span>
          {TOPICS.map((topic) => (
            <button key={topic.title} type="button" className="ls-note" onClick={() => { setDraft(topic.text); inputRef.current?.focus(); }}>
              <strong>{topic.title}</strong>
              <span>点一下,帮你把话补完整</span>
            </button>
          ))}
          <div className="ls-note calm">
            <strong>60 秒放松练习</strong>
            <ol>
              <li>双脚放稳,慢慢呼气,确认此刻是安全的。</li>
              <li>说出看到的 5 个物体、听到的 3 种声音。</li>
              <li>给情绪打 0-10 分,只需观察,不急着解决。</li>
            </ol>
          </div>
          {turns.length === 0 && (
            <div className="ls-note">
              <strong>不知道怎么开头?</strong>
              {CHIPS.map((chip) => (
                <button key={chip.title} type="button" style={{ display: "block", font: "inherit", color: "var(--pine)", padding: "2px 0" }} onClick={() => { setDraft(chip.text); inputRef.current?.focus(); }}>
                  · {chip.title}
                </button>
              ))}
            </div>
          )}
        </aside>
      </div>
    </>
  );
}
