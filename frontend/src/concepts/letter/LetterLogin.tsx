/* 信笺概念 · 登录页:输入框即入口(Master 范式) → 渐进披露领取单。 */

import { useState } from "react";
import type { FormEvent } from "react";
import { useAuth } from "../../lib/auth";
import { useSystemStatus } from "../../hooks/useSystemStatus";
import { LoginHero } from "../../shared/LoginHero";
import "./letter.css";

const CHIPS = [
  { label: "压力失眠", text: "我最近考试压力很大,晚上总是睡不着。" },
  { label: "焦虑不安", text: "我感觉很焦虑,考试前完全静不下来。" },
  { label: "情绪低落", text: "我最近情绪很低落,不太想和别人说话。" },
  { label: "关系困扰", text: "我想聊聊最近和家人的矛盾。" },
  { label: "随便聊聊", text: "随便聊聊吧,我今天有点烦。" },
];

export function LetterLogin() {
  const { login, register } = useAuth();
  const status = useSystemStatus(false);
  const [showAuth, setShowAuth] = useState(false);
  const [topic, setTopic] = useState<string | null>(null);
  const [tab, setTab] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("student");
  const [password, setPassword] = useState("student123!");
  const [regUsername, setRegUsername] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [role, setRole] = useState("student");
  const [invite, setInvite] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submitLogin(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(username.trim(), password);
    } catch {
      setError("领取失败,请核对领件人与暗号。");
    } finally {
      setBusy(false);
    }
  }

  async function submitRegister(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await register({
        username: regUsername.trim(),
        password: regPassword,
        role,
        invite_code: role === "teacher" ? invite.trim() : "",
      });
    } catch {
      setError("刻章失败,请检查填写内容。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="lgh-portal">
      <div className="lgh-photo" aria-hidden="true" />
      <div className="lgh-top">
        <div className="lz-brand">
          <span className="seal-mark" aria-hidden="true">屿</span>
          <div>
            <h1 style={{ fontSize: 17 }}>心屿邮政</h1>
            <small>校园心理支持平台</small>
          </div>
        </div>
        <span className={`lz-stamp ${status.healthOk === false ? "bad" : status.healthOk ? "ok" : "quiet"}`}>
          邮路 · {status.healthText}
        </span>
      </div>

      <LoginHero
        slogan={<>每一句倾诉,都有人<em>认真对待</em>。</>}
        placeholder="今天,想聊点什么?"
        chips={CHIPS}
        actionLabel="开始倾诉"
        onActivate={(t) => { setTopic(t); setShowAuth(true); setTab("login"); setError(""); }}
      />

      {showAuth ? (
        <div className="lg-slip" style={{ width: "min(440px, 100%)", margin: 0 }}>
          {topic ? <span className="lgh-topic">想聊:{topic} —— 登录后继续</span> : null}
          {tab === "login" ? (
            <form className="lg-slip-form" onSubmit={submitLogin}>
              <h2>领取信匣</h2>
              <p className="slip-sub">登录后进入你的信桌</p>
              <div className="lg-field">
                <label htmlFor="lg-user">领件人 / 用户名</label>
                <input id="lg-user" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
              </div>
              <div className="lg-field">
                <label htmlFor="lg-pass">取件暗号 / 密码</label>
                <input id="lg-pass" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
              </div>
              <button type="submit" className="lg-wax" disabled={busy}>
                <span className="seal-dot" aria-hidden="true">启</span>
                <b>{busy ? "核对中" : "领取信匣"}</b>
              </button>
            </form>
          ) : (
            <form className="lg-slip-form" onSubmit={submitRegister}>
              <h2>刻一枚新章</h2>
              <p className="slip-sub">注册后拥有自己的信匣</p>
              <div className="lg-field">
                <label htmlFor="lg-reg-user">用户名</label>
                <input id="lg-reg-user" autoComplete="username" placeholder="2-32 位字母、数字、下划线或中文" value={regUsername} onChange={(e) => setRegUsername(e.target.value)} />
              </div>
              <div className="lg-field">
                <label htmlFor="lg-reg-pass">密码(至少 6 位)</label>
                <input id="lg-reg-pass" type="password" autoComplete="new-password" value={regPassword} onChange={(e) => setRegPassword(e.target.value)} />
              </div>
              <div className="lg-field">
                <label htmlFor="lg-reg-role">身份</label>
                <select id="lg-reg-role" value={role} onChange={(e) => setRole(e.target.value)}>
                  <option value="student">学生</option>
                  <option value="teacher">教师(需邀请码)</option>
                </select>
              </div>
              {role === "teacher" && (
                <div className="lg-field">
                  <label htmlFor="lg-invite">教师邀请码</label>
                  <input id="lg-invite" type="password" placeholder="学校发放的邀请码" value={invite} onChange={(e) => setInvite(e.target.value)} />
                </div>
              )}
              <button type="submit" className="lg-wax" disabled={busy}>
                <span className="seal-dot" aria-hidden="true">刻</span>
                <b>{busy ? "刻章中" : "注册并进入"}</b>
              </button>
            </form>
          )}
          {error ? <p className="lg-annotate" role="alert">{error}</p> : null}
          <p className="lg-swap">
            {tab === "login" ? (
              <>还没有信匣?<button type="button" onClick={() => { setTab("register"); setError(""); }}>刻一枚新章</button></>
            ) : (
              <>已有信匣?<button type="button" onClick={() => { setTab("login"); setError(""); }}>返回领取</button></>
            )}
          </p>
          <div className="lg-memo">演示信匣 student / student123! · 值班信匣 admin / admin123!</div>
        </div>
      ) : (
        <p className="lgh-alt">
          已有信匣?<button type="button" onClick={() => { setShowAuth(true); setTab("login"); }}>直接登录</button>
          {" · "}没有信匣?<button type="button" onClick={() => { setShowAuth(true); setTab("register"); }}>注册一个</button>
        </p>
      )}

      <p className="lgh-foot">
        心屿用于支持与陪伴,不提供医学诊断,不能替代专业心理咨询或危机干预。
        <br />需要立即帮助?热线 <b>12356</b> · 紧急 <b>120</b>
      </p>
    </div>
  );
}
