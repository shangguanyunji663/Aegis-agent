/* CSS 落地体检:统计解析到的规则数,并核对登录卡/雾层是否命中。
   用法: node .css_probe.mjs [concept]   concept ∈ letter|radio|atlas */
/* ESM 不认 NODE_PATH,直接按真实路径导入托管工作区的 playwright。 */
const PW = "file:///C:/Users/17536/.workbuddy/binaries/node/workspace/node_modules/playwright/index.mjs";
const { chromium } = await import(PW);

const concept = process.argv[2] || "letter";
const BASE = "http://127.0.0.1:8000/";

const browser = await chromium.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  args: ["--autoplay-policy=no-user-gesture-required"],
});
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();

await page.addInitScript((c) => {
  try { localStorage.setItem("aegis:concept", c); } catch {}
}, concept);

const msgs = [];
page.on("console", (m) => { if (m.type() === "error") msgs.push("[console] " + m.text()); });
page.on("pageerror", (e) => msgs.push("[pageerror] " + e.message));

await page.goto(BASE, { waitUntil: "networkidle" });
await page.waitForTimeout(600);

/* 1) 样式表规则统计 + 关键词命中 */
const sheetStats = await page.evaluate(() => {
  const out = [];
  for (const sheet of document.styleSheets) {
    let n = -1, err = null, hits = {};
    const probe = ["lg-slip", "rg-console", "at-logbook", "lgh-mist", "lgh-video", "rg-power", "at-sail"];
    try {
      const rules = sheet.cssRules;
      n = rules.length;
      const walk = (list) => {
        for (const r of list) {
          const sel = r.selectorText || r.conditionText || r.cssText?.slice(0, 60) || "";
          for (const p of probe) if (sel.includes(p)) hits[p] = (hits[p] || 0) + 1;
          if (r.cssRules) walk(r.cssRules);
        }
      };
      walk(rules);
    } catch (e) { err = String(e).slice(0, 120); }
    out.push({ href: (sheet.href || "(inline)").split("/").pop(), n, err, hits });
  }
  return out;
});

/* 2) 展开登录卡 */
const clickTarget = { letter: "开始倾诉", radio: "接通热线", atlas: "启航" }[concept];
await page.evaluate(() => {
  const bar = document.querySelector(".lgh-inputbar");
  if (bar) bar.click();
});
await page.waitForTimeout(900);

/* 3) 关键元素计算样式 */
const style = await page.evaluate((concept) => {
  const pick = {
    letter: ".lg-slip", radio: ".rg-console", atlas: ".at-logbook",
  }[concept];
  const card = document.querySelector(pick);
  const mist = document.querySelector(".lgh-mist i");
  const mistBox = document.querySelector(".lgh-mist");
  const video = document.querySelector(".lgh-video");
  const slogan = document.querySelector(".lgh-slogan");
  const cs = (el) => el ? getComputedStyle(el) : null;
  const c = cs(card);
  return {
    concept,
    cardPresent: !!card,
    card: c ? {
      background: c.backgroundColor,
      backdrop: c.backdropFilter,
      border: c.borderColor,
      shadow: c.boxShadow.slice(0, 90),
      color: c.color,
    } : null,
    mistPresent: !!mist,
    mist: mist ? {
      animationName: cs(mist).animationName,
      animationDuration: cs(mist).animationDuration,
      filter: cs(mist).filter.slice(0, 80),
      transform: cs(mist).transform,
      opacity: cs(mist).opacity,
      rect: (() => { const r = mist.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height) }; })(),
    } : null,
    mistBoxFilter: mistBox ? cs(mistBox).filter.slice(0, 70) : null,
    videoPresent: !!video,
    video: video ? { src: video.currentSrc.split("/").pop(), paused: video.paused, dur: video.duration, t: video.currentTime } : null,
    vidWarm: getComputedStyle(document.documentElement).getPropertyValue("--vid-warm").trim(),
    sloganColor: slogan ? cs(slogan).color : null,
  };
}, concept);

/* 4) 雾带位移采样:隔 1.2s 读两次 transform,确认真的在动 */
let mistMotion = null;
if (concept === "letter") {
  const a = await page.evaluate(() => {
    const el = document.querySelectorAll(".lgh-mist i");
    return [...el].map((e) => getComputedStyle(e).transform);
  });
  await page.waitForTimeout(1400);
  const b = await page.evaluate(() => {
    const el = document.querySelectorAll(".lgh-mist i");
    return [...el].map((e) => getComputedStyle(e).transform);
  });
  mistMotion = a.map((v, i) => ({ i, before: v, after: b[i], moved: v !== b[i] }));
}

console.log("=== 样式表 ===");
for (const s of sheetStats) console.log(JSON.stringify(s));
console.log("=== 计算样式 ===");
console.log(JSON.stringify(style, null, 1));
if (mistMotion) { console.log("=== 雾带动了吗 ==="); console.log(JSON.stringify(mistMotion)); }
if (msgs.length) { console.log("=== 页面报错 ==="); msgs.slice(0, 10).forEach((m) => console.log(m)); }

await page.screenshot({ path: `.probe-${concept}.png`, fullPage: false });
await browser.close();
