/* 夜航电台 · 登录页:输入框即入口 → 渐进披露开机面板。 */

import { useState } from "react";
import type { FormEvent } from "react";
import { useAuth } from "../../lib/auth";
import { useSystemStatus } from "../../hooks/useSystemStatus";
import { LoginHero } from "../../shared/LoginHero";
import "./radio.css";

const CHIPS = [
  { label: "压力失眠", text: "我最近考试压力很大,晚上总是睡不着。" },
  { label: "焦虑不安", text: "我感觉很焦虑,考试前完全静不下来。" },
  { label: "情绪低落", text: "我最近情绪很低落,不太想和别人说话。" },
  { label: "关系困扰", text: "我想聊聊最近和家人的矛盾。" },
  { label: "随便聊聊", text: "随便聊聊吧,我今天有点烦。" },
];

export function RadioLogin() {
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
      setError("接通失败,请核对呼号与密码。");
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
      setError("注册失败,请检查填写内容。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="lgh-portal">
      <div className="lgh-photo" aria-hidden="true" />
      <div className="lgh-top">
        <div className="rg-brand">
          <div>
            <span className="callword">心屿夜航</span>
            <small>LATE-NIGHT SUPPORT RADIO</small>
          </div>
        </div>
        <span className={`rg-led ${status.healthOk === false ? "bad" : status.healthOk ? "ok" : ""}`}>
          SIGNAL {status.healthOk === false ? "LOST" : status.healthOk ? "OK" : "TESTING"}
        </span>
      </div>

      <LoginHero
        slogan={<>把今晚的心事,<em>说给夜航听</em>。</>}
        placeholder="接通夜航,说点什么…"
        chips={CHIPS}
        actionLabel="接通热线"
        onActivate={(t) => { setTopic(t); setShowAuth(true); setTab("login"); setError(""); }}
      />

      {showAuth ? (
        <div className="rg-console" style={{ width: "min(440px, 100%)", margin: 0 }}>
          <div className="rg-dial" aria-hidden="true"><i /></div>
          {topic ? <span className="lgh-topic">想聊:{topic} —— 接通后继续</span> : null}
          {tab === "login" ? (
            <form onSubmit={submitLogin}>
              <div className="rg-field">
                <label htmlFor="rg-user">CALLSIGN / 呼号(用户名)</label>
                <input id="rg-user" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
              </div>
              <div className="rg-field">
                <label htmlFor="rg-pass">PASSWORD / 密码</label>
                <input id="rg-pass" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
              </div>
              <button type="submit" className="rg-power" disabled={busy}>
                {busy ? "接通中…" : "接通电源"}
              </button>
            </form>
          ) : (
            <form onSubmit={submitRegister}>
              <div className="rg-field">
                <label htmlFor="rg-reg-user">新呼号 / 用户名</label>
                <input id="rg-reg-user" autoComplete="username" placeholder="2-32 位字母、数字、下划线或中文" value={regUsername} onChange={(e) => setRegUsername(e.target.value)} />
              </div>
              <div className="rg-field">
                <label htmlFor="rg-reg-pass">密码(至少 6 位)</label>
                <input id="rg-reg-pass" type="password" autoComplete="new-password" value={regPassword} onChange={(e) => setRegPassword(e.target.value)} />
              </div>
              <div className="rg-field">
                <label htmlFor="rg-role">身份</label>
                <select id="rg-role" value={role} onChange={(e) => setRole(e.target.value)}>
                  <option value="student">学生</option>
                  <option value="teacher">教师(需邀请码)</option>
                </select>
              </div>
              {role === "teacher" && (
                <div className="rg-field">
                  <label htmlFor="rg-invite">教师邀请码</label>
                  <input id="rg-invite" type="password" placeholder="学校发放的邀请码" value={invite} onChange={(e) => setInvite(e.target.value)} />
                </div>
              )}
              <button type="submit" className="rg-power" disabled={busy}>
                {busy ? "登记中…" : "登记新呼号"}
              </button>
            </form>
          )}
          {error ? <p className="rg-fail" role="alert">{error}</p> : null}
          <div className="rg-boot-foot">
            <span>{tab === "login" ? "演示呼号 student / student123!" : "值班 admin / admin123!"}</span>
            {tab === "login" ? (
              <button type="button" onClick={() => { setTab("register"); setError(""); }}>没有呼号?登记一个</button>
            ) : (
              <button type="button" onClick={() => { setTab("login"); setError(""); }}>已有呼号?返回接通</button>
            )}
          </div>
        </div>
      ) : (
        <p className="lgh-alt">
          已有呼号?<button type="button" onClick={() => { setShowAuth(true); setTab("login"); }}>直接接通</button>
          {" · "}没有呼号?<button type="button" onClick={() => { setShowAuth(true); setTab("register"); }}>登记一个</button>
        </p>
      )}

      <p className="lgh-foot">
        心屿用于支持与陪伴,不提供医学诊断,不能替代专业心理咨询或危机干预。
        <br />需要立即帮助?热线 <b>12356</b> · 紧急 <b>120</b>
      </p>
    </div>
  );
}
