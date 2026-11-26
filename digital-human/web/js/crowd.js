// 100-agent crowd demo: shared LOD2 resources, shared gait pose tables, AI round-robin scheduling, spatial hashing.
import * as THREE from '../vendor/three/three.module.js';
import { GLTFLoader } from '../vendor/three/jsm/loaders/GLTFLoader.js';
import { MeshoptDecoder } from '../vendor/three/jsm/libs/meshopt_decoder.module.js';
import { OrbitControls } from '../vendor/three/jsm/controls/OrbitControls.js';
import * as SkeletonUtils from '../vendor/three/jsm/utils/SkeletonUtils.js';
import { Character } from './character.js';

const N = +(new URLSearchParams(location.search).get('n') || 100);
const AI_BUDGET = 10;               // agents re-planned per frame (round robin)
const CELL = 2.0;                   // spatial hash cell (m)
const PHASES = 32;
const R = 18;                       // plaza radius

const view = document.getElementById('view');
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(view.clientWidth, view.clientHeight);
renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
renderer.toneMapping = THREE.AgXToneMapping;
renderer.shadowMap.enabled = false;
view.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x9aa3ad);
scene.add(new THREE.HemisphereLight(0xdfe8ff, 0x5a5048, 1.6));
const sun = new THREE.DirectionalLight(0xfff2e0, 2.2); sun.position.set(5, 10, 4); scene.add(sun);
const ground = new THREE.Mesh(new THREE.CircleGeometry(R + 4, 64), new THREE.MeshStandardMaterial({ color: 0x77736c, roughness: 0.9 }));
ground.rotation.x = -Math.PI / 2; scene.add(ground);
const camera = new THREE.PerspectiveCamera(45, view.clientWidth / view.clientHeight, 0.1, 200);
camera.position.set(0, 14, 26);
const controls = new OrbitControls(camera, renderer.domElement); controls.target.set(0, 1, 0);

// --- 1. shared gait pose table, evaluated ONCE with the hero DOF system on an offscreen character
const hero = new Character(new THREE.Scene(), { base: '/assets/characters/minjun', quality: 'rt' });
const gltfHero = await new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).loadAsync('/assets/characters/minjun/minjun_lod2.glb');
hero.root.add(gltfHero.scene); hero.model = gltfHero.scene; hero.meta = { correctives: {} };
hero.bones = {}; gltfHero.scene.traverse((o) => { if (o.isBone) hero.bones[o.name] = o; });
hero.restQuat = {}; hero.restPos = {};
for (const [n, b] of Object.entries(hero.bones)) { hero.restQuat[n] = b.quaternion.clone(); hero.restPos[n] = b.position.clone(); }
hero.model.updateMatrixWorld(true);
hero.probeDofs();
const KEY_BONES = Object.keys(hero.bones);
const table = [];   // [phase][boneIndex] -> Quaternion ; root height offset
for (let k = 0; k < PHASES; k++) {
  const ph = (k / PHASES) * Math.PI * 2;
  const L = {};
  for (const [s, sg] of [['L', 1], ['R', -1]]) {
    const p = ph + (s === 'L' ? 0 : Math.PI);
    L[`hip_flexion_${s}`] = 18 * Math.sin(p) + 4;
    L[`knee_flexion_${s}`] = 8 + 30 * Math.max(0, Math.sin(p + 1.9)) ** 1.2;
    L[`ankle_dorsiflexion_${s}`] = 8 * Math.sin(p + 0.6);
    L[`shoulder_flexion_${s}`] = -14 * Math.sin(p);
    L[`shoulder_abduction_${s}`] = -38;
    L[`elbow_flexion_${s}`] = 18 + 6 * Math.max(0, -Math.sin(p));
  }
  L.spine_rotation = 4 * Math.sin(ph); L.pelvis_tilt = 2;
  hero.layers.clear(); hero.setLayer('walk', L); hero.rootOffset.set(0, 0.02 * Math.cos(2 * ph) - 0.01, 0);
  hero.applyPose();
  table.push({ q: KEY_BONES.map((n) => hero.bones[n].quaternion.clone()), rootPos: hero.bones.root.position.clone() });
}

// --- 2. agents: skeleton clones share geometry + materials (GPU skinning per agent)
const proto = gltfHero.scene;
proto.traverse((o) => { if (o.isMesh) { o.material = new THREE.MeshStandardMaterial({ map: null, color: o.material.name.includes('Skin') ? 0xc89c82 : o.material.name.includes('casual') ? 0x4a5a78 : o.material.name.includes('shoe') ? 0x223355 : 0x2a1d16, roughness: 0.7 }); } });
const agents = [];
const tints = [0x4a5a78, 0x7a3b3b, 0x3b6b4a, 0x6b6b6b, 0x8a7a50, 0x2b2b2b, 0x5b4a7a];
for (let i = 0; i < N; i++) {
  const m = SkeletonUtils.clone(proto);
  const bones = {}; m.traverse((o) => { if (o.isBone) bones[o.name] = o; if (o.isMesh) { o.frustumCulled = false; if (o.material.color.getHex() === 0x4a5a78) { o.material = o.material.clone(); o.material.color.setHex(tints[i % tints.length]); } } });
  const a = { m, boneList: KEY_BONES.map((n) => bones[n]), pos: new THREE.Vector3((Math.random() - 0.5) * 2 * R * 0.8, 0, (Math.random() - 0.5) * 2 * R * 0.8),
    vel: new THREE.Vector3(), target: new THREE.Vector3(), speed: 1.1 + Math.random() * 0.5, phase: Math.random(), heading: 0, scale: 0.9 + Math.random() * 0.15,
    personality: Math.random(), visible: true };
  m.scale.setScalar(a.scale);
  scene.add(m); agents.push(a);
  replan(a);
}
function replan(a) {
  const ang = Math.random() * Math.PI * 2, r = Math.sqrt(Math.random()) * R * 0.9;
  a.target.set(Math.cos(ang) * r, 0, Math.sin(ang) * r);
  a.wait = Math.random() < 0.3 ? 1 + Math.random() * 3 : 0;     // some agents pause (idle / chat)
}

// --- 3. spatial hash
const grid = new Map();
const key = (x, z) => `${Math.floor(x / CELL)},${Math.floor(z / CELL)}`;
function rebuildGrid() { grid.clear(); for (const a of agents) { const k = key(a.pos.x, a.pos.z); if (!grid.has(k)) grid.set(k, []); grid.get(k).push(a); } }
function neighbours(a) {
  const out = [], cx = Math.floor(a.pos.x / CELL), cz = Math.floor(a.pos.z / CELL);
  for (let dx = -1; dx <= 1; dx++) for (let dz = -1; dz <= 1; dz++) { const c = grid.get(`${cx + dx},${cz + dz}`); if (c) out.push(...c); }
  return out;
}

const frustum = new THREE.Frustum(), pm = new THREE.Matrix4();
let rr = 0, last = performance.now(), fps = 0, simMs = 0, visibleCount = 0;
const hud = document.getElementById('hud');
function frame() {
  const now = performance.now(), dt = Math.min(0.05, (now - last) / 1000); last = now;
  const t0 = performance.now();
  // AI scheduling: fixed budget per frame
  for (let k = 0; k < AI_BUDGET; k++) { const a = agents[rr++ % agents.length]; if (a.pos.distanceTo(a.target) < 0.6) replan(a); }
  rebuildGrid();
  pm.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse); frustum.setFromProjectionMatrix(pm);
  visibleCount = 0;
  const sph = new THREE.Sphere(new THREE.Vector3(), 1.2);
  for (const a of agents) {
    if (a.wait > 0) { a.wait -= dt; a.vel.multiplyScalar(0.9); }
    else {
      const des = a.target.clone().sub(a.pos); des.y = 0; des.setLength(a.speed);
      for (const b of neighbours(a)) {             // separation (local avoidance)
        if (b === a) continue;
        const d = a.pos.clone().sub(b.pos); const l = d.length();
        if (l < 0.8 && l > 1e-4) des.addScaledVector(d.normalize(), (0.8 - l) * 3);
      }
      a.vel.lerp(des, Math.min(1, dt * 2));
    }
    a.pos.addScaledVector(a.vel, dt);
    const sp = a.vel.length();
    if (sp > 0.05) a.heading = Math.atan2(a.vel.x, a.vel.z);
    // stride frequency from speed -> shared pose table lookup (no per-agent IK)
    a.phase = (a.phase + dt * (0.55 + 0.27 * sp) * (sp > 0.05 ? 1 : 0)) % 1;
    sph.center.copy(a.pos).setY(0.9);
    const dist = camera.position.distanceTo(sph.center);
    a.visible = frustum.intersectsSphere(sph) && dist < 60;   // frustum + distance culling
    a.m.visible = a.visible;
    a.m.position.copy(a.pos); a.m.rotation.y = a.heading;
    if (!a.visible) continue;
    visibleCount++;
    // animation LOD: far agents update their pose every 3rd frame
    if (dist > 25 && (rr + a.personality * 7 | 0) % 3) continue;
    const T = table[Math.floor(a.phase * PHASES) % PHASES];
    const moving = sp > 0.15;
    for (let i = 0; i < a.boneList.length; i++) a.boneList[i].quaternion.copy(moving ? T.q[i] : hero.restQuat[KEY_BONES[i]]);
  }
  simMs = simMs * 0.9 + (performance.now() - t0) * 0.1;
  controls.update();
  renderer.render(scene, camera);
  fps = fps * 0.95 + (1 / Math.max(dt, 1e-3)) * 0.05;
  window.CROWD = { n: agents.length, fps: +fps.toFixed(1), simMs: +simMs.toFixed(2), visible: visibleCount, drawCalls: renderer.info.render.calls, tris: renderer.info.render.triangles };
  hud.textContent = `agents ${N}  visible ${visibleCount}  sim ${simMs.toFixed(2)} ms  fps ${fps.toFixed(1)}  draw ${renderer.info.render.calls}  tris ${(renderer.info.render.triangles / 1e6).toFixed(2)}M`;
  requestAnimationFrame(frame);
}
frame();
