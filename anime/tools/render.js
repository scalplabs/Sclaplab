// Usage: EP=2 node tools/render.js <outDir> [fps] [t1,t2,...]  — renders anime/index.html frames to JPEG
//        EP=4 THUMB=1 node tools/render.js <out.png>                — renders the episode's 9:16 thumbnail
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
(async () => {
  const out = process.argv[2]; const fps = +(process.argv[3] || 30);
  const only = process.argv[4] ? process.argv[4].split(',').map(Number) : null;
  const thumb = !!process.env.THUMB;
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 1920 } });
  page.on('pageerror', e => { console.error('PAGE ERROR', e); process.exit(1); });
  const q = `?render&ep=${process.env.EP || 1}${thumb ? '&thumb' : ''}`;
  await page.goto('file://' + path.resolve(__dirname, '../index.html') + q);
  await page.evaluate(() => window.ready);
  if (thumb) {
    const data = await page.evaluate(() => document.getElementById('c').toDataURL('image/png'));
    fs.writeFileSync(out, Buffer.from(data.split(',')[1], 'base64'));
    await browser.close(); return;
  }
  fs.mkdirSync(out, { recursive: true });
  const dur = await page.evaluate(() => DUR);
  const times = only || Array.from({ length: Math.round(dur * fps) }, (_, i) => i / fps);
  for (let i = 0; i < times.length; i++) {
    const data = await page.evaluate(t => { renderFrame(t); return document.getElementById('c').toDataURL('image/jpeg', 0.93); }, times[i]);
    const name = only ? `t${times[i]}.jpg` : `${String(i).padStart(4, '0')}.jpg`;
    fs.writeFileSync(path.join(out, name), Buffer.from(data.split(',')[1], 'base64'));
  }
  await browser.close();
})();
