/* 量测:视频整段的亮度/色彩动态范围,以及三个采样区的差异。
   目的是确定 --vid-warm 的归一化区间该取多少,以及要不要给天空区加权。 */
const PW = "file:///C:/Users/17536/.workbuddy/binaries/node/workspace/node_modules/playwright/index.mjs";
const { chromium } = await import(PW);

const browser = await chromium.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  args: ["--autoplay-policy=no-user-gesture-required"],
});
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
await page.addInitScript(() => { try { localStorage.setItem("aegis:concept", "radio"); } catch {} });
await page.goto("http://127.0.0.1:8000/", { waitUntil: "networkidle" });
await page.waitForTimeout(1200);

const scan = await page.evaluate(async () => {
  const v = document.querySelector(".lgh-video");
  const W = 48, H = 27;
  const c = document.createElement("canvas");
  c.width = W; c.height = H;
  const ctx = c.getContext("2d", { willReadFrequently: true });
  const out = [];
  const zones = {
    full: [0, 1, 0, 1],
    upper: [0.25, 0.75, 0.02, 0.42],
    card: [0.28, 0.72, 0.44, 0.86],
  };
  for (let k = 0; k < 14; k++) {
    const frac = k / 13;
    v.currentTime = v.duration * frac;
    await new Promise((r) => setTimeout(r, 120));
    ctx.drawImage(v, 0, 0, W, H);
    const d = ctx.getImageData(0, 0, W, H).data;
    const acc = {};
    for (const [name, [x0, x1, y0, y1]] of Object.entries(zones)) {
      let r = 0, g = 0, b = 0, n = 0;
      const px0 = Math.floor(W * x0), px1 = Math.ceil(W * x1);
      const py0 = Math.floor(H * y0), py1 = Math.ceil(H * y1);
      for (let y = py0; y < py1; y++) for (let x = px0; x < px1; x++) {
        const i = (y * W + x) * 4;
        r += d[i]; g += d[i + 1]; b += d[i + 2]; n++;
      }
      const rr = r / n, gg = g / n, bb = b / n;
      acc[name] = {
        rgb: [rr, gg, bb].map((x) => Math.round(x)),
        lum: +((0.2126 * rr + 0.7152 * gg + 0.0722 * bb) / 255).toFixed(4),
        warm: +((rr - bb) / 255).toFixed(4),
      };
    }
    out.push({ t: +v.currentTime.toFixed(2), ...acc });
  }
  return out;
});

console.log("t(s)   full.rgb / lum / r-b      upper.rgb / lum / r-b    card.rgb / lum / r-b");
for (const r of scan) {
  const f = r.full, u = r.upper, c = r.card;
  console.log(
    String(r.t).padStart(5),
    String(f.rgb).padEnd(14), f.lum.toFixed(3), f.warm.toFixed(3).padStart(6), "  ",
    String(u.rgb).padEnd(14), u.lum.toFixed(3), u.warm.toFixed(3).padStart(6), "  ",
    String(c.rgb).padEnd(14), c.lum.toFixed(3), c.warm.toFixed(3).padStart(6),
  );
}
const lums = scan.map((r) => r.full.lum);
console.log("\nfull lum  min/max =", Math.min(...lums), "/", Math.max(...lums),
  " 跨度 =", (Math.max(...lums) - Math.min(...lums)).toFixed(4));
const warns = scan.map((r) => r.full.warm);
console.log("full r-b  min/max =", Math.min(...warns).toFixed(3), "/", Math.max(...warns).toFixed(3),
  " 跨度 =", (Math.max(...warns) - Math.min(...warns)).toFixed(3));
await browser.close();
