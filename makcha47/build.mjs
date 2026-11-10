// 막차 47 PART 1 — builds index.html (HyperFrames native: <img> + one paused GSAP timeline).
// Scene/caption timing comes from narration_alignment.json; look values come from
// reference/막차47_영상엔진_v2.html (S array). No canvas, no requestAnimationFrame, no timers.
import fs from 'node:fs';

const W = 1080, H = 1920, FPS = 30;
const words = JSON.parse(fs.readFileSync('narration_alignment.json', 'utf8')).words.filter(w => w.type === 'word');
const NARR_END = words.at(-1).end;

// Caption chunks: [text, firstWordIdx, lastWordIdx]. *x* = yellow highlight.
const SCENES = [
  { id: 's01', img: 's01_phone', hud: false, capY: H * 0.42, cam: { fx: 0.55, z0: 1.05, z1: 1.25 }, vig: 0.6,
    chunks: [['어젯밤', 0, 0], ['*모르는 번호*로', 1, 2], ['문자가 왔다', 3, 4]] },
  { id: 's02', img: 's02_wake', cam: { fx: 0.5, z0: 1.25, z1: 1.05 }, vig: 0.55,
    chunks: [['눈을 떠보니', 5, 6], ['*2호선 막차*', 7, 8], ['승객은', 9, 9], ['딱 *100명*', 10, 11]] },
  { id: 's03', img: 's03_speaker', cam: { fx: 0.5, fy: 0.45, z0: 1.0, z1: 1.3 }, vig: 0.6,
    chunks: [['안내방송이 나온다', 12, 13], ['역에 설 때마다', 14, 16], ['*한 명씩* 내린다', 17, 19], ['내린 사람은', 20, 21], ['*돌아오지 못한다*', 22, 23]] },
  { id: 's04', img: 's04_money', cam: { fx: 0.5, fy: 0.4, z0: 1.0, z1: 1.15 }, vig: 0.5,
    chunks: [['한 명이 사라질 때마다', 24, 27], ['상금 *1억*이 쌓인다', 28, 30]] },
  { id: 's05', img: 's05_99', cam: { fx: 0.5, fy: 0.35, z0: 1.1, z1: 1.2 }, vig: 0.5,
    chunks: [['*첫 번째 역*', 31, 33]] },
  { id: 's06', img: 's06_door', cam: { fx: 0.6, z0: 1.0, z1: 1.18 }, vig: 0.5,
    chunks: [['문 앞에 서 있던', 34, 37], ['*23번*이', 38, 38], ['사라졌다', 39, 39]] },
  { id: 's07', img: 's02_wake', cam: { fx: 0.12, fy: 0.5, z0: 1.6, z1: 1.85 }, bright: 0.8, vig: 0.65,
    chunks: [['그때', 40, 40], ['*12번*이 다가와', 41, 42], ['속삭인다', 43, 43], ['"나 여기서', 44, 45], ['*나가는 법* 알아"', 46, 48]] },
  { id: 's08', img: 's08_hand', cam: { fx: 0.5, fy: 0.5, z0: 1.0, z1: 1.35 }, vig: 0.7,
    chunks: [['근데 *이상하다*', 49, 50], ['12번 손에', 51, 52], ['*피*가 묻어 있다', 53, 55]] },
  { id: 's09', img: 's09_choice', cam: { fx: 0.5, z0: 1.0, z1: 1.1 }, bright: 0.75, vig: 0.5, capY: H * 0.8,
    chunks: [['너라면', 56, 56], ['*어떻게 할래?*', 57, 58]] },
  { id: 's10', img: 's10_tunnel', hud: false, cam: { fx: 0.5, z0: 1.0, z1: 1.25 }, bright: 0.55, vig: 0.6, chunks: [] },
];

// ---- timing from alignment (snapped to frames) ----
const snap = t => Math.round(t * FPS) / FPS;
SCENES.forEach((s, i) => { s.start = i === 0 ? 0 : snap(words[s.chunks[0]?.[1] ?? 0].start); });
SCENES[9].start = snap(NARR_END + 1.5);           // A/B cards need ~1.5s after the last word
SCENES.forEach((s, i) => { s.end = i < 9 ? SCENES[i + 1].start : s.start + 4.0; s.dur = +(s.end - s.start).toFixed(4); });
const TOTAL = SCENES[9].end;
for (const s of SCENES) {
  s.cs = s.chunks.map(([text, a, b], j) => {
    const st = snap(words[a].start);
    const next = s.chunks[j + 1];
    const en = next ? snap(words[next[1]].start) : Math.min(snap(words[b].end + 0.35), s.end);
    return { text, st, en };
  });
}
const local = (s, wi) => snap(words[wi].start) - s.start;   // word start, scene-local
// scene-local event times (reference used fixed seconds; here they follow the voice)
const EV = {
  poolStart: local(SCENES[3], 28),            // "상금"
  drop: 0.25,                                 // 100 -> 99 just after the cut to s05
  doorFlash: local(SCENES[5], 39),            // "사라졌다"
  bubble: local(SCENES[6], 44),               // "나 여기서"
};
EV.poolDur = Math.min(1.0, SCENES[3].dur - EV.poolStart - 0.2);

// ---- HTML helpers ----
const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const F = "'Noto Sans KR',sans-serif", MONO = "'JB Mono','Noto Sans KR',monospace";
const svg = (inner, extra = '') => `<svg class="ov" ${extra} viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">${inner}</svg>`;
const vignette = a => `<div class="vig" style="background:radial-gradient(circle at 50% 48.75%, rgba(0,0,0,0) 480px, rgba(0,0,0,${a}) 1536px)"></div><div class="vtop"></div>`;

function overlays(s) {
  const o = { under: '', over: '' };   // under = before vignette, over = after
  if (s.id === 's01') o.under = svg(`<g id="msg" opacity="0"><rect x="170" y="980" width="740" height="220" rx="30" fill="rgba(20,28,40,.88)"/>
      <text font-family="${F}" font-weight="600" font-size="46" fill="#e9f1ff" xml:space="preserve"><tspan id="msg1" x="210" y="1060"></tspan><tspan id="msg2" x="210" y="1126"></tspan></text></g>`);
  if (s.id === 's04') o.over = svg(`<text id="plus" opacity="0" x="540" y="${H * 0.74}" text-anchor="middle" font-family="${MONO}" font-weight="800" font-size="50" fill="#9ef0a8" style="filter:drop-shadow(0 0 6px #000)">+ ₩100,000,000 / 1명</text>`);
  if (s.id === 's05') o.over = svg(`<text id="out23" opacity="0" x="70" y="300" font-family="${MONO}" font-weight="700" font-size="40" fill="#ff6b6b">✕ 참가자 23 탈락</text>`);
  if (s.id === 's07') o.under = `<div id="bubble" class="bub">${svg(`<g transform="translate(${W * 0.62},${H * 0.36})">
      <rect x="-220" y="-70" width="440" height="140" rx="40" fill="#fff" stroke="#111" stroke-width="7"/>
      <path d="M-150 66 L-200 130 L-90 66 Z" fill="#fff" stroke="#111" stroke-width="7" stroke-linejoin="miter"/>
      <rect x="-160" y="58" width="80" height="12" fill="#fff"/>
      <text x="0" y="4" text-anchor="middle" dominant-baseline="middle" font-family="${F}" font-weight="800" font-size="50" fill="#111">나가는 법 알아</text></g>`)}</div>`;
  if (s.id === 's09') {
    const card = (id, y, label, txt, col) => `<div id="${id}" class="card">${svg(`<g transform="translate(540,${y})">
      <rect x="-440" y="-90" width="880" height="180" rx="30" fill="rgba(10,14,20,.88)" stroke="${col}" stroke-width="6"/>
      <circle cx="-345" cy="0" r="52" fill="${col}"/>
      <text x="-345" y="4" text-anchor="middle" dominant-baseline="middle" font-family="${F}" font-weight="900" font-size="60" fill="#000">${label}</text>
      <text x="-265" y="4" dominant-baseline="middle" font-family="${F}" font-weight="800" font-size="54" fill="#fff">${txt}</text></g>`)}</div>`;
    o.over = card('cardA', H * 0.36, 'A', '12번을 따라간다', '#ffd84a') + card('cardB', H * 0.36 + 220, 'B', '혼자 움직인다', '#7fd3ff');
  }
  if (s.id === 's10') o.over = svg(`<g id="ask">
      <text x="540" y="760" text-anchor="middle" font-family="${F}" font-weight="900" font-size="100" fill="#fff" style="filter:drop-shadow(0 0 8px #000)">너라면 뭐 할래?</text>
      <text x="540" y="840" text-anchor="middle" font-family="${F}" font-weight="700" font-size="42" fill="#cfdbe2">댓글에 너의 선택을 적어줘</text>
      <rect x="130" y="910" width="820" height="116" rx="58" fill="rgba(20,26,34,.92)"/>
      <text id="typed" x="190" y="984" font-family="${F}" font-weight="600" font-size="44" fill="#eee" xml:space="preserve">댓글 달기...</text>
      <circle cx="890" cy="968" r="38" fill="#ffd84a"/>
      <text x="540" y="1160" text-anchor="middle" font-family="${F}" font-weight="900" font-size="46" fill="#ffd84a">댓글 1등이 PART 2를 정한다</text></g>
    <g id="logo" opacity="0">
      <text x="540" y="760" text-anchor="middle" font-family="${F}" font-weight="900" font-size="170" fill="#7fd3ff" style="filter:drop-shadow(0 0 15px #7fd3ff)">99</text>
      <text x="540" y="930" text-anchor="middle" font-family="${F}" font-weight="900" font-size="130" fill="#fff">막차 47</text>
      <text x="540" y="1005" text-anchor="middle" font-family="${MONO}" font-weight="700" font-size="42" fill="#ff5a5a">PART 1 · 네가 정해</text>
      <circle cx="430" cy="1190" r="52" fill="#ff4d6d"/><text x="430" y="1208" text-anchor="middle" font-family="${F}" font-weight="900" font-size="50" fill="#fff">♥</text>
      <circle cx="650" cy="1190" r="52" fill="#ddd"/><text x="650" y="1208" text-anchor="middle" font-family="${F}" font-weight="900" font-size="50" fill="#000">+</text>
      <text x="430" y="1282" text-anchor="middle" font-family="${F}" font-weight="600" font-size="30" fill="#bbb">좋아요</text>
      <text x="650" y="1282" text-anchor="middle" font-family="${F}" font-weight="600" font-size="30" fill="#bbb">팔로우</text></g>`);
  return o;
}

function captionSvg(text, y) {
  const spans = text.split(/(\*[^*]+\*)/).filter(Boolean).map(p => p.startsWith('*')
    ? `<tspan fill="#ffd84a">${esc(p.slice(1, -1))}</tspan>` : `<tspan>${esc(p)}</tspan>`).join('');
  return svg(`<text x="540" y="${y}" text-anchor="middle" dominant-baseline="middle" font-family="${F}" font-weight="900" font-size="100"
    fill="#fff" stroke="#000" stroke-width="20" stroke-linejoin="round" paint-order="stroke" xml:space="preserve">${spans}</text>`);
}

const r3 = x => +x.toFixed(3);
let html = '';
SCENES.forEach((s, i) => {
  const o = overlays(s);
  html += `
  <div id="${s.id}" class="scene clip" data-start="${r3(s.start)}" data-duration="${r3(s.dur)}" data-track-index="0">
    <img id="${s.id}img" class="bg" src="scenes/${s.img}.png" alt=""${s.bright ? ` style="filter:brightness(${s.bright})"` : ''}>
    <div id="${s.id}flash" class="flash"></div>
    ${o.under}${vignette(s.vig)}${o.over}
  </div>`;
});
const hudStart = SCENES[1].start, hudEnd = SCENES[8].end;
html += `
  <div id="hud" class="clip" data-start="${r3(hudStart)}" data-duration="${r3(hudEnd - hudStart)}" data-track-index="1">
    ${svg(`<text font-family="${F}" fill="#fff"><tspan id="left" x="60" y="170" font-weight="900" font-size="110">100</tspan><tspan dx="12" dy="-5" font-weight="700" font-size="34">명 남음</tspan></text>`, 'style="filter:drop-shadow(0 0 7px rgba(0,0,0,.7))"')}
    ${svg(`<line x1="60" y1="198" x2="400" y2="198" stroke="rgba(255,255,255,.5)" stroke-width="3"/>
      <text id="pool" x="62" y="240" font-family="${MONO}" font-weight="600" font-size="30" fill="#d6e2e8" xml:space="preserve">상금 ₩0</text>`)}
  </div>`;
SCENES.forEach(s => s.cs.forEach((c, j) => {
  html += `
  <div id="${s.id}c${j}" class="cap clip" data-start="${r3(c.st)}" data-duration="${r3(c.en - c.st)}" data-track-index="2"
       style="transform-origin:540px ${s.capY ?? H * 0.62}px">${captionSvg(c.text, s.capY ?? H * 0.62)}</div>`;
}));
html += `
  <div id="grain" class="clip" data-start="0" data-duration="${r3(TOTAL)}" data-track-index="3"></div>
  <audio id="narr" src="narration.mp3" data-start="0" data-duration="${r3(Math.min(TOTAL, NARR_END + 0.3))}" data-track-index="4"></audio>`;

// ---- timeline data for the inline script ----
const data = {
  W, H, FPS, TOTAL, EV,
  scenes: SCENES.map(s => ({ id: s.id, start: s.start, dur: s.dur, cam: s.cam, caps: s.cs.map(c => c.st) })),
};

const script = String.raw`
const D = ${JSON.stringify(data)};
const {W,H,FPS,EV} = D;
const clamp=(x,a=0,b=1)=>Math.max(a,Math.min(b,x)), lerp=(a,b,k)=>a+(b-a)*k;
const ease=x=>{x=clamp(x);return x<.5?2*x*x:1-Math.pow(-2*x+2,2)/2;}, eout=x=>1-Math.pow(1-clamp(x),3);
const tl = gsap.timeline({ paused: true });
const $ = id => document.getElementById(id);
// Every frame is a pure function of time: precompute per-frame values and place them on the timeline.
function perFrame(sc, fn){ const n=Math.round(sc.dur*FPS); for(let f=0;f<n;f++){ const t=f/FPS; fn(t, sc.start+t); } }
function cam(t,d,{fx=.5,fy=.5,z0=1,z1=1.12},shake=0){
  const z=lerp(z0,z1,ease(t/d)), w=1920*z, h=1920*z;
  let x=W/2-fx*w, y=H/2-fy*h; x=Math.min(0,Math.max(W-w,x)); y=Math.min(0,Math.max(H-h,y));
  if(shake){ x+=Math.sin(t*40)*shake; y+=Math.cos(t*34)*shake; }
  return {x,y,scale:z};
}
const flashFn = {
  s02:t=>['#000', 1-t/0.5],
  s03:t=>['#ff141e', 0.10*(0.5+0.5*Math.sin(t*9))],
  s05:t=>['#ff0014', t>EV.drop?0.55*(1-clamp((t-EV.drop)/0.6)):0],
  s06:t=>['#fff', t>EV.doorFlash?0.7*Math.sin(clamp((t-EV.doorFlash)/0.6)*Math.PI):0],
  s08:t=>['#000', 0.35*(1-clamp(t/1.2))],
};
for(const sc of D.scenes){
  const img=$(sc.id+'img'), fl=$(sc.id+'flash');
  gsap.set(img,{transformOrigin:'0 0'});
  const ff=flashFn[sc.id]; if(ff) tl.set(fl,{backgroundColor:ff(0)[0]},sc.start);
  perFrame(sc,(t,T)=>{
    const shake = sc.id==='s05' && t>EV.drop && t<EV.drop+0.5 ? 14 : 0;
    tl.set(img, cam(t,sc.dur,sc.cam,shake), T);
    if(ff) tl.set(fl,{opacity:clamp(ff(t)[1])},T);
  });
}
// captions pop: scale 1.18 -> 1 over 0.12s (ease out cubic)
document.querySelectorAll('.cap').forEach((el)=>{ const st=+el.dataset.start; tl.fromTo(el,{scale:1.18},{scale:1,duration:0.12,ease:'power3.out'},st); });
const S = Object.fromEntries(D.scenes.map(s=>[s.id,s]));
// s01: message box fades in and types
{ const sc=S.s01, m1='축하합니다, 참가자 47번.', m2='당신은 선택되었습니다.'; let last=-1;
  perFrame(sc,(t,T)=>{ const k=clamp((t-0.6)/1.2); tl.set($('msg'),{opacity:k},T);
    const n=Math.floor(k*30); if(n!==last){ last=n; const s=(m1+'\n'+m2).slice(0,n).split('\n');
      tl.set($('msg1'),{textContent:s[0]||''},T); tl.set($('msg2'),{textContent:s[1]||''},T); } }); }
// s04: prize pool counts up, then "+ ₩100,000,000 / 1명"
{ const sc=S.s04; let last='';
  perFrame(sc,(t,T)=>{ const v=t>EV.poolStart?lerp(0,1e8,eout((t-EV.poolStart)/EV.poolDur)):0;
    const s='상금 ₩'+Math.round(v).toLocaleString('en-US'); if(s!==last){ last=s; tl.set($('pool'),{textContent:s},T); } });
  tl.set($('plus'),{opacity:1}, sc.start+EV.poolStart+EV.poolDur); }
// s05: 100 -> 99, eliminated tag
{ const sc=S.s05; tl.set($('pool'),{textContent:'상금 ₩100,000,000'},sc.start);
  tl.set($('left'),{textContent:'99'},sc.start+EV.drop); tl.set($('out23'),{opacity:1},sc.start+EV.drop); }
// s07: speech bubble pops
{ const sc=S.s07, el=$('bubble'); gsap.set(el,{transformOrigin:(W*0.62)+'px '+(H*0.36)+'px'});
  tl.fromTo(el,{scale:0},{scale:1,duration:0.25,ease:'power3.out'},sc.start+EV.bubble); }
// s09: A/B cards slide in from the right
{ const sc=S.s09; tl.fromTo($('cardA'),{x:700},{x:0,duration:0.35,ease:'power3.out'},sc.start+0.2);
  tl.fromTo($('cardB'),{x:700},{x:0,duration:0.35,ease:'power3.out'},sc.start+0.5); }
// s10: comment typing, then logo
{ const sc=S.s10, msg='나라면 B. 혼자 간다'; let last=-1;
  perFrame(sc,(t,T)=>{ if(t>=2.4) return; const n=Math.floor(clamp((t-0.4)/1.2)*12);
    if(n!==last){ last=n; tl.set($('typed'),{textContent:n?msg.slice(0,n):'댓글 달기...'},T); } });
  tl.set($('ask'),{opacity:0},sc.start+2.4);
  perFrame(sc,(t,T)=>{ if(t>=2.4) tl.set($('logo'),{opacity:eout((t-2.4)/0.5)},T); }); }
// film grain: jump the noise tile every frame
{ const g=$('grain'), n=Math.round(D.TOTAL*FPS); for(let f=0;f<n;f++) tl.set(g,{x:-((f*131)%256),y:-((f*71)%256)},f/FPS); }
tl.set({}, {}, D.TOTAL);
window.__timelines = window.__timelines || {};
window.__timelines['root'] = tl;
`;

const grainSvg = encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch"/><feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 1.4 -0.55"/></filter><rect width="256" height="256" filter="url(#n)"/></svg>`);

const page = `<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=${W}, height=${H}">
<title>막차 47 PART 1</title>
<link rel="stylesheet" href="fonts/fonts.css">
<style>
  html,body{margin:0;padding:0;background:#000;overflow:hidden}
  #root{position:relative;width:${W}px;height:${H}px;overflow:hidden;background:#000;font-family:${F}}
  .clip{position:absolute;inset:0;width:${W}px;height:${H}px;overflow:hidden}
  .scene{background:#000}
  .bg{position:absolute;left:0;top:0;width:1920px;height:1920px;max-width:none;object-fit:cover;will-change:transform}
  .flash{position:absolute;inset:0;opacity:0;pointer-events:none}
  .vig,.vtop{position:absolute;inset:0;pointer-events:none}
  .vtop{bottom:auto;height:320px;background:linear-gradient(rgba(0,0,0,.55),rgba(0,0,0,0))}
  .ov{position:absolute;left:0;top:0;width:${W}px;height:${H}px;overflow:visible}
  .bub,.card{position:absolute;inset:0}
  .cap{pointer-events:none}
  #grain{inset:auto;left:0;top:0;width:${W + 256}px;height:${H + 256}px;overflow:visible;
    background:url("data:image/svg+xml,${grainSvg}");opacity:.05;mix-blend-mode:screen;pointer-events:none}
</style></head>
<body>
<div id="root" data-composition-id="root" data-width="${W}" data-height="${H}" data-duration="${r3(TOTAL)}">${html}
</div>
<script src="vendor/gsap.min.js"></script>
<script>${script}</script>
</body></html>
`;
fs.writeFileSync('index.html', page);
const report = SCENES.map((s, i) => `${String(i + 1).padStart(2)} ${s.id} ${s.img.padEnd(12)} start ${s.start.toFixed(2)}s  dur ${s.dur.toFixed(2)}s`).join('\n');
fs.writeFileSync('scene_times.txt', report + `\nTOTAL ${TOTAL.toFixed(2)}s\n`);
console.log(report + `\nTOTAL ${TOTAL.toFixed(2)}s`, '\nEV', EV);
