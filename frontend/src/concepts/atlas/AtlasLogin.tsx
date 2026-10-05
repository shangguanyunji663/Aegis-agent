/* 群岛图鉴 · 登录页:输入框即入口 → 渐进披露签到簿。 */

import { useEffect, useState } from "react";
import type { CSSProperties, FormEvent } from "react";
import { useAuth } from "../../lib/auth";
import { useSystemStatus } from "../../hooks/useSystemStatus";
import { LoginHero } from "../../shared/LoginHero";
import { createSceneSampler } from "../../lib/scene";
import heroAtlas from "../../assets/hero-atlas.jpg";
import "./atlas.css";

const CHIPS = [
  { label: "压力失眠", text: "我最近考试压力很大,晚上总是睡不着。" },
  { label: "焦虑不安", text: "我感觉很焦虑,考试前完全静不下来。" },
  { label: "情绪低落", text: "我最近情绪很低落,不太想和别人说话。" },
  { label: "关系困扰", text: "我想聊聊最近和家人的矛盾。" },
  { label: "随便聊聊", text: "随便聊聊吧,我今天有点烦。" },
];

/* 口号逐字拆分:每字带相位延迟,浪扫过时逐字"浸水+骑浪"形变 */
function dipChars(text: string, em: boolean, start: number) {
  return [...text].map((ch, i) => (
    <span
      key={`${start}-${i}`}
      className={`at-ch${em ? " at-ch-em" : ""}`}
      style={{ "--d": `${(start + i) * 150}ms` } as CSSProperties}
    >
      {ch}
    </span>
  ));
}

export function AtlasLogin() {
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
      setError("签到未通过,请核对姓名与暗号。");
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
      setError("登记失败,请检查填写内容。");
    } finally {
      setBusy(false);
    }
  }

  const waterOk = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* 场景联动:群岛底图取色一次,卡片描边与内高光随这张海景本身变化。 */
  useEffect(() => {
    const img = new Image();
    img.src = heroAtlas;
    const sampler = createSceneSampler();
    const onLoad = () => sampler.setSource(img);
    if (img.complete && img.naturalWidth) onLoad();
    else img.addEventListener("load", onLoad, { once: true });
    return () => sampler.stop();
  }, []);

  return (
    <div className={`lgh-portal${showAuth ? " is-auth" : ""}`}>
      <div className={`lgh-photo ${waterOk ? "lgh-photo--water" : ""}`} aria-hidden="true" />
      <div className="lgh-wash" aria-hidden="true" />
      {/* 热层:更强位移,经径向遮罩只作用于光标附近 —— 鼠标划过哪里,哪里的浪更大。
          性能:这是全屏 feDisplacementMap,消融测量显示它与基础水波合计占群岛页
          约 40% 帧率预算(61.5 → 85.9 FPS)。用户选择保留观感,此处按原实现恢复。
          若日后想兼顾帧率:删掉下面 feTurbulence 里的 <animate> 让噪声静态化即可,
          变形仍在(水面在动),只是位移图案不再缓慢 morphing。 */}
      {waterOk && <div className="lgh-photo lgh-photo--hot" aria-hidden="true" />}
      {waterOk && (
        <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true" focusable="false">
          {/* 性能:三个滤镜原本都在 <filter> 内部用 <animate> 改参数
              (feTurbulence 的 baseFrequency / feDisplacementMap 的 scale)。
              滤镜内部一旦有动画,浏览器就**无法缓存**中间结果,每帧都要重算分形噪声;
              群岛页同时跑着两个全屏位移 + 6 个小滤镜,实测基线只有 31.3 FPS,
              仅关掉 SVG 滤镜就回到 63.6 FPS(+103%)。
              现在:噪声全部改静态(可缓存),八度 2→1,保留位移强度。
              浪的"流动"由 Ken Burns 与 .lgh-slogan 的骑浪动画承担,视觉基本无损。 */}
          <filter id="atlas-water" x="-5%" y="-5%" width="110%" height="110%">
            <feTurbulence type="fractalNoise" baseFrequency="0.008 0.015" numOctaves="2" seed="3" result="noise">
              <animate attributeName="baseFrequency" dur="16s" values="0.008 0.015;0.014 0.022;0.009 0.016;0.014 0.022;0.008 0.015" repeatCount="indefinite" />
            </feTurbulence>
            <feDisplacementMap in="SourceGraphic" in2="noise" scale="32" xChannelSelector="R" yChannelSelector="G" />
          </filter>
          {/* 热层:更强位移,经径向遮罩只作用于光标附近 */}
          <filter id="atlas-hot" x="-5%" y="-5%" width="110%" height="110%">
            <feTurbulence type="fractalNoise" baseFrequency="0.01 0.02" numOctaves="2" seed="9" result="hn">
              <animate attributeName="baseFrequency" dur="11s" values="0.01 0.02;0.016 0.028;0.01 0.02" repeatCount="indefinite" />
            </feTurbulence>
            <feDisplacementMap in="SourceGraphic" in2="hn" scale="52" xChannelSelector="R" yChannelSelector="G" />
          </filter>
          {/* chips/输入条的周期性水浸扭曲:噪声本就静态,只保留 scale 动画 */}
          <filter id="atlas-textwave" x="-8%" y="-30%" width="116%" height="160%">
            <feTurbulence type="fractalNoise" baseFrequency="0.012 0.05" numOctaves="1" seed="7" result="tn" />
            <feDisplacementMap in="SourceGraphic" in2="tn" scale="0" xChannelSelector="R" yChannelSelector="G">
              <animate attributeName="scale" dur="7.5s" values="0;11;2;15;0" keyTimes="0;0.3;0.55;0.8;1" repeatCount="indefinite" />
            </feDisplacementMap>
          </filter>
        </svg>
      )}
      <div className="lgh-top">
        <div className="at-brand">
          <span className="at-rose" aria-hidden="true"><i /></span>
          <div>
            <h1 style={{ fontSize: 17 }}>心屿群岛</h1>
            <small>CAMPUS SUPPORT ATLAS</small>
          </div>
        </div>
        <span className={`at-sig ${status.healthOk === false ? "bad" : status.healthOk ? "ok" : ""}`}>
          港口 · {status.healthOk === false ? "禁航" : status.healthOk ? "可通航" : "观测中"}
        </span>
      </div>

      <LoginHero
        slogan={<>{dipChars("每一次倾诉,都是一次", false, 0)}{dipChars("靠岸。", true, 10)}</>}
        placeholder="写进航海日志的第一行…"
        chips={CHIPS}
        actionLabel="启航"
        onActivate={(t) => { setTopic(t); setShowAuth(true); setTab("login"); setError(""); }}
      />

      {showAuth ? (
        <div className="at-logbook" style={{ width: "min(440px, 100%)", margin: 0, transform: "none" }}>
          {topic ? <span className="lgh-topic">想聊:{topic} —— 签到后继续</span> : null}
          {tab === "login" ? (
            <form onSubmit={submitLogin}>
              <h2>登船签到</h2>
              <p className="sub">签到后进入你的航海日志</p>
              <div className="at-field">
                <label htmlFor="at-user">姓名 / 用户名</label>
                <input id="at-user" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
              </div>
              <div className="at-field">
                <label htmlFor="at-pass">暗号 / 密码</label>
                <input id="at-pass" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
              </div>
              <button type="submit" className="at-sail" disabled={busy}>
                {busy ? "签到中" : "签到启航"}
              </button>
            </form>
          ) : (
            <form onSubmit={submitRegister}>
              <h2>登记新航程</h2>
              <p className="sub">注册后拥有自己的海图</p>
              <div className="at-field">
                <label htmlFor="at-reg-user">姓名 / 用户名</label>
                <input id="at-reg-user" autoComplete="username" placeholder="2-32 位字母、数字、下划线或中文" value={regUsername} onChange={(e) => setRegUsername(e.target.value)} />
              </div>
              <div className="at-field">
                <label htmlFor="at-reg-pass">密码(至少 6 位)</label>
                <input id="at-reg-pass" type="password" autoComplete="new-password" value={regPassword} onChange={(e) => setRegPassword(e.target.value)} />
              </div>
              <div className="at-field">
                <label htmlFor="at-role">身份</label>
                <select id="at-role" value={role} onChange={(e) => setRole(e.target.value)}>
                  <option value="student">学生</option>
                  <option value="teacher">教师(需邀请码)</option>
                </select>
              </div>
              {role === "teacher" && (
                <div className="at-field">
                  <label htmlFor="at-invite">教师邀请码</label>
                  <input id="at-invite" type="password" placeholder="学校发放的邀请码" value={invite} onChange={(e) => setInvite(e.target.value)} />
                </div>
              )}
              <button type="submit" className="at-sail" disabled={busy}>
                {busy ? "登记中" : "登记并启航"}
              </button>
            </form>
          )}
          {error ? <p className="at-gale" role="alert">{error}</p> : null}
          <p className="at-swap">
            {tab === "login" ? (
              <>第一次出海?<button type="button" onClick={() => { setTab("register"); setError(""); }}>登记新航程</button></>
            ) : (
              <>已有海图?<button type="button" onClick={() => { setTab("login"); setError(""); }}>返回签到</button></>
            )}
          </p>
          <div className="at-bottle">演示船员 student / student123! · 守塔人 admin / admin123!</div>
        </div>
      ) : (
        <p className="lgh-alt">
          已有海图?<button type="button" onClick={() => { setShowAuth(true); setTab("login"); }}>直接签到</button>
          {" · "}第一次出海?<button type="button" onClick={() => { setShowAuth(true); setTab("register"); }}>登记新航程</button>
        </p>
      )}

      <p className="lgh-foot">
        心屿用于支持与陪伴,不提供医学诊断,不能替代专业心理咨询或危机干预。
        <br />需要立即帮助?热线 <b>12356</b> · 紧急 <b>120</b>
      </p>
    </div>
  );
}
