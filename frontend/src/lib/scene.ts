/* 场景取色:让界面颜色真正"由背景决定",而不是各主题写死一套色。
 *
 * 做法:把背景(电台的视频 / 信笺与群岛的照片)画进一块 48×27 的离屏 canvas,
 * 每 90ms 取一次像素,分两个区域统计平均色:
 *   · 全画面  → 页面情绪(品牌、页脚、洗色层)
 *   · 下中部  → 认证卡所在位置,卡片颜色直接跟这里走
 * 结果写进 :root 的 CSS 变量,供 premium.css 的玻璃层与排版层消费。
 *
 * ⚠️ 驱动信号是【色温】而不是亮度 —— 这是量过之后才定下来的。
 * 实测本片 13.88s 循环内:
 *   平均亮度 0.1405 → 0.1645,跨度只有 0.024(几乎不变);
 *   而 r−b(冷暖) −0.216 → +0.034,跨度 0.250,是亮度的十倍。
 * 也就是说用户看到的"一开始偏黑、后来转黄"是色相变化,不是明暗变化。
 * 用亮度驱动文字反色会得到几乎为零的联动幅度,所以这里以 r−b 为主信号。
 *
 * 归一化用覆盖整段循环的滑动窗口(160 帧 ≈ 14.5s > 13.88s):
 * 循环播放时首尾取值一致,不会在循环点跳变,同时也自动适配任何素材。
 */

const W = 48;
const H = 27;
/* 认证卡所在区域(视口比例):x 28%–72%,y 44%–86% */
const CARD = { x0: 0.28, x1: 0.72, y0: 0.44, y1: 0.86 };
/* 窗口略长于视频循环,保证一轮之内 min/max 稳定 */
const WINDOW = 160;
/* 静态图(信笺/群岛)采样 16 帧后冻结区间,不必等满一整轮 */
const FREEZE_AFTER = 16;
const TICK_MS = 90;

export type SceneSource = HTMLVideoElement | HTMLImageElement | null;

export interface SceneHandle {
  /** reset=false 时保留已有滑动窗口统计 —— 同一素材换播放实例(交叉淡化)时用,
   *  否则每 14 秒就要重新攒满一整轮,期间归一化会失真。 */
  setSource: (el: SceneSource, reset?: boolean) => void;
  stop: () => void;
}

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);

export function createSceneSampler(): SceneHandle {
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  const style = document.documentElement.style;

  let source: SceneSource = null;
  let timer = 0;
  let tainted = false;

  /* 平滑态:全画面色 / 卡片区色 / 色温 */
  const sm = { fr: 24, fg: 22, fb: 20, cr: 24, cg: 22, cb: 20, warm: 0 };
  /* 滑动窗口:对色温做 min/max 归一化 */
  const hist = new Float32Array(WINDOW);
  let head = 0;
  let filled = 0;
  let frozen = { lo: 0, hi: 1, done: false };
  let primed = false;

  function resetStats() {
    sm.fr = 24; sm.fg = 22; sm.fb = 20;
    sm.cr = 24; sm.cg = 22; sm.cb = 20;
    sm.warm = 0;
    head = 0; filled = 0;
    frozen = { lo: 0, hi: 1, done: false };
    primed = false;
  }

  function intrinsic(s: Exclude<SceneSource, null>) {
    if (s instanceof HTMLVideoElement) return [s.videoWidth, s.videoHeight] as const;
    return [s.naturalWidth, s.naturalHeight] as const;
  }

  function sample() {
    if (!source || !ctx) return;
    const [w, h] = intrinsic(source);
    if (!w || !h) return;
    if (source instanceof HTMLVideoElement && source.readyState < 2) return;

    try {
      ctx.drawImage(source, 0, 0, W, H);
    } catch {
      return; // 视频尚未解出首帧
    }

    let data: Uint8ClampedArray;
    try {
      data = ctx.getImageData(0, 0, W, H).data;
    } catch {
      if (!tainted) {
        tainted = true;
        console.warn("[scene] 画布被跨源污染,场景取色停用(界面回退到主题默认色)");
      }
      return;
    }

    const px0 = Math.floor(W * CARD.x0);
    const px1 = Math.ceil(W * CARD.x1);
    const py0 = Math.floor(H * CARD.y0);
    const py1 = Math.ceil(H * CARD.y1);

    let fr = 0, fg = 0, fb = 0, cr = 0, cg = 0, cb = 0, cn = 0;
    for (let y = 0; y < H; y++) {
      const inY = y >= py0 && y < py1;
      for (let x = 0; x < W; x++) {
        const i = (y * W + x) * 4;
        const r = data[i], g = data[i + 1], b = data[i + 2];
        fr += r; fg += g; fb += b;
        if (inY && x >= px0 && x < px1) { cr += r; cg += g; cb += b; cn++; }
      }
    }

    const n = W * H;
    fr /= n; fg /= n; fb /= n;
    if (cn) { cr /= cn; cg /= cn; cb /= cn; }
    /* 主信号:色温 r−b,归一到 0..1(约 −0.25 … +0.25) */
    const warmRaw = clamp01(((fr - fb) / 255 + 0.25) / 0.5);

    /* 首帧直接落位(否则页面会从灰黑慢慢长出色调),之后按 ~0.65s 时间常数平滑 */
    const a = primed ? 0.14 : 1;
    sm.fr += (fr - sm.fr) * a;
    sm.fg += (fg - sm.fg) * a;
    sm.fb += (fb - sm.fb) * a;
    sm.cr += (cr - sm.cr) * a;
    sm.cg += (cg - sm.cg) * a;
    sm.cb += (cb - sm.cb) * a;
    sm.warm += (warmRaw - sm.warm) * a;
    primed = true;

    /* 滑动窗口归一化 */
    let lo: number, hi: number;
    if (source instanceof HTMLImageElement) {
      if (!frozen.done && filled < FREEZE_AFTER) {
        hist[filled] = sm.warm;
        filled++;
        if (filled >= FREEZE_AFTER) {
          let a0 = Infinity, b0 = -Infinity;
          for (let i = 0; i < filled; i++) { a0 = Math.min(a0, hist[i]); b0 = Math.max(b0, hist[i]); }
          frozen = { lo: a0, hi: b0, done: true };
        }
      }
      lo = frozen.done ? frozen.lo : 0;
      hi = frozen.done ? frozen.hi : 1;
    } else {
      hist[head] = sm.warm;
      head = (head + 1) % WINDOW;
      if (filled < WINDOW) filled++;
      lo = Infinity; hi = -Infinity;
      for (let i = 0; i < filled; i++) {
        if (hist[i] < lo) lo = hist[i];
        if (hist[i] > hi) hi = hist[i];
      }
    }
    const span = Math.max(hi - lo, 0.08);
    const windowed = clamp01((sm.warm - lo) / span);
    /* 窗口没攒满一整轮之前,hi−lo 会被 0.08 的兜底撑开,归一化结果直接顶到 0/1
       —— 表现为页面刚加载时颜色被钉死在某个极端、几秒后突然跳一下。
       这里改用"原始色温信号 → 窗口归一化信号"的平滑过渡:
       原始信号本身已在 ±0.25 区间归一到 0..1,开局即可用,
       随窗口填充进度线性切到归一化信号,没有台阶。 */
    const blend = Math.min(1, filled / WINDOW);
    const signal = clamp01(sm.warm * (1 - blend) + windowed * blend);

    style.setProperty("--scene-r", sm.fr.toFixed(1));
    style.setProperty("--scene-g", sm.fg.toFixed(1));
    style.setProperty("--scene-b", sm.fb.toFixed(1));
    style.setProperty("--scene-card-r", sm.cr.toFixed(1));
    style.setProperty("--scene-card-g", sm.cg.toFixed(1));
    style.setProperty("--scene-card-b", sm.cb.toFixed(1));
    /* 平均亮度:仅用于"背景真的变亮才反色"的安全阀,不做主信号 */
    style.setProperty("--scene-lum", ((0.2126 * sm.fr + 0.7152 * sm.fg + 0.0722 * sm.fb) / 255).toFixed(4));
    /* 0 = 冷(深夜蓝),1 = 暖(黎明黄) */
    style.setProperty("--vid-warm", signal.toFixed(4));
  }

  function start() {
    if (timer) return;
    timer = window.setInterval(sample, TICK_MS);
  }

  return {
    setSource(el, reset = true) {
      source = el;
      if (reset) resetStats();
      if (el) start();
    },
    stop() {
      if (timer) window.clearInterval(timer);
      timer = 0;
      source = null;
    },
  };
}
