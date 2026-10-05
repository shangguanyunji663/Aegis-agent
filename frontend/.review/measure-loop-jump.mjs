/* 精确量测:先暂停视频再 seek,消除"seek 期间继续播放导致跨循环"的采样假象。 */
const PW = "file:///C:/Users/17536/.workbuddy/binaries/node/workspace/node_modules/playwright/index.mjs";
const { chromium } = await import(PW);

const browser = await chromium.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  args: ["--autoplay-policy=no-user-gesture-required"],
});
const page = await (await browser.newContext({ viewport: { width: 1200, height: 750 } })).newPage();
await page.addInitScript(() => { try { localStorage.setItem("aegis:concept", "radio"); } catch {} });
await page.goto("http://127.0.0.1:8000/", { waitUntil: "networkidle" });
await page.waitForTimeout(1500);

const data = await page.evaluate(async () => {
  const v = document.querySelector(".lgh-video");
  v.pause();                       // 关键:暂停后 seek 才是精确的
  await new Promise((r) => setTimeout(r, 120));

  const c = document.createElement("canvas");
  c.width = 64; c.height = 36;
  const ctx = c.getContext("2d", { willReadFrequently: true });

  const grab = async (t) => {
    v.currentTime = t;
    await new Promise((r) => v.addEventListener("seeked", r, { once: true }));
    await new Promise((r) => requestAnimationFrame(r));
    ctx.drawImage(v, 0, 0, 64, 36);
    const d = ctx.getImageData(0, 0, 64, 36).data;
    let r = 0, g = 0, b = 0;
    for (let i = 0; i < d.length; i += 4) { r += d[i]; g += d[i + 1]; b += d[i + 2]; }
    const n = d.length / 4;
    return [r / n, g / n, b / n].map((x) => Math.round(x));
  };

  const dur = v.duration;
  const ts = [0, 0.5, 2, 5, 8, 11, 12, 13, 13.4, 13.6, 13.78, dur - 0.02];
  const out = [];
  for (const t of ts) out.push({ t: +t.toFixed(2), rgb: await grab(t) });
  return { dur, out };
});

const d = (a, b) => Math.round(Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]));
console.log("视频时长:", data.dur, "s   (暂停后精确 seek)\n");
console.log("  t(s)     均值 RGB        相邻 Δ");
for (let i = 0; i < data.out.length; i++) {
  const f = data.out[i];
  const prev = i > 0 ? data.out[i - 1] : null;
  const delta = prev ? d(prev.rgb, f.rgb) : null;
  const isLoop = prev && Math.abs(prev.t - f.t) > 1;
  console.log(`  ${String(f.t).padStart(6)}   rgb(${String(f.rgb).padEnd(11)})  ${delta === null ? "  -" : String(delta).padStart(3)}${isLoop ? "   <<< 跨越循环点" : ""}`);
}
const last = data.out[data.out.length - 1].rgb;
const first = data.out[0].rgb;
console.log("\n循环点:末帧 rgb(" + last + ") → 首帧 rgb(" + first + ")  Δ=" + d(last, first));
await browser.close();
