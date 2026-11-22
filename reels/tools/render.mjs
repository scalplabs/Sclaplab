// node tools/render.mjs shots --ep NN --qa qa/NN --sheet   → qa/NN/sheet.jpg, one tile per shot (the shot check)
// node tools/render.mjs stills 1.2,5,9 --ep NN             → qa/t1.20.jpg … full-size single frames
// node tools/render.mjs info --ep NN                       → prints the shot plan
// node tools/render.mjs serve                              → live preview in your own browser (no sound)
// node tools/render.mjs video out.mp4 [--from s] [--to s] [--part i/n] [--gl metal|swiftshader] [--crf 14] [--cap png|jpeg|blob] [--enc x264|vt]
import { chromium } from 'playwright-core';
import { spawn } from 'child_process'; import fs from 'fs'; import path from 'path'; import os from 'os'; import http from 'http';
import { fileURLToPath } from 'url';
const A = process.argv.slice(2), MODE = A[0];
const opt = (k, d) => { const i = A.indexOf('--' + k); return i < 0 ? d : A[i + 1]; };
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const QA = path.resolve(ROOT, opt('qa', 'qa'));  // --qa qa/<ep> keeps parallel runs apart; --sheet writes one tiled <qa>/sheet.jpg
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.woff2': 'font/woff2', '.json': 'application/json' };
const srv = http.createServer((q, r) => { const f = path.join(ROOT, decodeURIComponent(q.url.split('?')[0])); fs.readFile(f, (e, d) => { if (e) { r.writeHead(404); r.end(); return; } r.writeHead(200, { 'Content-Type': MIME[path.extname(f)] || 'application/octet-stream' }); r.end(d); }); });
if (!MODE || MODE === 'help') { console.log(fs.readFileSync(fileURLToPath(import.meta.url), 'utf8').split('\n').slice(0, 5).join('\n')); process.exit(0); }
const EPN = opt('ep', null);
if (MODE !== 'serve') { if (!EPN) { console.error('Add --ep <episode>, for example --ep 01_right'); process.exit(1); }
  if (!fs.existsSync(path.join(ROOT, 'eps', EPN, 'timing.json'))) { console.error(`eps/${EPN}/timing.json not found. Run the voices first: python3 tools/tts.py ${EPN}`); process.exit(1); } }
await new Promise((r) => srv.listen(MODE === 'serve' ? +opt('port', 8123) : 0, '127.0.0.1', r)); const port = srv.address().port;
if (MODE === 'serve') { const eps = fs.readdirSync(path.join(ROOT, 'eps')).filter((e) => fs.existsSync(path.join(ROOT, 'eps', e, 'timing.json')));
  console.log('Preview (picture only, press play):'); for (const e of eps) console.log(`  http://127.0.0.1:${port}/index.html?ep=${e}`); console.log('Ctrl+C to stop.'); await new Promise(() => {}); }
const gl = opt('gl', os.platform() === 'darwin' ? 'metal' : 'swiftshader');
const args = gl === 'metal' ? ['--use-angle=metal', '--ignore-gpu-blocklist', '--enable-gpu-rasterization']
  : gl === 'egl' ? ['--use-angle=gl-egl', '--ignore-gpu-blocklist', '--enable-gpu']
  : ['--use-angle=swiftshader', '--use-gl=angle', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--disable-gpu-sandbox'];
// Chrome: --chrome <path>, or CHROME_PATH (environment or .env), or the normal install location of Google Chrome.
const dotenv = fs.existsSync(path.join(ROOT, '.env')) ? Object.fromEntries(fs.readFileSync(path.join(ROOT, '.env'), 'utf8').split('\n').filter((l) => l.includes('=') && !l.trim().startsWith('#')).map((l) => [l.slice(0, l.indexOf('=')).trim(), l.slice(l.indexOf('=') + 1).trim()])) : {};
const MAC = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const exe = opt('chrome', process.env.CHROME_PATH || dotenv.CHROME_PATH || (fs.existsSync(MAC) ? MAC : undefined));
const br = await chromium.launch({ ...(exe ? { executablePath: exe } : { channel: 'chrome' }), args: [...args, '--hide-scrollbars', '--force-device-scale-factor=1', '--force-color-profile=srgb'] })
  .catch((e) => { console.error('Could not start Google Chrome. Install it, or put its full path in .env as CHROME_PATH=...\n' + String(e.message).split('\n')[0]); process.exit(1); });
const ctx = await br.newContext({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
const pg = await ctx.newPage(); const errs = [];
pg.on('pageerror', (e) => errs.push('PAGEERROR ' + e.message)); pg.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') errs.push(m.text()); });
await pg.goto(`http://127.0.0.1:${port}/index.html?render=1${opt('ep', null) ? '&ep=' + opt('ep') : ''}${opt('aa', null) ? '&aa=' + opt('aa') : ''}${opt('cam', null) ? '&cam=' + opt('cam') : ''}`);
await pg.waitForFunction(() => window.READY === true, null, { timeout: 600000 }).catch((e) => { console.log(errs.join('\n')); throw e; });
const dur = await pg.evaluate(() => window.DUR), fps = await pg.evaluate(() => window.FPS);
const cdp = await ctx.newCDPSession(pg);
// --cap blob: JPEG encoded inside the page from the two canvases. Byte-identical to the CDP screenshot, ~1.6x faster (the screenshot round trip was 85% of a frame).
await pg.evaluate(() => { const off = new OffscreenCanvas(1080, 1920), c = off.getContext('2d'), gl = document.getElementById('gl'), cap = document.getElementById('cap');
  window.grab = async (t, q) => { await window.seek(t); c.drawImage(gl, 0, 0); c.drawImage(cap, 0, 0); const u = new Uint8Array(await (await off.convertToBlob({ type: 'image/jpeg', quality: q })).arrayBuffer());
    let s = ''; for (let i = 0; i < u.length; i += 32768) s += String.fromCharCode.apply(null, u.subarray(i, i + 32768)); return btoa(s); }; });
const snap = async (t, fmt) => { if (fmt === 'blob') return Buffer.from(await pg.evaluate(([t, q]) => window.grab(t, q), [t, +opt('q', 95) / 100]), 'base64'); await pg.evaluate((t) => window.seek(t), t); const s = await cdp.send('Page.captureScreenshot', fmt === 'jpeg' ? { format: 'jpeg', quality: +opt('q', 95) } : { format: 'png', optimizeForSpeed: true }); return Buffer.from(s.data, 'base64'); };
if (MODE === 'info') { console.log(JSON.stringify(await pg.evaluate(() => window.INFO()), null, 0).replace(/\],\["/g, '],\n["')); }
else if (MODE === 'shots') {
  const sh = (await pg.evaluate(() => window.SHOTS)).map((x) => x.t0); fs.rmSync(path.join(QA, 'shots'), { recursive: true, force: true }); fs.mkdirSync(path.join(QA, 'shots'), { recursive: true }); const files = [];
  for (let i = 0; i < sh.length; i++) { const t1 = i + 1 < sh.length ? sh[i + 1] : dur; const t = sh[i] + (t1 - sh[i]) * .55; const f = path.join(QA, 'shots', `s${String(i).padStart(2, '0')}.jpg`); fs.writeFileSync(f, await snap(t, 'jpeg')); files.push(f); }
  const { spawnSync } = await import('child_process');
  if (A.includes('--sheet')) spawnSync('ffmpeg', ['-v', 'error', '-y', '-framerate', '1', '-start_number', '0', '-i', path.join(QA, 'shots', 's%02d.jpg'), '-vf', `scale=240:426,tile=8x${Math.ceil(files.length / 8)}`, '-frames:v', '1', path.join(QA, 'sheet.jpg')]);
  else for (let k = 0; k < files.length; k += 7) { const grp = files.slice(k, k + 7); const inp = grp.flatMap((f) => ['-i', f]);
    spawnSync('ffmpeg', ['-v', 'error', '-y', ...inp, '-filter_complex', grp.map((_, j) => `[${j}]`).join('') + `hstack=${grp.length},scale=${300 * grp.length}:-1`, path.join(QA, `shots_${k / 7}.jpg`)]); }
  console.log('shots', sh.length);
} else if (MODE === 'stills') {
  fs.mkdirSync(QA, { recursive: true });
  for (const t of A[1].split(',').map(Number)) { const b = await snap(t, 'jpeg'); fs.writeFileSync(path.join(QA, `${opt('tag', 't')}${t.toFixed(2)}.jpg`), b); }
  console.log('stills ok'); 
} else {
  const out = A[1]; let n0 = Math.round(+opt('from', 0) * fps), n1 = Math.round(+opt('to', dur) * fps); n1 = Math.min(n1, Math.round(dur * fps));
  const part = opt('part', null); if (part) { const [i, n] = part.split('/').map(Number); const tot = n1 - n0, a = n0 + Math.floor(tot * i / n), b = n0 + Math.floor(tot * (i + 1) / n); n0 = a; n1 = b; }
  fs.mkdirSync(path.dirname(path.resolve(out)), { recursive: true });
  const CAP = opt('cap', 'png'), ENC = opt('enc', 'x264');
  const venc = ENC === 'vt' ? ['-c:v', 'h264_videotoolbox', '-b:v', opt('bv', '22M'), '-maxrate', opt('bv', '22M'), '-allow_sw', '0', '-profile:v', 'high', '-realtime', '0']
    : ['-c:v', 'libx264', '-preset', opt('preset', 'slow'), '-crf', opt('crf', '14'), '-threads', opt('threads', '4'), '-tune', 'film', '-x264-params', 'aq-mode=3'];
  const ff = spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', CAP === 'png' ? 'png' : 'mjpeg', '-i', '-', ...venc, '-pix_fmt', 'yuv420p', '-r', String(fps), '-g', '60', '-movflags', '+faststart', out], { stdio: ['pipe', 'inherit', 'inherit'] });
  const t0 = Date.now();
  for (let n = n0, k = 0; n < n1; n++, k++) {
    const b = await snap(n / fps, CAP); if (!ff.stdin.write(b)) await new Promise((r) => ff.stdin.once('drain', r));
    if (k % 30 === 0) console.log(`frame ${n}/${n1} ${((Date.now() - t0) / 1000 / (k + 1)).toFixed(2)}s/f`);
  }
  ff.stdin.end(); await new Promise((r) => ff.on('close', r));
  console.log(`done ${n1 - n0} frames in ${((Date.now() - t0) / 1000).toFixed(1)}s`);
}
console.log(errs.slice(0, 20).join('\n') || 'no page errors');
await br.close(); srv.close();
