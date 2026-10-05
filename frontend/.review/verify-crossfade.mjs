/* 验证交叉淡化:跨越循环点连续采样合成后的实际画面,
   输出每 0.4s 一帧的均值与相邻差,用来定位是否存在突变尖峰。 */
import { writeFileSync, mkdirSync } from "node:fs";

const PW = "file:///C:/Users/17536/.workbuddy/binaries/node/workspace/node_modules/playwright/index.mjs";
const { chromium } = await import(PW);

mkdirSync(".review/loop", { recursive: true });

const browser = await chromium.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  args: ["--autoplay-policy=no-user-gesture-required"],
});
const page = await (await browser.newContext({ viewport: { width: 1000, height: 640 } })).newPage();
await page.addInitScript(() => { try { localStorage.setItem("aegis:concept", "radio"); } catch {} });
await page.goto("http://127.0.0.1:8000/", { waitUntil: "networkidle" });
await page.waitForTimeout(1500);

/* 只在背景区采样(避开卡片与文字),左上角一块干净的天空/山影 */
const clip = { x: 30, y: 60, width: 150, height: 110 };

const log = [];
const t0 = Date.now();
for (let i = 0; i < 48; i++) {
  const st = await page.evaluate(() => {
    const a = document.querySelector(".lgh-video--a");
    const b = document.querySelector(".lgh-video--b");
    const g = (v) => (v ? { t: +v.currentTime.toFixed(2), o: +Number(v.style.opacity || getComputedStyle(v).opacity).toFixed(2), p: v.paused } : null);
    return { a: g(a), b: g(b) };
  });
  const buf = await page.screenshot({ clip });
  writeFileSync(`.review/loop/f${String(i).padStart(2, "0")}.png`, buf);
  log.push({ i, ms: Date.now() - t0, ...st });
  await page.waitForTimeout(400);
}

console.log("采样完成,共", log.length, "帧 → .review/loop/");
console.log("i    A(t/op/paused)          B(t/op/paused)");
for (const r of log) {
  const a = r.a ? `${r.a.t}/${r.a.o}/${r.a.p ? "P" : "▶"}` : "-";
  const b = r.b ? `${r.b.t}/${r.b.o}/${r.b.p ? "P" : "▶"}` : "-";
  console.log(String(r.i).padStart(2), a.padEnd(24), b.padEnd(24));
}
writeFileSync(".review/loop/state.json", JSON.stringify(log, null, 1));
await browser.close();
