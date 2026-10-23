// Renders a deterministic 60fps "screen recording" of the Halden page inside a macOS Safari frame,
// with a scripted cursor and Screen Studio-style camera zooms.
// Usage: node capture/capture.mjs <outDir> [seconds]
// Time is virtualised (rAF / performance.now / Date) so every frame is exact regardless of render speed.
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PW_PATH || '/opt/node-tools/node_modules/playwright');

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const out = process.argv[2] || join(root, 'frames');
const SECONDS = +(process.argv[3] || 10);
const FPS = 60, DT = 1000 / FPS, PORT = 8765;
const DSF = +(process.env.DSF || 2);
const OX = 160, OY = 128;          // site viewport origin inside the stage (window left, window top + toolbar)
const K = 1600 / 1920;             // site viewport is 1600x900
mkdirSync(out, { recursive: true });

const server = spawn('python3', ['-m', 'http.server', String(PORT), '--bind', '127.0.0.1'], { cwd: root, stdio: 'ignore' });
await new Promise(r => setTimeout(r, 600));

const browser = await chromium.launch({ args: ['--hide-scrollbars', '--force-color-profile=srgb'] });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: DSF });
await page.addInitScript(() => {
  let now = 0;
  const base = Date.UTC(2026, 9, 23, 9, 42, 7); // 18:42:07 in Seoul
  const queue = [];
  window.requestAnimationFrame = cb => (queue.push(cb), queue.length);
  window.cancelAnimationFrame = () => {};
  performance.now = () => now;
  const RealDate = Date;
  window.Date = class extends RealDate {
    constructor(...a) { a.length ? super(...a) : super(base + now); }
    static now() { return base + now; }
  };
  window.__step = ms => { now += ms; queue.splice(0).forEach(cb => cb(now)); };
});
await page.goto(`http://127.0.0.1:${PORT}/capture/mac.html`);
const site = page.frames().find(f => f.url().endsWith('/index.html'));
await site.waitForFunction(() => document.documentElement.dataset.ready === '1');

const ease = t => (t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const clamp01 = v => Math.min(1, Math.max(0, v));
const center = sel => site.evaluate(s => {
  const r = document.querySelector(s).getBoundingClientRect();
  return [r.left + r.width / 2, r.top + r.height / 2];
}, sel);
const P = (x, y) => [x * K, y * K];

// Cursor path in site coordinates. `to` is a point or a selector resolved when the move starts.
const moves = [
  { at: 0.0, dur: 1.3, to: P(1210, 690), arc: 34 },
  { at: 1.35, dur: 1.35, to: P(360, 380), arc: -76 },
  { at: 2.75, dur: 0.75, to: P(820, 650), arc: 42 },
  { at: 3.55, dur: 0.7, to: 'header nav a', arc: -50, off: [8, 3] },
  { at: 4.3, dur: 0.3, to: 'header nav a', off: [-7, -2], arc: 0 },
  { at: 4.85, dur: 0.9, to: P(1180, 600), arc: 34 },
  { at: 6.55, dur: 0.6, to: '.card:nth-child(3) .visual', arc: -26, off: [-24, 16] },
  { at: 7.2, dur: 0.45, off: [125, -92], rel: true, arc: 16 },
  { at: 7.7, dur: 0.45, off: [-140, 76], rel: true, arc: -16 },
  { at: 8.2, dur: 1.2, to: P(1320, 760), arc: 26 },
];
const clicks = [4.65];
const wheels = [[5.85, 6.55, 700], [8.15, 9.7, 1800]];

// Camera: target zoom over time; `follow` tracks the cursor, otherwise it eases back to the stage centre.
const shot = t =>
  t < 1.35 ? { s: 1 } :
  t < 3.45 ? { s: 1.2, follow: true } :
  t < 4.75 ? { s: 1.3, follow: true } :
  t < 6.5 ? { s: 1 } :
  t < 8.15 ? { s: 1.24, follow: true } :
  { s: 1 };

let pos = P(1560, 900);
let active = null;
const cam = { s: 1, fx: 960, fy: 540 };
const frames = Math.round(SECONDS * FPS);

for (let f = 0; f < frames; f++) {
  const t = f / FPS;

  const mv = moves.find(m => t >= m.at && t < m.at + m.dur + 1e-9);
  if (mv && active !== mv) {
    active = mv;
    let to = mv.to;
    if (mv.rel) to = [pos[0] + mv.off[0], pos[1] + mv.off[1]];
    else if (typeof to === 'string') { const c = await center(to); to = [c[0] + (mv.off?.[0] || 0), c[1] + (mv.off?.[1] || 0)]; }
    mv.from = [...pos]; mv.dest = to;
  }
  if (mv) {
    const p = ease(clamp01((t - mv.at) / mv.dur));
    const [x0, y0] = mv.from, [x1, y1] = mv.dest;
    const dx = x1 - x0, dy = y1 - y0, len = Math.hypot(dx, dy) || 1;
    const bow = Math.sin(p * Math.PI) * (mv.arc || 0);
    pos = [x0 + dx * p + (-dy / len) * bow, y0 + dy * p + (dx / len) * bow];
  } else {
    pos = [pos[0] + Math.sin(t * 2.1) * .2, pos[1] + Math.cos(t * 1.7) * .2];
  }

  const sp = [pos[0] + OX, pos[1] + OY]; // cursor in stage coordinates
  const sh = shot(t);
  cam.s += (sh.s - cam.s) * .065;
  const [tfx, tfy] = sh.follow ? sp : [960, 540];
  cam.fx += (tfx - cam.fx) * .07;
  cam.fy += (tfy - cam.fy) * .07;
  await page.evaluate(([s, fx, fy, b]) => { window.__cam(s, fx, fy); window.__bar(b); }, [cam.s, cam.fx, cam.fy, clamp01(t / .45)]);

  await page.mouse.move(cam.fx + (sp[0] - cam.fx) * cam.s, cam.fy + (sp[1] - cam.fy) * cam.s);

  for (const c of clicks) if (Math.abs(t - c) < DT / 2000) { await page.mouse.down(); await page.mouse.up(); }
  for (const [a, b, total] of wheels) {
    if (t >= a && t < b) {
      const p0 = (t - a) / (b - a), p1 = Math.min(1, (t + 1 / FPS - a) / (b - a));
      const dy = total * (Math.sin(p1 * Math.PI / 2) ** 2 - Math.sin(p0 * Math.PI / 2) ** 2);
      if (dy) await page.mouse.wheel(0, dy);
    }
  }

  await site.evaluate(ms => window.__step(ms), DT);
  await page.screenshot({ path: join(out, `f${String(f).padStart(4, '0')}.jpg`), type: 'jpeg', quality: 95 });
  if (f % 60 === 0) process.stdout.write(`${t.toFixed(0)}s `);
}
console.log('done');
await browser.close();
server.kill();
