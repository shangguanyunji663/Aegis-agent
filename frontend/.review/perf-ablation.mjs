/* 卡顿归因(精简版):逐项关闭可疑重负载,测对帧率的贡献。
   用法: node .review/perf-ablation.mjs letter [--headed] */
import { chromium } from "file:///C:/Users/17536/.workbuddy/binaries/node/workspace/node_modules/playwright/index.mjs";

const concept = process.argv[2] || "letter";
const HEADED = process.argv.includes("--headed");

const ABLATIONS = [
  ["基线(什么都不关)", ""],
  ["全部 backdrop-filter", "*{backdrop-filter:none!important;-webkit-backdrop-filter:none!important}"],
  ["SVG 滤镜(mist/water/hot/textwave)", ".lgh-mist,.lgh-photo,.lgh-photo--hot,.lgh-chips,.lgh-inputbar{filter:none!important}"],
  ["Ken Burns 照片慢推", ".lgh-portal>.lgh-photo::before{animation:none!important}"],
  [".fx-ambient(blur 72px)", ".fx-ambient{display:none!important}"],
  [".lgh-portal::after(blur 58px)", ".lgh-portal::after{display:none!important}"],
  ["雾层 .lgh-mist", ".lgh-mist{display:none!important}"],
  ["视频层", ".lgh-video{display:none!important}"],
];

const browser = await chromium.launch({
  headless: !HEADED,
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  args: ["--autoplay-policy=no-user-gesture-required"],
});
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });

const rows = [];
for (const [name, css] of ABLATIONS) {
  const page = await ctx.newPage();
  await page.addInitScript((c) => { try { localStorage.setItem("aegis:concept", c); } catch {} }, concept);
  if (css) {
    await page.addInitScript((t) => {
      document.addEventListener("DOMContentLoaded", () => {
        const s = document.createElement("style");
        s.textContent = t;
        document.head.appendChild(s);
      });
    }, css);
  }
  await page.goto("http://127.0.0.1:8000/", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1800);
  await page.evaluate(() => document.querySelector(".lgh-inputbar")?.click());
  await page.waitForTimeout(900);

  const fps = await page.evaluate(async () => {
    let n = 0, stop = false;
    const loop = () => { n++; if (!stop) requestAnimationFrame(loop); };
    requestAnimationFrame(loop);
    const t0 = performance.now();
    await new Promise((r) => setTimeout(r, 3000));
    stop = true;
    return +(n / ((performance.now() - t0) / 1000)).toFixed(1);
  });
  rows.push([name, fps]);
  await page.close();
}

const base = rows[0][1];
console.log(`\n=== ${concept} ===  模式:${HEADED ? "headed 真实 GPU" : "headless(可能软件渲染)"}  基线 ${base} FPS`);
for (const [name, fps] of rows.slice(1)) {
  const gain = fps - base;
  const pct = ((fps / base - 1) * 100).toFixed(0);
  console.log(`  ${gain >= 0 ? "+" : ""}${gain.toFixed(1).padStart(5)} FPS (${pct.padStart(4)}%)  -> ${fps.toFixed(1).padStart(5)}  ${name}`);
}
await browser.close();
