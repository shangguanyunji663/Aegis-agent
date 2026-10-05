/* 帧时间分布:卡顿的体感来自长帧,不是平均帧率。
   记录 rAF 时间戳,输出 p50/p90/p99 与超过 32ms(掉帧阈值)的帧占比。 */
import { chromium } from "file:///C:/Users/17536/.workbuddy/binaries/node/workspace/node_modules/playwright/index.mjs";

const only = process.argv[2];
const concepts = only ? [only] : ["letter", "radio", "atlas"];

const browser = await chromium.launch({
  headless: true,
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  args: ["--autoplay-policy=no-user-gesture-required"],
});
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });

console.log("帧时间分布(ms)  —— 长帧才是卡顿的来源\n");
for (const concept of concepts) {
  const page = await ctx.newPage();
  await page.addInitScript((c) => { try { localStorage.setItem("aegis:concept", c); } catch {} }, concept);
  await page.goto("http://127.0.0.1:8000/", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1800);
  await page.evaluate(() => document.querySelector(".lgh-inputbar")?.click());
  await page.waitForTimeout(900);

  const r = await page.evaluate(async () => {
    const ts = [];
    let stop = false;
    const loop = (t) => { ts.push(t); if (!stop) requestAnimationFrame(loop); };
    requestAnimationFrame(loop);
    await new Promise((r) => setTimeout(r, 8000));
    stop = true;
    const d = [];
    for (let i = 1; i < ts.length; i++) d.push(ts[i] - ts[i - 1]);
    d.sort((a, b) => a - b);
    const q = (p) => d[Math.min(d.length - 1, Math.floor(d.length * p))];
    return {
      n: d.length,
      p50: +q(0.5).toFixed(1),
      p90: +q(0.9).toFixed(1),
      p99: +q(0.99).toFixed(1),
      max: +d[d.length - 1].toFixed(1),
      over32: +(100 * d.filter((x) => x > 32).length / d.length).toFixed(1),
      over50: +(100 * d.filter((x) => x > 50).length / d.length).toFixed(1),
    };
  });
  console.log(`${concept.padEnd(7)} 帧数 ${String(r.n).padStart(4)}  p50 ${String(r.p50).padStart(5)}  p90 ${String(r.p90).padStart(6)}  p99 ${String(r.p99).padStart(7)}  max ${String(r.max).padStart(7)}   >32ms ${String(r.over32).padStart(5)}%  >50ms ${String(r.over50).padStart(5)}%`);
  await page.close();
}
await browser.close();
