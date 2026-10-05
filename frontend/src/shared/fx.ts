/* 共享动效桥:body 级事件委托 + 运行时自动标记。
   不侵入各概念 JSX:按已知类名清单打 data-tilt / data-spot /
   data-magnet / data-ripple 标记,DOM 重渲染后由 MutationObserver 补标。
   选定概念删除落选皮肤后,可把标记改为显式 JSX 属性。
   四种反馈:倾斜(tilt)/聚光(spot)/磁吸(magnet)/涟漪(ripple)。
   只写 CSS 变量与 transform,不碰布局;reduced-motion 下整体静默。 */

const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)");

const TILT = [
  "lg-notice", "lg-slip", "ls-sheet", "la-drawer",
  "rg-console", "rg-main", "rd-board",
  "at-chart-wall", "at-logbook-main", "at-tower",
];

const SPOT = [
  "la-card", "rd-item", "at-obs",
  "ls-envelope", "at-isle", "at-bearing", "rg-preset",
  "cell", "rd-meter", "at-gauge",
  "cns-row", "cns-stat", "cns-tool", "cns-tile",
];

const MAGNET = ["lg-wax", "rg-power", "rg-send", "at-sail", "at-log-btn", "lgh-chip"];

const RIPPLE = [
  "lg-wax", "rg-send", "at-log-btn",
  "la-stamp-btn", "rd-key", "at-beacon",
  "lz-link", "rg-ghost", "at-link", "ls-new", "at-set-sail",
  "cns-btn", "cns-mini", "cns-tab", "cns-stat", "lgh-inputbar", "lgh-chip",
];

const FADE_CONTAINERS = [
  "lg-desk", "ls-letters", "ls-notes", "la-ledger", "la-cards",
  "rg-presets", "rg-logs", "rd-meters", "rd-list",
  "at-isles", "at-compass-col", "at-watch-metrics", "at-observations",
];

function ensureDecor() {
  // 全站环境光斑(所有页面)
  if (!document.querySelector("body > .fx-ambient")) {
    const amb = document.createElement("div");
    amb.className = "fx-ambient";
    amb.setAttribute("aria-hidden", "true");
    amb.append(document.createElement("i"), document.createElement("i"));
    document.body.prepend(amb);
  }
  // 登录页光尘
  document.querySelectorAll(".lgh-portal").forEach((portal) => {
    if (!portal.querySelector(":scope > .lgh-motes")) {
      const motes = document.createElement("div");
      motes.className = "lgh-motes";
      motes.setAttribute("aria-hidden", "true");
      for (let i = 0; i < 9; i++) motes.append(document.createElement("i"));
      portal.append(motes);
    }
  });
}

function mark(root: ParentNode) {
  ensureDecor();
  for (const cls of TILT) {
    root.querySelectorAll(`.${cls}`).forEach((el) => el.setAttribute("data-tilt", "2"));
  }
  for (const cls of SPOT) {
    root.querySelectorAll(`.${cls}`).forEach((el) => el.setAttribute("data-spot", ""));
  }
  for (const cls of MAGNET) {
    root.querySelectorAll(`.${cls}`).forEach((el) => el.setAttribute("data-magnet", ""));
  }
  for (const cls of RIPPLE) {
    root.querySelectorAll(`.${cls}`).forEach((el) => el.setAttribute("data-ripple", ""));
  }
  for (const cls of FADE_CONTAINERS) {
    // 带基础倾角的子项用纯透明度编排(fx-fade),无倾角容器用升入场(fx-stagger)
    const fade = ["ls-letters", "ls-notes", "la-ledger", "la-cards", "rg-logs", "rd-meters", "rd-list", "at-isles", "at-compass-col", "at-watch-metrics", "at-observations"];
    root.querySelectorAll(`.${cls}`).forEach((el) =>
      el.classList.add(fade.includes(cls) ? "fx-fade" : "fx-stagger"),
    );
  }
  root.querySelectorAll(".cns-list,.cns-tools,.lgh-chips").forEach((el) =>
    el.classList.add("fx-stagger"),
  );
}

/* 临界阻尼跟随(Unity SmoothDamp 的解法)。
   velocity 走引用传入/传出 —— 每帧从上一次的速度继续积分,
   所以指针快速反向时不会出现 CSS transition 那种"重新起算缓动"的折返抖动。 */
function smoothDamp(
  current: number,
  target: number,
  vel: { v: number },
  smoothTime: number,
  dt: number,
): number {
  const st = Math.max(0.0001, smoothTime);
  const omega = 2 / st;
  const x = omega * dt;
  const exp = 1 / (1 + x + 0.48 * x * x + 0.235 * x * x * x);
  const change = current - target;
  const goal = current - change;
  const temp = (vel.v + omega * change) * dt;
  vel.v = (vel.v - omega * temp) * exp;
  let out = goal + (change + temp) * exp;
  // 理论上临界阻尼不过冲,浮点与大步长下仍可能越一点,夹回去
  if (target - current > 0 === out > target) {
    out = target;
    vel.v = 0;
  }
  return out;
}

/* 跟随手感。
   原设 0.12s —— 在核显 42.5ms/帧的条件下等于 3 帧滞后,看起来是"跟不上"
   而不是"有黏性"。用户明确反馈"光圈不跟鼠标",故收紧到 0.055s:
   核显下每帧仍能吃掉 78% 的差距(视觉上是干脆地贴上去),
   独显 6.1ms/帧下每帧吃 20%,164 帧/秒的平滑度足以掩盖台阶。 */
const FOLLOW_SMOOTH = 0.055;

export function initFx(): () => void {
  if (REDUCED.matches) return () => {};

  mark(document.body);
  let markTimer = 0;
  const observer = new MutationObserver(() => {
    if (markTimer) return;
    markTimer = window.setTimeout(() => {
      markTimer = 0;
      mark(document.body);
    }, 240);
  });
  observer.observe(document.body, { childList: true, subtree: true });

  let raf = 0;
  let lastEvent: PointerEvent | null = null;
  let lastPt = { x: 0, y: 0 };
  let waveBoost = 0;
  let portalRect: DOMRect | null = null;
  let portalRectFor: HTMLElement | null = null;

  /* 光标跟随器:只在指针移动时启动,收敛后自动停,不留常驻 rAF。 */
  const follow = {
    el: null as HTMLElement | null,
    x: 0, y: 0, tx: 0, ty: 0,
    vx: { v: 0 }, vy: { v: 0 },
    nx: 0, ny: 0,
    raf: 0, last: 0, primed: false,
  };

  const stepFollow = () => {
    const el = follow.el;
    if (!el) { follow.raf = 0; return; }
    const now = performance.now();
    /* 上限 50ms:切走标签页再回来时 dt 会很大,不夹会瞬移 */
    const dt = Math.min(0.05, Math.max(0.001, (now - follow.last) / 1000));
    follow.last = now;

    /* 显式积分的稳定条件约 omega*dt < 1,即 smoothTime > 2*dt。
       帧率掉到 23fps(dt≈42ms)时,0.055s 会越过稳定边界 —— 光圈在目标附近来回抖,
       速度阈值永远不满足,跟随循环还会停不下来(实测静止 1s 仍有 38 次写入)。
       这里按实测 dt 动态兜底:机器快时保持紧(0.055s),机器慢时自动放宽到稳定值。 */
    const st = Math.max(FOLLOW_SMOOTH, dt * 2.2);

    follow.x = smoothDamp(follow.x, follow.tx, follow.vx, st, dt);
    follow.y = smoothDamp(follow.y, follow.ty, follow.vy, st, dt);

    /* 收敛判定:位置与速度都足够小就停,不留空转 */
    const done =
      Math.abs(follow.tx - follow.x) < 0.15 && Math.abs(follow.ty - follow.y) < 0.15 &&
      Math.abs(follow.vx.v) < 0.6 && Math.abs(follow.vy.v) < 0.6;
    if (done) {
      follow.x = follow.tx; follow.y = follow.ty;
      follow.vx.v = 0; follow.vy.v = 0;
    }

    el.style.setProperty("--cx", `${follow.x.toFixed(1)}px`);
    el.style.setProperty("--cy", `${follow.y.toFixed(1)}px`);
    /* 热层专用的归一化视差:与遮罩同源,内容与遮罩完全同步,不会互相滑开 */
    el.style.setProperty("--hx-n", follow.nx.toFixed(3));
    el.style.setProperty("--hy-n", follow.ny.toFixed(3));

    if (done) { follow.raf = 0; return; }
    follow.raf = requestAnimationFrame(stepFollow);
  };
  const invalidatePortalRect = () => { portalRect = null; };
  window.addEventListener("scroll", invalidatePortalRect, { passive: true, capture: true });
  window.addEventListener("resize", invalidatePortalRect, { passive: true });

  /* B:缓存滤镜元素。原先每帧 document.querySelector 查两遍,现在只在元素被
     React 重新挂载(isConnected 变 false)时才重查 —— 切主题会换掉这个节点。 */
  let waterDisp: Element | null = null;
  let lastWaterScale = -1;

  const getWaterDisp = (): Element | null => {
    if (waterDisp && waterDisp.isConnected) return waterDisp;
    waterDisp = document.querySelector("#atlas-water feDisplacementMap");
    if (!waterDisp) lastWaterScale = -1;
    return waterDisp;
  };

  const applyWaveBoost = () => {
    const disp = getWaterDisp();
    if (!disp) return;
    const s = 20 + Math.round(waveBoost);
    /* 写 SVG 滤镜参数会让全屏 filter: url(#atlas-water) 作废重算,
       所以整数值没变化时绝不写 —— 鼠标慢速移动时能省掉绝大多数重算。 */
    if (s === lastWaterScale) return;
    lastWaterScale = s;
    disp.setAttribute("scale", String(s));
  };

  // 指针静止时浪高缓缓回落到基准
  setInterval(() => {
    if (waveBoost > 0.4) {
      waveBoost *= 0.86;
      applyWaveBoost();
    }
  }, 240);

  const apply = () => {
    raf = 0;
    const e = lastEvent;
    if (!e) return;
    const target = e.target instanceof Element ? e.target : null;

    // 倾斜:光标在面板上的相对位置 → rotateX/rotateY
    const tilt = target?.closest("[data-tilt]") as HTMLElement | null;
    if (tilt) {
      const r = tilt.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width - 0.5;
      const py = (e.clientY - r.top) / r.height - 0.5;
      const max = Number(tilt.dataset.tilt) || 2;
      tilt.style.setProperty("--ry", `${(px * max * 2).toFixed(2)}deg`);
      tilt.style.setProperty("--rx", `${(-py * max * 2).toFixed(2)}deg`);
    }

    // 聚光:光标位置画进 ::after 径向渐变
    const spot = target?.closest("[data-spot]") as HTMLElement | null;
    if (spot) {
      const r = spot.getBoundingClientRect();
      spot.style.setProperty("--mx", `${e.clientX - r.left}px`);
      spot.style.setProperty("--my", `${e.clientY - r.top}px`);
    }

    applyWaveBoost();

    // 登录页视差:照片反向漂移,水印字正向漂移(景深)
    const portal = target?.closest(".lgh-portal") as HTMLElement | null;
    if (portal) {
      /* D:getBoundingClientRect 会强制 layout,指针每帧调一次没有必要。
         portal 自身尺寸在一次会话里是稳的,只在滚动/缩放时失效缓存。 */
      if (!portalRect || portalRectFor !== portal) {
        portalRect = portal.getBoundingClientRect();
        portalRectFor = portal;
      }
      const r = portalRect;
      const nx = ((e.clientX - r.left) / r.width - 0.5) * 2;
      const ny = ((e.clientY - r.top) / r.height - 0.5) * 2;
      /* 视差仍然直写:它由 .lgh-photo 的 0.9s CSS transition 负责缓动,
         再叠一层弹簧会变成双重延迟。 */
      portal.style.setProperty("--mx-n", nx.toFixed(3));
      portal.style.setProperty("--my-n", ny.toFixed(3));

      /* 遮罩位置改走弹簧跟随:光标位置不再是"啪"地跳过去。
         只有群岛的光标扰动层消费 --cx/--cy/--hx-n/--hy-n(遮罩位置 + 同步视差),
         信笺与电台没有这个图层 —— 白跑 4 次 style 写入/帧纯属浪费,实测让信笺
         p50 从 12.2ms 涨到 18.1ms。所以按概念门控。 */
      if (document.documentElement.dataset.concept !== "atlas") {
        follow.el = null;
      } else {
      if (follow.el !== portal) { follow.el = portal; follow.primed = false; }
      if (!follow.primed) {
        /* 第一次直接落位,不要从 0 飞过来 */
        follow.x = e.clientX - r.left; follow.y = e.clientY - r.top;
        follow.vx.v = 0; follow.vy.v = 0;
        follow.primed = true;
      }
      follow.tx = e.clientX - r.left;
      follow.ty = e.clientY - r.top;
      follow.nx = nx; follow.ny = ny;
      if (!follow.raf) {
        follow.last = performance.now();
        follow.raf = requestAnimationFrame(stepFollow);
      }
      }

      // 群岛浪高联动:指针速度越快,液态位移越强;停下后缓慢回落
      if (getWaterDisp()) {
        const speed = Math.hypot(e.clientX - lastPt.x, e.clientY - lastPt.y);
        waveBoost = Math.min(30, waveBoost + speed * 0.22);
        lastPt = { x: e.clientX, y: e.clientY };
      }
    }

    // 磁吸:按钮向光标轻移
    const magnet = target?.closest("[data-magnet]") as HTMLElement | null;
    if (magnet) {
      const r = magnet.getBoundingClientRect();
      const dx = e.clientX - (r.left + r.width / 2);
      const dy = e.clientY - (r.top + r.height / 2);
      magnet.style.setProperty("--tx", `${(dx * 0.16).toFixed(1)}px`);
      magnet.style.setProperty("--ty", `${(dy * 0.22).toFixed(1)}px`);
    }
  };

  const onMove = (e: PointerEvent) => {
    lastEvent = e;
    if (!raf) raf = requestAnimationFrame(apply);
  };

  const onClick = (e: MouseEvent) => {
    const el = e.target instanceof Element ? (e.target.closest("[data-ripple]") as HTMLElement | null) : null;
    if (!el) return;
    const r = el.getBoundingClientRect();
    el.style.setProperty("--px", `${e.clientX - r.left}px`);
    el.style.setProperty("--py", `${e.clientY - r.top}px`);
    el.classList.remove("fx-rippling");
    void el.offsetWidth;
    el.classList.add("fx-rippling");
    window.setTimeout(() => el.classList.remove("fx-rippling"), 650);
  };

  document.body.addEventListener("pointermove", onMove, { passive: true });
  document.body.addEventListener("click", onClick);
  return () => {
    observer.disconnect();
    document.body.removeEventListener("pointermove", onMove);
    document.body.removeEventListener("click", onClick);
    window.removeEventListener("scroll", invalidatePortalRect, { capture: true });
    window.removeEventListener("resize", invalidatePortalRect);
    if (raf) cancelAnimationFrame(raf);
    if (follow.raf) cancelAnimationFrame(follow.raf);
    if (markTimer) window.clearTimeout(markTimer);
  };
}
