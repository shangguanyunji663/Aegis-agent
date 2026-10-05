/* 改动后复验:玻璃是否生效 / 卡片是否完整可见 / 雾是否真的在动。
   产出:<concept>-t0.png、<concept>-t1.png(相隔 1.8s)、<concept>-auth.png */
const PW = "file:///C:/Users/17536/.workbuddy/binaries/node/workspace/node_modules/playwright/index.mjs";
const { chromium } = await import(PW);

const BASE = "http://127.0.0.1:8000/";
const browser = await chromium.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  args: ["--autoplay-policy=no-user-gesture-required"],
});
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });

const out = {};
for (const concept of ["letter", "radio", "atlas"]) {
  const page = await ctx.newPage();
  await page.addInitScript((c) => { try { localStorage.setItem("aegis:concept", c); } catch {} }, concept);
  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);

  // 背景静置区间(避开居中文字):左侧 0-340px
  const clip = { x: 0, y: 90, width: 340, height: 720 };
  await page.screenshot({ path: `.v-${concept}-t0.png`, clip });
  await page.waitForTimeout(1800);
  await page.screenshot({ path: `.v-${concept}-t1.png`, clip });

  // 展开认证卡
  await page.evaluate(() => document.querySelector(".lgh-inputbar")?.click());
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `.v-${concept}-auth.png` });

  out[concept] = await page.evaluate((c) => {
    const sel = { letter: ".lg-slip", radio: ".rg-console", atlas: ".at-logbook" }[c];
    const card = document.querySelector(sel);
    const portal = document.querySelector(".lgh-portal");
    const mist = document.querySelector(".lgh-mist i");
    const cs = (e) => e ? getComputedStyle(e) : null;
    const r = card?.getBoundingClientRect();
    return {
      cardSel: sel,
      backdropFilter: cs(card)?.backdropFilter,
      cardBgImage: cs(card)?.backgroundImage?.slice(0, 70),
      cardBox: r ? { top: Math.round(r.top), bottom: Math.round(r.bottom), h: Math.round(r.height) } : null,
      // 卡片底边是否落在视口内(留 8px 余量)
      cardFitsViewport: r ? r.bottom <= window.innerHeight - 8 : null,
      portalClass: portal?.className,
      mistAnimation: cs(mist)?.animationName,
      mistDuration: cs(mist)?.animationDuration,
      mistBlend: cs(mist)?.mixBlendMode,
      docScrollable: document.documentElement.scrollHeight > window.innerHeight + 2,
    };
  }, concept);
  await page.close();
}
console.log(JSON.stringify(out, null, 1));
await browser.close();
