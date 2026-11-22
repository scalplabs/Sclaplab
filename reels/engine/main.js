// Generic engine: window.seek(t) renders frame t of an episode (?ep=NN_name). Pure function of t.
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { BokehPass } from 'three/addons/postprocessing/BokehPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { makeFounder, makeClawd, setFMouth, setFBlink, setCEyes, rng, strSeed } from './chars.js';
import { buildSet, animateSet, KEY_TOP } from './set.js';
import { drawUI, setUI } from './ui.js';

const Q = new URLSearchParams(location.search);
const EP = Q.get('ep'), W = 1080, H = 1920, AA = +(Q.get('aa') || 4);
const RENDER = Q.has('render'); if (RENDER) document.body.classList.add('render');
const T = await (await fetch(`eps/${EP}/timing.json`)).json();
const FPS = T.fps || 30, DUR = T.dur, LINES = T.lines;
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const sm = (x) => { x = clamp(x); return x * x * (3 - 2 * x); };
const eio = (x) => { x = clamp(x); return x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; };
const eout = (x) => 1 - Math.pow(1 - clamp(x), 3);
const lerp = (a, b, u) => a + (b - a) * u;
const noise = (t, s) => Math.sin(t * 1.31 + s) * .5 + Math.sin(t * 2.17 + s * 2.3) * .3 + Math.sin(t * .53 + s * 4.1) * .2;
const V = (a) => new THREE.Vector3(a[0], a[1], a[2]);

// ---------------------------------------------------------------- renderer / scene / post
const canvas = document.getElementById('gl');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(1); renderer.setSize(W, H, false);
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.12;
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const scene = new THREE.Scene(); scene.background = new THREE.Color(0x05061a);
const cam = new THREE.PerspectiveCamera(32, W / H, 0.5, 4000);

setUI(T.ui, (T.uiEvents || []).map((e) => ({ ...e, t: e.t ?? (LINES.find((l) => l.id === e.line)?.s ?? 0) + (e.dt || 0) })));
const S = buildSet(scene);
const F = makeFounder(), C = makeClawd();
scene.add(F.root, C.root);
const FSEAT = { x: -5.2, y: -0.08, z: 1.6, yaw: .42 }, CSEAT = { x: 4.9, y: KEY_TOP, z: 0.9, yaw: -.4 };

const rt = new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, samples: AA });
const composer = new EffectComposer(renderer, rt); composer.setPixelRatio(1); composer.setSize(W, H);
composer.addPass(new RenderPass(scene, cam));
const bokeh = new BokehPass(scene, cam, { focus: 30, aperture: 0.004, maxblur: 0.012 }); composer.addPass(bokeh);
const bloom = new UnrealBloomPass(new THREE.Vector2(W, H), 0.4, 0.7, 0.9); composer.addPass(bloom);
composer.addPass(new OutputPass());
const finish = new ShaderPass({
  uniforms: { tDiffuse: { value: null }, uTime: { value: 0 }, uVig: { value: .62 }, uGrain: { value: .05 }, uCA: { value: .0015 }, uFade: { value: 0 }, uLift: { value: new THREE.Vector3(.016, .013, .042) }, uStreak: { value: 0 } },
  vertexShader: 'varying vec2 vUv; void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }',
  fragmentShader: `uniform sampler2D tDiffuse; uniform float uTime,uVig,uGrain,uCA,uFade,uStreak; uniform vec3 uLift; varying vec2 vUv;
    float h(vec2 p){ return fract(sin(dot(p, vec2(12.9898,78.233))+uTime*7.13)*43758.5453); }
    void main(){ vec2 c=vUv-.5; float r=length(c*vec2(.5625,1.)); vec2 o=c*uCA*(1.+r*2.);
      vec3 col=vec3(texture2D(tDiffuse,vUv+o).r, texture2D(tDiffuse,vUv).g, texture2D(tDiffuse,vUv-o).b);
      col = col + uLift*(1.-col); col *= mix(1., smoothstep(.98,.2,r*1.22), uVig);
      float g=h(vUv*vec2(1080.,1920.))-.5; col += g*uGrain*(1.-col*.6);
      col *= 1.-uFade; gl_FragColor=vec4(col,1.); }` });
composer.addPass(finish);

// ---------------------------------------------------------------- poses
const FP_KEYS = ['tx', 'ty', 'tz', 'nx', 'ny', 'nz', 'lsx', 'lsy', 'lsz', 'lex', 'ley', 'lez', 'rsx', 'rsy', 'rsz', 'rex', 'rey', 'rez', 'phone', 'swing'];
const fpv = (o) => FP_KEYS.map((k) => o[k] ?? 0);
const FPOSE = {
  idle: fpv({ tx: .1, ty: .1, nx: .02, ny: .2, lsx: -.55, lsz: .12, lex: -1.0, rsx: -.95, rsz: -.2, rex: -1.5, swing: 1 }),
  talk: fpv({ tx: .12, ty: .1, nx: .0, ny: .22, lsx: -.6, lsz: .3, lex: -1.1, rsx: -1.1, rsz: .25, rex: -1.3, swing: 1 }),
  listen: fpv({ tx: .14, ty: .1, nx: .06, ny: .3, nz: .08, lsx: -.55, lsz: .12, lex: -1.0, rsx: -.95, rsz: -.2, rex: -1.5, swing: 1 }),
  shrug: fpv({ tx: .05, ty: .05, nx: -.03, nz: .12, lsx: -.35, lsz: .85, lex: -1.35, rsx: -.35, rsz: .85, rex: -1.35, swing: 1 }),
  chin: fpv({ tx: .18, ty: .12, nx: .1, ny: .2, nz: .05, lsx: -.55, lsz: .12, lex: -1.0, rsx: -1.15, rsz: -.55, rex: -2.45, swing: 1 }),
  facepalm: fpv({ tx: .22, ty: .1, nx: .3, ny: .1, lsx: -.55, lsz: .12, lex: -1.0, rsx: -1.55, rsz: -.25, rex: -2.75, rey: .2, swing: 0 }),
  point: fpv({ tx: .08, ty: .25, nx: .0, ny: .35, lsx: -.55, lsz: .12, lex: -1.0, rsx: -.25, rsz: 1.5, rex: -.15, swing: 1 }),
  phone: fpv({ tx: .26, ty: .08, nx: .5, ny: .08, lsx: -1.05, lsz: -.05, lex: -1.55, rsx: -1.05, rsz: .05, rex: -1.6, phone: 1, swing: 0 }),
  fist: fpv({ tx: .02, ty: .1, nx: -.05, ny: .2, lsx: -.55, lsz: .12, lex: -1.0, rsx: -2.45, rsz: .3, rex: -.5, swing: 1 }),
  slump: fpv({ tx: .42, ty: .08, nx: .38, ny: .1, lsx: -.35, lsz: .15, lex: -.7, rsx: -.4, rsz: .1, rex: -.7, swing: 0 }),
  up: fpv({ tx: -.06, ty: .1, nx: -.08, ny: .3, lsx: -.5, lsz: .2, lex: -1.0, rsx: -.5, rsz: -.1, rex: -1.0, swing: 1 }),
  lean: fpv({ tx: .3, ty: .22, nx: .08, ny: .45, lsx: -.6, lsz: .12, lex: -1.0, rsx: -.7, rsz: .2, rex: -1.2, swing: 1 }),
  duck: fpv({ tx: .2, ty: -.5, nx: .06, ny: -.8, lsx: -.55, lsz: .12, lex: -1.0, rsx: -.95, rsz: -.2, rex: -1.5, swing: 1 }),
  away: fpv({ tx: .1, ty: -.35, nx: .05, ny: -.5, lsx: -.55, lsz: .12, lex: -1.0, rsx: -.95, rsz: -.2, rex: -1.5, swing: 0 }),
};
const CP_KEYS = ['lean', 'tilt', 'yaw', 'sq', 'alx', 'alz', 'arx', 'arz'];
const cpv = (o) => CP_KEYS.map((k) => o[k] ?? (k === 'sq' ? 1 : 0));
const CPOSE = {
  idle: cpv({ yaw: -.15 }), talk: cpv({ yaw: -.2, lean: .04, arx: -.2, alx: -.15 }), listen: cpv({ yaw: -.22, tilt: .06 }),
  lean: cpv({ yaw: -.28, lean: .14 }), tilt: cpv({ yaw: -.15, tilt: .16 }), flap: cpv({ yaw: -.4, sq: 1.04, arx: -1.1, alx: -1.1, arz: .5, alz: -.5 }),
  hunch: cpv({ yaw: -.35, sq: .9, lean: .1 }), proud: cpv({ yaw: -.4, sq: 1.07, lean: -.05, arz: .35, alz: -.35 }),
  away: cpv({ yaw: .9, lean: .02 }), sad: cpv({ yaw: -.3, sq: .92, lean: .12, tilt: -.07, arx: .15, alx: .15 }), point: cpv({ yaw: -.6, lean: .08, alx: -1.3, alz: -.4 }),
};
const FACE = { // founder face: brow height/tilt, smile, eye scale   |   clawd eyes: w,h,y,rot
  norm: { brow: .2, rot: 0, smile: 0 }, worry: { brow: .8, rot: .35, smile: -.1 }, smirk: { brow: .35, rot: -.15, smile: .8 }, shock: { brow: 1.1, rot: 0, smile: 0 },
  sad: { brow: .6, rot: .5, smile: -.2 }, shut: { brow: .4, rot: 0, smile: .35, shut: 1 }, laugh: { brow: .5, rot: 0, smile: 1 }, deadpan: { brow: -.15, rot: -.1, smile: 0 }, annoyed: { brow: -.5, rot: -.45, smile: 0 },
};
const ceo = (w, h, y, rot) => ({ w, h, y, rot });
const CEYE = { norm: ceo(1, 1, 0, 0), wide: ceo(1.15, 1.3, .06, 0), squint: ceo(1.1, .38, -.08, 0), flat: ceo(1.4, .12, -.1, 0), sad: ceo(1, .85, -.05, .3), happy: ceo(1.2, .5, 0, 0), up: ceo(1, 1.1, .12, 0) };

// timelines from the script
const tl = { F: [], C: [], ff: [], ce: [], hops: [] };
tl.F.push([-1, FPOSE.idle]); tl.C.push([-1, CPOSE.idle]); tl.ff.push([-1, FACE.norm]); tl.ce.push([-1, CEYE.norm]);
LINES.forEach((l, i) => {
  const sp = l.who === 'F';
  const t0 = l.s - (l.lead ?? .12);
  tl.F.push([t0, FPOSE[l.f || (sp ? 'talk' : 'listen')]]);
  tl.C.push([t0, CPOSE[l.c || (sp ? 'listen' : 'talk')]]);
  tl.ff.push([t0, FACE[l.fe || 'norm']]);
  tl.ce.push([t0, CEYE[l.ce || 'norm']]);
  if (l.hop) tl.hops.push(l.s + (l.hopAt || 0));
  (l.extra || []).forEach((e) => { if (e.f) tl.F.push([l.s + e.t, FPOSE[e.f]]); if (e.c) tl.C.push([l.s + e.t, CPOSE[e.c]]); if (e.fe) tl.ff.push([l.s + e.t, FACE[e.fe]]); if (e.ce) tl.ce.push([l.s + e.t, CEYE[e.ce]]); if (e.hop) tl.hops.push(l.s + e.t); });
});
['F', 'C', 'ff', 'ce'].forEach((k) => tl[k].sort((a, b) => a[0] - b[0]));
const blendVec = (arr, t, b = .32) => { let v = arr[0][1]; for (let i = 1; i < arr.length; i++) { const [tk, vk] = arr[i]; if (t < tk) break; const u = sm((t - tk) / b); v = Array.isArray(vk) ? v.map((x, j) => lerp(x, vk[j], u)) : { ...Object.fromEntries(Object.keys(vk).map((k) => [k, lerp(v[k] ?? 0, vk[k], u)])) }; } return v; };
const blendObj = (arr, t, b = .22) => { let v = arr[0][1]; for (let i = 1; i < arr.length; i++) { const [tk, vk] = arr[i]; if (t < tk) break; const u = sm((t - tk) / b); v = Object.fromEntries(Object.keys(vk).map((k) => [k, lerp(v[k] ?? 0, vk[k], u)])); } return v; };
const env = (who, t) => { const m = T.mouth[who], f = t * FPS, i = Math.floor(f), u = f - i; return lerp(m[Math.min(m.length - 1, i)] || 0, m[Math.min(m.length - 1, i + 1)] || 0, u); };
const roundAt = (t) => { for (const l of LINES) if (l.who === 'F' && t >= l.s && t <= l.e) for (const w of l.words || []) if (t >= w.s && t <= w.e) { const ww = w.w.toLowerCase(); const k = Math.floor((t - w.s) / Math.max(.01, w.e - w.s) * ww.length); return 'ouwq'.includes(ww[Math.min(ww.length - 1, k)]) ? 1 : 0; } return 0; };
const blinkAt = (t, seed) => { const per = 3.1 + (seed % 7) * .23, ph = (t + seed * .77) % per; return ph < .13 ? Math.sin(ph / .13 * Math.PI) : 0; };
const holdBlink = T.holdBlinks || [];

function perform(t) {
  const fv = blendVec(tl.F, t), fT = env('F', t), ff = blendObj(tl.ff, t), laugh = (LINES.find((l) => t >= l.s && t <= l.e + .4 && l.fe === 'laugh')) ? 1 : 0;
  const g = (k) => fv[FP_KEYS.indexOf(k)];
  F.root.position.set(FSEAT.x, FSEAT.y, FSEAT.z); F.root.rotation.y = FSEAT.yaw;
  F.hips.rotation.set(0, 0, 0);
  // legs: right knee up (hugged), left extended + swinging
  F.legR.hp.rotation.set(-2.55, 0, .08); F.legR.kn.rotation.set(2.3, 0, 0);
  F.legL.hp.rotation.set(-1.5 + Math.sin(t * 1.9) * .06 * g('swing'), 0, -.1); F.legL.kn.rotation.set(.35 + Math.sin(t * 1.9 + 1) * .2 * g('swing'), 0, 0);
  const breath = Math.sin(t * 2.1) * .012;
  F.torso.rotation.set(g('tx') + breath + laugh * (Math.sin(t * 24) * .04 - .1), g('ty') + noise(t, 1) * .02, g('tz') + noise(t, 2) * .012);
  F.neck.rotation.set(g('nx') + fT * .05 * Math.sin(t * 9) + laugh * -.18, g('ny') + noise(t, 4) * .03, g('nz') + noise(t, 5) * .025);
  const arm = (A, side, pre, amp) => { A.sh.rotation.set(g(pre + 'sx') + noise(t, 7 + side) * .03 - amp * .1, g(pre + 'sy') * side, g(pre + 'sz') * side + noise(t, 9 + side) * .02); A.el.rotation.set(g(pre + 'ex') - amp * .22, g(pre + 'ey') * side, g(pre + 'ez') * side); };
  arm(F.armL, -1, 'l', 0); arm(F.armR, 1, 'r', fT * .6);
  F.phone.visible = g('phone') > .5; F.phoneLight.intensity = g('phone') * 14;
  setFMouth(F, clamp(fT * 1.15), roundAt(t) ? clamp(fT * 1.15) : 0, ff.smile);
  setFBlink(F, Math.max(blinkAt(t, 3), ff.shut || 0));
  F.browL.position.y = .42 + ff.brow * .09 - .04; F.browR.position.y = F.browL.position.y; F.browL.rotation.z = -ff.rot * .5; F.browR.rotation.z = ff.rot * .5;
  // ----- clawd
  const cv = blendVec(tl.C, t), cT = env('C', t), ce = blendObj(tl.ce, t, .16);
  const c = (k) => cv[CP_KEYS.indexOf(k)];
  let hop = 0; for (const h of tl.hops) { const u = (t - h) / .55; if (u > 0 && u < 1) hop = Math.max(hop, Math.sin(u * Math.PI) * (1 - u * .3) * 1.1); }
  C.root.position.set(CSEAT.x, CSEAT.y + hop, CSEAT.z); C.root.rotation.y = c('yaw') + noise(t, 21) * .02;
  const sq = c('sq') * (1 - cT * .055 + Math.sin(t * 15) * cT * .018) * (1 - (hop > 0 ? 0 : 0));
  C.bodyG.scale.set(1 / Math.sqrt(sq), sq, 1 / Math.sqrt(sq)); C.bodyG.rotation.set(c('lean') + noise(t, 22) * .01 - cT * .02, 0, c('tilt') + Math.sin(t * 6.5) * cT * .035);
  C.armL.rotation.set(c('alx') + cT * .5 * Math.sin(t * 11), 0, c('alz') + noise(t, 23) * .03); C.armR.rotation.set(c('arx') + cT * .5 * Math.sin(t * 11 + 2), 0, c('arz') + noise(t, 24) * .03);
  C.legs.forEach((lg, i) => { lg.scale.y = 1 + (hop > 0 ? .12 : 0); });
  const bl = blinkAt(t, 5);
  setCEyes(C, { w: ce.w, h: Math.max(.05, ce.h * (1 - bl)), y: ce.y, rot: ce.rot });
}

// ---------------------------------------------------------------- heads / shot planning
const faceW = (rig) => { rig.root.updateMatrixWorld(true); const v = new THREE.Vector3(); rig.face.getWorldPosition(v); return v; };
let HF, HC;
const cu = (Hd, o) => { const d = (o.d ?? 9), az = o.az ?? 0, el = o.el ?? .04, up = (o.up ?? .75) * d / 11, push = o.push ?? .07;
  const off = (k) => [Hd.x + Math.sin(az) * d * k + (o.dx ?? 0), Hd.y + el * d * k + (o.dy ?? 0), Hd.z + Math.cos(az) * d * k];
  return { p: off(1), p2: off(1 - push), l: [Hd.x + (o.lx ?? 0), Hd.y + up, Hd.z], fov: o.fov ?? 28, focus: o.focus, ap: o.ap ?? .006 }; };
const scrPt = (u, v) => [-22 + 44 * u, 1 + 14 + 13.25 - 26.5 * v, -15.5];
let TPL;
function templates() {
  const MID = HF.clone().add(HC).multiplyScalar(.5);
  const rd = (k) => (rng(strSeed(EP + k))() - .5);
  TPL = {
    F: (r) => cu(HF, { az: .1 + r * .5, d: 13, focus: 'F', up: .75 }),
    Fx: (r) => cu(HF, { az: .2 + r * .3, d: 10, focus: 'F', ap: .008, push: .1, up: .6 }),
    Fp: (r) => cu(HF, { az: 1.0, d: 12.5, el: .08, focus: 'F', ap: .007, up: .6 }),
    Flow: (r) => cu(HF, { az: .3, d: 11, el: -.18, focus: 'F', up: .25, fov: 31 }),
    Fm: (r) => cu(HF, { az: .15 + r * .3, d: 21, focus: 'F', up: 1.6, fov: 30, ap: .005 }),
    C: (r) => cu(HC, { az: -.1 - r * .5, d: 17, focus: 'C', up: .5, el: .02 }),
    Cx: (r) => cu(HC, { az: -.2 - r * .3, d: 12, focus: 'C', ap: .008, push: .1, up: .35 }),
    Clow: (r) => cu(HC, { az: -.25, d: 14, el: -.14, focus: 'C', up: -.1, fov: 32 }),
    Cm: (r) => cu(HC, { az: -.2 - r * .2, d: 24, focus: 'C', up: 1.0, fov: 30, ap: .005 }),
    otsF: (r) => ({ p: [HC.x + 3.4, HC.y - .5, HC.z + 11.5], p2: [HC.x + 3.0, HC.y - .5, HC.z + 10.4], l: [HF.x + 1.0, HF.y + .3, HF.z], fov: 30, focus: 'F', ap: .007 }),
    otsC: (r) => ({ p: [HF.x - 3.4, HF.y - .6, HF.z + 11.5], p2: [HF.x - 3.0, HF.y - .6, HF.z + 10.4], l: [HC.x - 1.0, HC.y + .2, HC.z], fov: 30, focus: 'C', ap: .007 }),
    two: (r) => ({ p: [MID.x + .6, MID.y - .6, MID.z + 25], p2: [MID.x + .3, MID.y - .4, MID.z + 22.5], l: [MID.x, MID.y + 3.2, MID.z], fov: 34, focus: 'mid', ap: .0035 }),
    twoLow: (r) => ({ p: [MID.x - 1.5, MID.y - 2.4, MID.z + 33], p2: [MID.x - 1.0, MID.y - 2.1, MID.z + 30], l: [MID.x, MID.y + 4.0, MID.z], fov: 34, focus: 'mid', ap: .0035 }),
    wide: (r) => ({ p: [MID.x - 1, MID.y + 17, MID.z + 36], p2: [MID.x - .5, MID.y + 15, MID.z + 33], l: [MID.x, MID.y + .5, MID.z - 2], fov: 36, focus: 'mid', ap: .003 }),
    hi: (r) => ({ p: [HF.x + 4, HF.y + 12, HF.z + 10], p2: [HF.x + 3, HF.y + 10.5, HF.z + 9.4], l: [HF.x + .8, HF.y - 1.8, HF.z], fov: 30, focus: 'F', ap: .005 }),
    ext: (r) => ({ p: [MID.x, MID.y + 5, MID.z + 52], p2: [MID.x + 2, MID.y + 12, MID.z + 96], l: [MID.x, MID.y + 7, MID.z - 6], l2: [MID.x, MID.y + 13, MID.z - 14], fov: 36, fov2: 40, focus: 'mid', ap: .002, ease: 'io', mv: [0, 8] }),
    duck: (r) => cu({ x: -28, y: 8.5, z: 9.5 }, { az: .75, d: 30, focus: 'duck', up: -.5, el: .05, fov: 30, ap: .004, push: .12 }),
    scr: (r) => ({ p: [6, 11, 3], p2: [4.5, 12, -1], l: scrPt(.55, .35), fov: 32, focus: 'scrfix', ap: .005 }),
  };
}
let SHOTS = [];
function plan() {
  const rr = rng(strSeed(EP));
  const push = (t0, tpl, extra = {}) => SHOTS.push({ t0, tpl, ...extra });
  let prev = '';
  const pick = (opts) => { const o = opts.filter((x) => x !== prev); const k = o[Math.floor(rr() * o.length)] || opts[0]; prev = k; return k; };
  LINES.forEach((l, i) => {
    const sp = l.who, dur = l.e - l.s, gapB = i ? l.s - LINES[i - 1].e : 0, cutT = i === 0 ? 0 : l.s - .06;
    if (i > 0 && gapB > .85 && !l.noBeat) push(LINES[i - 1].e + .05, pick(['two', 'wide', 'twoLow']));
    const list = Array.isArray(l.shot) ? l.shot : l.shot ? [l.shot] : null;
    const base = sp === 'F' ? ['F', 'Fm', 'Fp', 'otsC', 'Flow'] : ['C', 'Cm', 'otsF', 'Clow'];
    const first = list ? list[0] : i === 0 ? 'Fx' : (dur < 1.3 ? (sp === 'F' ? 'Fx' : 'Cx') : pick(base));
    if (!(i > 0 && gapB > .85 && !l.noBeat && !list)) push(cutT, first, { r: rr() - .5 }); else push(l.s - .06, first, { r: rr() - .5 });
    if (!list || list.length > 1) {
      const second = list ? list[1] : (dur > 3.1 ? pick(sp === 'F' ? ['Fp', 'otsC', 'two', 'hi'] : ['otsF', 'Clow', 'two', 'Cx']) : null);
      if (second) push(l.s + dur * (l.split || .52), second, { r: rr() - .5 });
    }
  });
  const last = LINES[LINES.length - 1];
  if (T.outro !== false) push(last.e + (T.outroDelay ?? .35), 'ext');
  SHOTS.sort((a, b) => a.t0 - b.t0);
  SHOTS = SHOTS.filter((s, i) => i === 0 || s.t0 - SHOTS[i - 1].t0 > .25 || (SHOTS[i - 1] = null, true)).filter(Boolean);
  SHOTS.forEach((s, i) => { s.t1 = i + 1 < SHOTS.length ? SHOTS[i + 1].t0 : DUR; s.spec = TPL[s.tpl](s.r ?? 0); });
}
const shotAt = (t) => { let k = 0; for (let i = 0; i < SHOTS.length; i++) if (t >= SHOTS[i].t0) k = i; return SHOTS[k]; };

function camera(t) {
  const sh = shotAt(t), sp = sh.spec, u0 = (t - sh.t0) / Math.max(.01, sh.t1 - sh.t0);
  let u = sp.mv ? (t - sh.t0 - sp.mv[0]) / sp.mv[1] : u0; u = sp.ease === 'io' || sp.mv ? eio(u) : clamp(u);
  const p = V(sp.p), l = V(sp.l); if (sp.p2) p.lerp(V(sp.p2), u); if (sp.l2) l.lerp(V(sp.l2), u);
  let fov = lerp(sp.fov, sp.fov2 ?? sp.fov, u);
  const hd = .045; p.x += noise(t * .8, 21) * hd; p.y += noise(t * .8, 22) * hd; l.x += noise(t * .6, 23) * hd * .6; l.y += noise(t * .6, 24) * hd * .6;
  if (window.DBGCAM) { const d = window.DBGCAM; p.set(d[0], d[1], d[2]); l.set(d[3], d[4], d[5]); fov = d[6] || 30; }
  cam.position.copy(p); cam.lookAt(l); cam.fov = fov; cam.updateProjectionMatrix();
  let fp; const f = sp.focus;
  if (f === 'F') fp = faceW(F); else if (f === 'C') fp = faceW(C); else if (f === 'mid') fp = faceW(F).add(faceW(C)).multiplyScalar(.5); else if (f === 'scrfix') fp = l.clone(); else if (f === 'duck') fp = V([-27.5, 10, 9.5]); else fp = HF.clone();
  bokeh.uniforms.focus.value = cam.position.distanceTo(fp); bokeh.uniforms.aperture.value = (sp.ap ?? .005) * 0.1; bokeh.uniforms.maxblur.value = sp.mb ?? 0.028;
  return sh;
}

// ---------------------------------------------------------------- captions (series style: Segoe-like semibold, off-white, soft shadow, ~37% height)
const cap = document.getElementById('cap'), cg = cap.getContext('2d');
const CAPFONT = '600 54px Inter, Pretendard';
function wrap(text, maxW) { cg.font = CAPFONT; const ws = text.split(' '), rows = []; let r = ''; for (const w of ws) { const tr = r ? r + ' ' + w : w; if (cg.measureText(tr).width > maxW && r) { rows.push(r); r = w; } else r = tr; } rows.push(r); return rows; }
function captions(t) {
  cg.clearRect(0, 0, W, H); if (T.captions === false) return;  // opt-in: script "captions": false = no burned-in captions
  let ln = null; for (let i = 0; i < LINES.length; i++) { const l = LINES[i], nx = LINES[i + 1]; const st = i === 0 ? 0 : l.s - .06; const end = Math.min(l.e + .5, nx ? nx.s - .05 : 1e9); if (t >= st && t < end) ln = { l, st, end }; }
  if (!ln) return;
  const a = Math.min(ln.st === 0 ? 1 : clamp((t - ln.st) / .13), clamp((ln.end - t) / .13));
  const rows = wrap(ln.l.cap || ln.l.text, 700), lh = 67, y0 = H * .37 - (rows.length - 1) * lh / 2;
  cg.save(); cg.textAlign = 'center'; cg.textBaseline = 'middle'; cg.font = CAPFONT;
  rows.forEach((r, i) => { const y = y0 + i * lh; cg.globalAlpha = a; cg.shadowColor = 'rgba(6,4,22,.85)'; cg.shadowBlur = 16; cg.shadowOffsetY = 2; cg.fillStyle = '#f4efef'; cg.fillText(r, W / 2, y); });
  cg.restore();
}

// ---------------------------------------------------------------- frame
function frame(t) {
  perform(t);
  const fz = (T.freeze || []).find((z) => t >= z[0] && t <= z[1]);
  drawUI({ t, freeze: !!fz, freezeT: fz ? fz[0] : 0, focus: -1 });
  animateSet(S, t);
  const hf = T.hideF ? LINES.find((l) => l.id === T.hideF).e + .15 : 1e9; F.root.visible = t < hf; F.phoneLight.visible = F.root.visible;
  const sh = camera(t);
  finish.uniforms.uTime.value = Math.floor(t * FPS) * 1.618;
  finish.uniforms.uFade.value = (T.end === 'fade') ? clamp((t - (DUR - 1.0)) / 1.0) : 0;
  composer.render(); captions(t);
}

perform(.3); HF = faceW(F); HC = faceW(C); templates(); plan();
window.INFO = () => ({ HF: HF.toArray(), HC: HC.toArray(), shots: SHOTS.map((s) => [s.t0.toFixed(2), s.tpl, s.spec.p.map((x) => +x.toFixed(1)), s.spec.l.map((x) => +x.toFixed(1))]) });
window.DUR = DUR; window.FPS = FPS; window.SHOTS = SHOTS.map((s) => ({ t0: s.t0, tpl: s.tpl }));
window.seek = async (t) => { frame(t); };
if (Q.get('cam')) window.DBGCAM = Q.get('cam').split(',').map(Number);
Promise.all([document.fonts.load('600 54px Inter'), document.fonts.load('600 54px Pretendard', '가'), document.fonts.load('500 15px Pretendard', '가'), document.fonts.load('700 16px Pretendard', '가'), document.fonts.load('500 15px "JetBrains Mono"'), document.fonts.load('700 16px Inter'), document.fonts.load('500 14px Inter')]).then(() => { frame(0); window.READY = true; });
if (!RENDER) {
  const sc = document.getElementById('sc'), tc = document.getElementById('tc'), pp = document.getElementById('pp'); let playing = false, t0 = 0, st = 0;
  const fit = () => { const k = Math.min(innerWidth / W, (innerHeight - 30) / H); document.getElementById('stage').style.transform = `scale(${k})`; }; fit(); addEventListener('resize', fit);
  sc.oninput = () => { st = sc.value * DUR; frame(st); tc.textContent = st.toFixed(2); };
  pp.onclick = () => { playing = !playing; t0 = performance.now() / 1000 - st; pp.textContent = playing ? 'pause' : 'play'; };
  const loop = () => { if (playing) { st = (performance.now() / 1000 - t0) % DUR; frame(st); sc.value = st / DUR; tc.textContent = st.toFixed(2); } requestAnimationFrame(loop); }; loop();
}
