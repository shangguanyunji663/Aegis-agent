/* 串行帧率测量:每个主题连续测 2 轮取较优值,避免单次抖动。
   用法: node .review/perf-fps.mjs            —— 全部三个主题
         node .review/perf-fps.mjs letter     —— 单个主题 */
import { chromium } from "file:///C:/Users/17536/.workbuddy/binaries/node/workspace/node_modules/playwright/index.mjs";

const only = process.argv[2];
const concepts = only ? [only] : ["letter", "radio", "atlas"];

const browser = await chromium.launch({
  headless: true,
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  args: ["--autoplay-policy=no-user-gesture-required"],
});
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });

for (const concept of concepts) {
  const runs = [];
  for (let k = 0; k < 2; k++) {
    const page = await ctx.newPage();
    await page.addInitScript((c) => { try { localStorage.setItem("aegis:concept", c); } catch {} }, concept);
    await page.goto("http://127.0.0.1:8000/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1800);
    await page.evaluate(() => document.querySelector(".lgh-inputbar")?.click());
    await page.waitForTimeout(900);
    const fps = await page.evaluate(async () => {
      let n = 0, stop = false;
      const loop = () => { n++; if (!stop) requestAnimationFrame(loop); };
      requestAnimationFrame(loop);
      const t0 = performance.now();
      await new Promise((r) => setTimeout(r, 3500));
      stop = true;
      return +(n / ((performance.now() - t0) / 1000)).toFixed(1);
    });
    runs.push(fps);
    await page.close();
  }
  console.log(`${concept.padEnd(7)} 轮1 ${String(runs[0]).padStart(6)}  轮2 ${String(runs[1]).padStart(6)}   取高 ${Math.max(...runs)}`);
}
await browser.close();
