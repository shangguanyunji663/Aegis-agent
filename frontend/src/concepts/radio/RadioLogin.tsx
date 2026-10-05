/* 夜航电台 · 登录页:输入框即入口 → 渐进披露开机面板。 */

import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useAuth } from "../../lib/auth";
import { useSystemStatus } from "../../hooks/useSystemStatus";
import { LoginHero } from "../../shared/LoginHero";
import { createSceneSampler } from "../../lib/scene";
import "./radio.css";

const CHIPS = [
  { label: "压力失眠", text: "我最近考试压力很大,晚上总是睡不着。" },
  { label: "焦虑不安", text: "我感觉很焦虑,考试前完全静不下来。" },
  { label: "情绪低落", text: "我最近情绪很低落,不太想和别人说话。" },
  { label: "关系困扰", text: "我想聊聊最近和家人的矛盾。" },
  { label: "随便聊聊", text: "随便聊聊吧,我今天有点烦。" },
];

/* 交叉淡化时长。量测:循环点末帧 rgb(38,35,39) → 首帧 rgb(19,46,74),
   RGB 距离 41(0–255),而片内相邻采样点正常变化只有 0–5 —— 硬切非常显眼。
   2s 线性溶解实测每 0.4s 仍有 10–15 的色阶变化,是常态中位数的 5 倍。
   改成 2.6s + smoothstep 曲线:两端多停在"接近单画面"的状态,
   50% 重影区间被快速掠过,观感更干净。 */
const FADE_SECONDS = 2.6;

/* smoothstep:两端速度趋 0、中段最快,让"双影最重"的 50% 只停留很短一瞬 */
const easeFade = (t: number) => t * t * (3 - 2 * t);

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
  const videoARef = useRef<HTMLVideoElement>(null);
  const videoBRef = useRef<HTMLVideoElement>(null);

  /* 无缝循环 + 场景联动。
     1) 循环:单个 video 直接 loop 会在末帧(暖灰夜色)硬切回首帧(冷蓝黄昏),
        实测 RGB 距离 41。这里用两个同源 video 交叉淡化 —— A 快播完时
        把 B 从 0 起播,A/B 不透明度线性互换,硬切就变成了溶解。
        B 起播失败(自动播放策略/解码问题)时自动退回 A.loop,不会黑屏。
     2) 联动:scene.ts 对"当前前景"取色,换前景时传 reset=false 保留滑动窗口,
        否则每 14 秒就要重新攒满一整轮,期间归一化会失真。 */
  useEffect(() => {
    const a = videoARef.current;
    const b = videoBRef.current;
    if (!a || !b) return;

    /* 降级动效偏好下视频本来就被 CSS 隐藏,没必要再跑调度器 */
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      a.loop = true;
      return;
    }

    const sampler = createSceneSampler();
    sampler.setSource(a);
    let front: HTMLVideoElement = a;
    let fading = false;
    let raf = 0;

    const other = () => (front === a ? b : a);

    /* 兜底:第二个视频不可用时退回原生 loop */
    const fallbackToLoop = () => {
      fading = false;
      front.loop = true;
      other().loop = true;
      other().pause();
      other().style.opacity = "0";
      front.style.opacity = "1";
    };

    const tick = () => {
      const dur = Number.isFinite(front.duration) ? front.duration : 0;
      if (dur > FADE_SECONDS) {
        const back = other();
        if (!fading && front.currentTime >= dur - FADE_SECONDS) {
          if (back.readyState >= 2) {
            fading = true;
            back.currentTime = 0;
            back.style.opacity = "0";
            const p = back.play();
            if (p && typeof p.catch === "function") p.catch(fallbackToLoop);
          } else {
            fallbackToLoop();
          }
        }
        if (fading) {
          const raw = Math.min(1, Math.max(0, (front.currentTime - (dur - FADE_SECONDS)) / FADE_SECONDS));
          const t = easeFade(raw);
          front.style.opacity = String(1 - t);
          back.style.opacity = String(t);
        }
      }
      raf = requestAnimationFrame(tick);
    };

    const onEnded = (event: Event) => {
      const ended = event.currentTarget as HTMLVideoElement;
      const next = other();
      ended.style.opacity = "0";
      ended.pause();
      next.style.opacity = "1";
      front = next;
      sampler.setSource(next, false);
      fading = false;
    };

    a.addEventListener("ended", onEnded);
    b.addEventListener("ended", onEnded);
    b.style.opacity = "0";
    raf = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(raf);
      a.removeEventListener("ended", onEnded);
      b.removeEventListener("ended", onEnded);
      sampler.stop();
    };
  }, []);

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
    <div className={`lgh-portal${showAuth ? " is-auth" : ""}`}>
      <div className="lgh-photo" aria-hidden="true" />
      {/* 两份同源视频交叉淡化:末帧硬切回首帧会被"溶解"掉。
          B 默认不自动播放、初始全透明,由上面的调度器在 A 播完前 2s 拉起来。 */}
      <video
        ref={videoARef}
        className="lgh-video lgh-video--a"
        autoPlay
        muted
        playsInline
        preload="auto"
        src="/media/night-lake.mp4"
        aria-hidden="true"
      />
      <video
        ref={videoBRef}
        className="lgh-video lgh-video--b"
        muted
        playsInline
        preload="auto"
        src="/media/night-lake.mp4"
        aria-hidden="true"
      />
      <div className="lgh-wash" aria-hidden="true" />
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
