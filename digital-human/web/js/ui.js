// Developer interface. Every control calls the public API (window.DH) so the UI exercises exactly what external programs use.
import * as THREE from '../vendor/three/three.module.js';
import GUI from '../vendor/three/jsm/libs/lil-gui.module.min.js';
import { App, LIGHTS, CAMS } from './app.js';
import { EMOTIONS, EMOTION_KO } from './face.js';
import { GESTURES } from './api.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const app = await new App($('view'), { quality: params.get('q') || 'hq', serverBase: params.get('server') || '' }).init();
const DH = app.api;
window.DH = DH; window.APP = app;
$('loading').remove();
const log = (...a) => { const el = $('log'); el.textContent = (a.map((x) => (typeof x === 'string' ? x : JSON.stringify(x))).join(' ') + '\n' + el.textContent).slice(0, 4000); };
const run = (p) => Promise.resolve(p).then((r) => { if (r !== undefined) log('✓', r); return r; }).catch((e) => log('✗', e.code || '', e.message));

// ------------------------------------------------------------------ GUI
const gui = new GUI({ container: $('gui'), width: 300, title: '제어 패널' });
const st = { camera: 'full', light: 'studio', exposure: 1, autoRotate: false, dof: false, wire: false, debug: false, matView: 'lit',
  emotion: 'neutral', intensity: 70, speed: 1.35, gx: 0, gy: 0, pupil: 0.38, clickWalk: true };

const fCam = gui.addFolder('카메라 / 렌더링');
fCam.add(st, 'camera', Object.keys(CAMS)).name('카메라 프리셋').onChange((v) => app.setCamera(v));
fCam.add(st, 'autoRotate').name('360° 자동 회전').onChange((v) => { app.controls.autoRotate = v; app.controls.autoRotateSpeed = 1.5; });
fCam.add(st, 'dof').name('피사계 심도 (HQ)').onChange((v) => { app.dof = v; });
fCam.add(st, 'light', Object.keys(LIGHTS)).name('조명 환경').onChange((v) => run(app.setLighting(v)));
fCam.add(st, 'exposure', 0.2, 2.5, 0.01).name('노출').onChange((v) => { app.renderer.toneMappingExposure = v; });
fCam.add(st, 'wire').name('와이어프레임').onChange((v) => app.setWireframe(v));
fCam.add(st, 'debug').name('스켈레톤 / COM / 발 접촉').onChange((v) => app.setDebug(v));
fCam.add(st, 'matView', ['lit', 'albedo', 'normal', 'roughness', 'masks']).name('재질 확인').onChange((v) => {
  app.character.materials.DH_Skin.userData.uniforms.uDebug.value = ['lit', 'albedo', 'normal', 'roughness', 'masks'].indexOf(v);
});

const fEmo = gui.addFolder('감정 / 표정');
fEmo.add(st, 'emotion', Object.fromEntries(Object.keys(EMOTIONS).map((k) => [`${EMOTION_KO[k]} (${k})`, k]))).name('감정').onChange(() => run(DH.setEmotion(st.emotion, st.intensity / 100)));
fEmo.add(st, 'intensity', 0, 100, 1).name('강도 %').onChange(() => DH.setEmotion(st.emotion, st.intensity / 100));
const fBs = fEmo.addFolder('Blendshape 슬라이더 (ARKit 52 + FACS)').close();
const bs = {};
for (const n of app.character.morphNames.filter((n) => !n.startsWith('corr_'))) {
  bs[n] = 0;
  fBs.add(bs, n, n === 'mouthClose' ? -1 : 0, 1, 0.01).onChange((v) => DH.setBlendshape(n, v === 0 ? null : v));
}
fBs.add({ reset: () => { for (const n of Object.keys(bs)) { bs[n] = 0; DH.setBlendshape(n, null); } fBs.controllers.forEach((c) => c.updateDisplay()); } }, 'reset').name('전체 초기화');

const fEye = gui.addFolder('눈 / 시선').close();
fEye.add({ user: () => run(DH.lookAt('user')) }, 'user').name('사용자 응시 (눈맞춤)');
fEye.add({ free: () => run(DH.lookAround()) }, 'free').name('자유 시선');
fEye.add({ cup: () => run(DH.lookAt('cup')) }, 'cup').name('컵 바라보기');
fEye.add(st, 'gx', -1, 1, 0.01).name('시선 좌우').onChange(gazePad);
fEye.add(st, 'gy', -1, 1, 0.01).name('시선 상하').onChange(gazePad);
fEye.add({ b: () => DH.blink() }, 'b').name('눈 깜빡임');
fEye.add(app.gaze, 'light', 0, 1, 0.01).name('주변 밝기 (동공)');
function gazePad() {
  const h = app.character.worldPos('head');
  const f = app.body.facingVec(), r = app.body.rightVec();
  DH.lookAt({ x: h.x + f.x * 1.5 - r.x * st.gx, y: h.y + st.gy * 0.9, z: h.z + f.z * 1.5 - r.z * st.gx });
}

const fJ = gui.addFolder('관절 제어 (해부학적 DOF)').close();
const jv = {};
const groups = { '척추/목': /spine|neck|pelvis/, '왼팔': /(clavicle|shoulder|elbow|forearm|wrist)_.*L$|_L$(?<!finger.*)/, '오른팔': /(clavicle|shoulder|elbow|forearm|wrist).*_R$/,
  '손가락 L': /finger.*_L$/, '손가락 R': /finger.*_R$/, '다리': /(hip|knee|ankle|toe)/, '눈': /eye/ };
const used = new Set();
for (const [g, re] of Object.entries(groups)) {
  const f = fJ.addFolder(g).close();
  for (const [k, sp] of Object.entries(app.character.dofs)) {
    if (used.has(k) || !re.test(k)) continue;
    if (g === '왼팔' && !/(clavicle|shoulder|elbow|forearm|wrist).*_L$/.test(k)) continue;
    used.add(k); jv[k] = 0;
    f.add(jv, k, sp.limit[0], sp.limit[1], 1).onChange((v) => DH.setJointRotation(k, v));
  }
}
fJ.add({ r: () => { for (const k of Object.keys(jv)) { jv[k] = 0; DH.setJointRotation(k, null); } fJ.controllersRecursive().forEach((c) => c.updateDisplay()); } }, 'r').name('관절 초기화 (자동 포즈로)');

const fLoc = gui.addFolder('이동 / 행동');
fLoc.add(st, 'clickWalk').name('Shift+클릭으로 이동');
fLoc.add(st, 'speed', 0.3, 7, 0.05).name('이동 속도 m/s');
const A = {
  walk: () => run(DH.walkTo({ x: 0, z: 2.0 })), run: () => run(DH.runTo({ x: 0, z: -2.2 })), sprint: () => run(DH.sprintTo({ x: 3, z: -1.5 })),
  back: () => run(DH.walkBackward(1.5)), side: () => run(DH.sidestep(1.0)), home: () => run(DH.walkTo({ x: 0, z: 0 }, { face: 0 })), stop: () => run(DH.stop()),
  sit: () => run(DH.sit()), stand: () => run(DH.stand()), squat: () => run(DH.squat()), lie: () => run(DH.lieDown()),
  pick: () => run(DH.interactWith('cup', 'pick')), place: () => run(DH.releaseObject()), door: () => run(DH.interactWith('door', 'open')),
  up: () => run(DH.interactWith('stairs', 'climb')), down: () => run(DH.interactWith('stairs', 'descend')),
  greet: () => run(DH.interactWith('user', 'greet')), shake: () => run(DH.interactWith('user', 'handshake')),
  point: () => run(DH.gesture('point', { target: 'door' })), reach: () => run(DH.reachFor('table')),
};
const lbl = { walk: '걷기', run: '뛰기', sprint: '전력 질주', back: '뒤로 걷기', side: '옆으로 걷기', home: '원위치', stop: '정지', sit: '의자에 앉기', stand: '일어서기',
  squat: '쪼그려 앉기', lie: '눕기', pick: '컵 집기', place: '컵 내려놓기', door: '문 열기', up: '계단 오르기', down: '계단 내려가기', greet: '다가가서 손 흔들기',
  shake: '악수하기', point: '문 가리키기', reach: '테이블에 손 뻗기' };
for (const k of Object.keys(A)) fLoc.add(A, k).name(lbl[k]);
const fG = fLoc.addFolder('제스처 / 애니메이션').close();
for (const g of GESTURES.filter((g) => g !== 'point')) fG.add({ [g]: () => run(DH.gesture(g)) }, g);
for (const c of Object.keys(app.clips)) fG.add({ [c]: () => run(DH.playAnimation(c)) }, c).name('clip: ' + c);
fG.add({ blend: () => run(DH.blendAnimation('stretch', 'clap', 0.4)) }, 'blend').name('blend: stretch×clap');

const fAI = gui.addFolder('AI 행동 시스템').close();
const ai = { autonomous: false, fatigue: 0.15, thirst: 0.25, stress: 0.2 };
fAI.add(ai, 'autonomous').name('자동 행동 모드').onChange((v) => { DH.updateBehavior({ autonomous: v }); $('abtn').textContent = v ? 'Auto' : 'Manual'; $('abtn').classList.toggle('on', v); });
for (const k of ['fatigue', 'thirst', 'stress']) fAI.add(ai, k, 0, 1, 0.01).onChange((v) => DH.updateBehavior({ needs: { [k]: v } }));
fAI.add({ g: () => run(DH.setGoal({ type: 'fetch', target: 'cup' })) }, 'g').name('목표: 컵 가져오기');
fAI.add({ g: () => run(DH.setGoal({ type: 'greet' })) }, 'g').name('목표: 인사하기');
fAI.add({ m: () => run(DH.remember(prompt('기억할 내용') || '', { importance: 0.8 })) }, 'm').name('기억 저장 (remember)');
fAI.add({ r: () => run(DH.recall(prompt('검색어') || '')) }, 'r').name('기억 검색 (recall)');
fAI.add({ b: () => run(DH.breathe({ deep: true })) }, 'b').name('심호흡 (breathe)');

$('qbtn').onclick = () => { const q = app.quality === 'hq' ? 'rt' : 'hq'; app.setQuality(q); $('qbtn').textContent = q === 'hq' ? 'HQ' : 'Realtime'; $('qbtn').classList.toggle('on', q === 'hq'); };
$('qbtn').classList.add('on');
$('abtn').onclick = () => { ai.autonomous = !ai.autonomous; fAI.controllers[0].setValue(ai.autonomous); };

// ------------------------------------------------------------------ dialogue
$('speak').onclick = () => run(DH.speak($('say').value, { lang: $('lang').value || undefined, emotion: st.emotion, intensity: st.intensity / 100 }));
$('conv').onclick = () => run(DH.converse($('say').value));
$('listen').onclick = () => run(DH.listen(!DH.listening, { mic: true }));
$('say').addEventListener('keydown', (e) => { if (e.key === 'Enter') $('speak').click(); });

// phoneme / viseme timeline
const tl = $('tl'), tg = tl.getContext('2d');
function drawTimeline() {
  const sp = DH.lastSpeech;
  const W = tl.width = tl.clientWidth * devicePixelRatio, H = tl.height = 54 * devicePixelRatio;
  tg.clearRect(0, 0, W, H);
  tg.font = `${10 * devicePixelRatio}px monospace`;
  if (!sp || !sp.phones) { tg.fillStyle = '#556'; tg.fillText(sp ? sp.method : '음소 타임라인: 말하기를 실행하면 표시됩니다', 8, H / 2); return; }
  const dur = sp.duration || 1, x = (t) => (t / dur) * (W - 10) + 5;
  const e = sp.energy || [];
  tg.fillStyle = '#1d2a36';
  e.forEach((v, i) => { const xx = x(i / 50); tg.fillRect(xx, H - v * H * 0.5, Math.max(1, W / e.length), v * H * 0.5); });
  for (const p of sp.phones) {
    tg.fillStyle = p.viseme === 'PP' ? '#ff8a65' : /aa|E|I|O|U/.test(p.viseme) ? '#7cc4ff' : '#9fd89f';
    tg.fillRect(x(p.start), 4, Math.max(1, x(p.end) - x(p.start) - 1), 12);
    tg.fillStyle = '#cfd6e4';
    if (x(p.end) - x(p.start) > 14 * devicePixelRatio) tg.fillText(p.p, x(p.start) + 2, 28 * devicePixelRatio);
  }
  if (app.lipsync.active) { const t = app.lipsync.time(); tg.fillStyle = '#ffcc00'; tg.fillRect(x(t), 0, 2, H); }
  tg.fillStyle = '#8b93a1'; tg.fillText(`${sp.method}  ·  ${sp.provider || ''}  ·  ${sp.duration}s`, 6, H - 6);
}

// ------------------------------------------------------------------ click to walk
const ray = new THREE.Raycaster(), mouse = new THREE.Vector2();
app.renderer.domElement.addEventListener('pointerdown', (e) => {
  if (!st.clickWalk || !e.shiftKey) return;
  const r = app.renderer.domElement.getBoundingClientRect();
  mouse.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(mouse, app.camera);
  const hit = ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), new THREE.Vector3());
  if (hit) run(DH.moveTo({ x: hit.x, z: hit.z }, { speed: st.speed }));
});

// ------------------------------------------------------------------ HUD refresh
setInterval(() => {
  const p = app.perf();
  $('fps').textContent = p.fps; $('ms').textContent = p.frameMs; $('dc').textContent = p.drawCalls; $('tri').textContent = (p.triangles / 1000).toFixed(0) + 'k';
  $('mem').textContent = p.jsHeapMB ? p.jsHeapMB + ' MB' : `${p.textures} tex`;
  const s = DH.getState();
  const g = app.body.debug.gait || {};
  $('state').textContent = [
    `pos   ${s.body.position.join(', ')}  hdg ${s.body.heading_deg}°`,
    `speed ${s.body.speed} m/s  posture ${s.body.posture}  action ${s.currentAction}`,
    `gait  φ ${(g.phase || 0).toFixed(2)} f ${(g.freq || 0).toFixed(2)}Hz duty ${(g.duty || 0).toFixed(2)} run ${(g.run || 0).toFixed(2)}`,
    `feet  L ${s.body.contacts.L ? 'stance' : 'swing '} R ${s.body.contacts.R ? 'stance' : 'swing '}  slip ${app.body.slip.last.toFixed(3)} m/s`,
    `emo   ${s.face.emotion.name} ${(s.face.emotion.intensity * 100).toFixed(0)}%  pupil ${s.face.pupil}`,
    `eyes  blinks ${s.face.blinks}  saccades ${s.face.saccades}  breath ${app.body.breathRate}/min ×${(app.body.breathMul || 1).toFixed(2)}`,
    `needs fatigue ${s.fatigue.toFixed(2)} thirst ${s.thirst.toFixed(2)} stress ${s.stress.toFixed(2)} focus ${s.focus.toFixed(2)}`,
    `mood  v ${s.mood.valence.toFixed(2)} a ${s.mood.arousal.toFixed(2)}  attention ${s.attention}`,
    `goal  ${s.goal ? s.goal.type : '-'}  memories ${s.memory.length}  autonomous ${s.autonomous}`,
    `ai    ${(app.mind.log.slice(-1)[0] || {}).choice || '-'}`,
  ].join('\n');
}, 250);
(function loop() { drawTimeline(); requestAnimationFrame(loop); })();
DH.lookAt('user');
log('ready — window.DH 로 API 사용 가능. 예) DH.walkTo({x:1,z:1})');
