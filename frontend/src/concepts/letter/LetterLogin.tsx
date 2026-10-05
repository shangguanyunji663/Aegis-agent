/* 信笺概念 · 登录页:输入框即入口(Master 范式) → 渐进披露领取单。 */

import { useEffect, useState } from "react";
import type { CSSProperties, FormEvent } from "react";
import { useAuth } from "../../lib/auth";
import { useSystemStatus } from "../../hooks/useSystemStatus";
import { LoginHero } from "../../shared/LoginHero";
import { createSceneSampler } from "../../lib/scene";
import heroLetter from "../../assets/hero-letter.jpg";
import "./letter.css";

const CHIPS = [
  { label: "压力失眠", text: "我最近考试压力很大,晚上总是睡不着。" },
  { label: "焦虑不安", text: "我感觉很焦虑,考试前完全静不下来。" },
  { label: "情绪低落", text: "我最近情绪很低落,不太想和别人说话。" },
  { label: "关系困扰", text: "我想聊聊最近和家人的矛盾。" },
  { label: "随便聊聊", text: "随便聊聊吧,我今天有点烦。" },
];

/* 口号逐字拆分:雾带扫过时逐字"浸雾"形变(15s,与雾带同周期) */
function dipChars(text: string, em: boolean, start: number) {
  return [...text].map((ch, i) => (
    <span
      key={`${start}-${i}`}
      className={`at-ch${em ? " at-ch-em" : ""}`}
      style={{ "--d": `${(start + i) * 110}ms` } as CSSProperties}
    >
      {ch}
    </span>
  ));
}

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
  const waterOk = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* 场景联动:信笺底图是静态照片,取一次色即可 ——
     卡片描边与内高光因此由这张"日出云海"本身决定,而不是写死一个暖白色。 */
  useEffect(() => {
    const img = new Image();
    img.src = heroLetter;
    const sampler = createSceneSampler();
    const onLoad = () => sampler.setSource(img);
    if (img.complete && img.naturalWidth) onLoad();
    else img.addEventListener("load", onLoad, { once: true });
    return () => sampler.stop();
  }, []);

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
    <div className={`lgh-portal${showAuth ? " is-auth" : ""}`}>
      <div className="lgh-photo" aria-hidden="true" />
      <div className="lgh-wash" aria-hidden="true" />
      <div className="lgh-mist" aria-hidden="true"><i /><i /><i /></div>
      {waterOk && (
        <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true" focusable="false">
          {/* 流动雾滤镜:粗尺度造云团轮廓,细尺度加丝缕纹理。
              两级 feDisplacementMap 串联,只靠单层低频湍流位移肉眼看不出"在动"。
              color-interpolation-filters=sRGB 避免线性光空间把亮度压平。
              (两段 feTurbulence 内的 <animate> 是有意保留的:它让位移图案缓慢 morphing,
               代价是每帧重算分形噪声 —— 用户选择观感优先。) */}
          <filter id="letter-mist-flow" x="-25%" y="-25%" width="150%" height="150%" color-interpolation-filters="sRGB">
            <feTurbulence type="fractalNoise" baseFrequency="0.0055 0.013" numOctaves="3" seed="5" result="coarse">
              <animate attributeName="baseFrequency" dur="19s"
                values="0.0055 0.013;0.0085 0.019;0.0042 0.010;0.0055 0.013" repeatCount="indefinite" />
            </feTurbulence>
            <feTurbulence type="turbulence" baseFrequency="0.021 0.048" numOctaves="2" seed="17" result="fine">
              <animate attributeName="baseFrequency" dur="7.5s"
                values="0.021 0.048;0.030 0.062;0.017 0.040;0.021 0.048" repeatCount="indefinite" />
            </feTurbulence>
            <feDisplacementMap in="SourceGraphic" in2="coarse" scale="120"
              xChannelSelector="R" yChannelSelector="G" result="warped" />
            <feDisplacementMap in="warped" in2="fine" scale="34"
              xChannelSelector="R" yChannelSelector="G" />
          </filter>
        </svg>
      )}
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
        slogan={<>{dipChars("每一句倾诉,都有人", false, 0)}{dipChars("认真对待", true, 9)}{dipChars("。", false, 13)}</>}
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
