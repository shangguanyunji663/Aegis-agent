/* 场景联动实测:同一页面把视频拖到"深夜"与"黎明"两个时刻,
   对比卡片描边 / 文字 / 按钮是否随背景改变。
   附加:截两帧,直接看"卡片颜色随背景走"是否成立。 */
const PW = "file:///C:/Users/17536/.workbuddy/binaries/node/workspace/node_modules/playwright/index.mjs";
const { chromium } = await import(PW);

const browser = await chromium.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  args: ["--autoplay-policy=no-user-gesture-required"],
});
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
await page.addInitScript(() => { try { localStorage.setItem("aegis:concept", "radio"); } catch {} });
await page.goto("http://127.0.0.1:8000/", { waitUntil: "networkidle" });
await page.evaluate(() => document.querySelector(".lgh-inputbar")?.click());
await page.waitForTimeout(1500);
/* 先让视频自然播满一轮(13.88s)+ 余量,滑动窗口填满后归一化才有意义 */
console.log("等待滑动窗口填满(约 17s)…");
await page.waitForTimeout(17000);

const probe = () => page.evaluate(() => {
  const g = (sel, prop) => {
    const el = document.querySelector(sel);
    return el ? getComputedStyle(el)[prop] : null;
  };
  const cs = getComputedStyle(document.documentElement);
  return {
    scene: ["--scene-r", "--scene-g", "--scene-b"].map((k) => cs.getPropertyValue(k).trim()).join(","),
    cardScene: ["--scene-card-r", "--scene-card-g", "--scene-card-b"].map((k) => cs.getPropertyValue(k).trim()).join(","),
    lum: cs.getPropertyValue("--scene-lum").trim(),
    warm: cs.getPropertyValue("--vid-warm").trim(),
    cardTopEdge: g(".rg-console", "borderTopColor"),
    cardShadow: (g(".rg-console", "boxShadow") || "").slice(0, 96),
    slogan: g(".lgh-slogan", "color"),
    chip: g(".lgh-chip", "color"),
    brand: g(".rg-brand .callword", "color"),
    foot: g(".lgh-foot", "color"),
    label: g(".rg-console label", "color"),
    inputText: g(".rg-console input", "color"),
    powerBg: (g(".rg-power", "backgroundImage") || "").slice(0, 110),
  };
});

async function seek(frac, name) {
  await page.evaluate((f) => {
    const v = document.querySelector(".lgh-video");
    if (v && Number.isFinite(v.duration)) v.currentTime = v.duration * f;
  }, frac);
  await page.waitForTimeout(1600); // 让 EMA 与滑动窗口跟上
  const out = await probe();
  console.log("\n--- " + name + " (t=" + (frac * 100).toFixed(0) + "% 时长) ---");
  for (const [k, v] of Object.entries(out)) console.log("  " + k.padEnd(12), v);
  await page.screenshot({ path: `.review/scene-radio-${name}.png` });
  return out;
}

const dark = await seek(0.02, "deep-night");
const bright = await seek(0.5, "dawn-yellow");

console.log("\n=== 差异判定 ===");
const num = (c) => {
  const m = /rgba?\(([^)]+)\)/.exec(c || "");
  if (!m) return null;
  return m[1].split(",").slice(0, 3).map((v) => parseFloat(v));
};
for (const key of ["slogan", "chip", "brand", "foot", "label", "inputText"]) {
  const a = num(dark[key]), b = num(bright[key]);
  if (a && b) {
    const d = Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) + Math.abs(a[2] - b[2]);
    console.log(`  ${key.padEnd(11)} 深夜 rgb(${a}) → 黎明 rgb(${b})  Δ=${d}`);
  }
}
console.log("  cardTopEdge 深夜 →", dark.cardTopEdge, " | 黎明 →", bright.cardTopEdge);

await browser.close();
