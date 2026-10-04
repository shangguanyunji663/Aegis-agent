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

    // 登录页视差:照片反向漂移,水印字正向漂移(景深)
    const portal = target?.closest(".lgh-portal") as HTMLElement | null;
    if (portal) {
      const r = portal.getBoundingClientRect();
      const nx = ((e.clientX - r.left) / r.width - 0.5) * 2;
      const ny = ((e.clientY - r.top) / r.height - 0.5) * 2;
      portal.style.setProperty("--mx-n", nx.toFixed(3));
      portal.style.setProperty("--my-n", ny.toFixed(3));
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
    if (raf) cancelAnimationFrame(raf);
    if (markTimer) window.clearTimeout(markTimer);
  };
}
