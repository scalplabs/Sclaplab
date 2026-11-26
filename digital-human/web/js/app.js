// Application bootstrap: renderer, lighting, post-processing, frame orchestration, control bridge.
import * as THREE from '../vendor/three/three.module.js';
import { OrbitControls } from '../vendor/three/jsm/controls/OrbitControls.js';
import { EXRLoader } from '../vendor/three/jsm/loaders/EXRLoader.js';
import { EffectComposer } from '../vendor/three/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from '../vendor/three/jsm/postprocessing/RenderPass.js';
import { GTAOPass } from '../vendor/three/jsm/postprocessing/GTAOPass.js';
import { BokehPass } from '../vendor/three/jsm/postprocessing/BokehPass.js';
import { SMAAPass } from '../vendor/three/jsm/postprocessing/SMAAPass.js';
import { OutputPass } from '../vendor/three/jsm/postprocessing/OutputPass.js';
import { Character } from './character.js';
import { FaceController } from './face.js';
import { GazeController } from './eyes.js';
import { LipSync } from './lipsync.js';
import { Body } from './motion.js';
import { World } from './world.js';
import { Mind } from './ai.js';
import { DigitalHumanAPI, DHError } from './api.js';

export const LIGHTS = {
  studio: { hdri: 'brown_photostudio_02', rot: 0.7, env: 0.5, key: [2.6, [-1.1, 2.2, 1.5], 0xfff2e6], rim: [2.0, [0.9, 2.1, -1.4], 0xe6f0ff], bg: 0x2b2c2f, lux: 0.55 },
  window: { hdri: 'hotel_room', rot: 2.1, env: 0.8, key: [4.0, [-2.0, 1.9, 0.8], 0xf4f7ff], rim: null, bg: 0x3a3836, lux: 0.6 },
  overcast: { hdri: 'kloofendal_48d_partly_cloudy_puresky', rot: 0, env: 1.0, key: [1.2, [0.5, 4, 1], 0xffffff], rim: null, bg: 0x9aa3ad, lux: 0.9 },
  park: { hdri: 'cloudy_vondelpark', rot: 3.5, env: 1.0, key: [1.6, [1.5, 3.5, 1.2], 0xfff4e0], rim: null, bg: 0x7d8a86, lux: 0.85 },
  loft: { hdri: 'photo_studio_loft_hall', rot: 1.2, env: 0.9, key: [2.2, [-1.5, 2.5, 1.2], 0xfff0e0], rim: [1.2, [1, 2, -1.5], 0xffffff], bg: 0x45413c, lux: 0.7 },
  night: { hdri: 'brown_photostudio_02', rot: 0, env: 0.06, key: [1.6, [1.2, 1.9, 0.9], 0xffb070], rim: null, bg: 0x08090b, lux: 0.12 },
};

export const CAMS = {
  face: { pos: [0.0, 1.69, 0.62], tgt: [0, 1.66, 0.02], fov: 22 },
  face34: { pos: [0.36, 1.71, 0.52], tgt: [0, 1.66, 0.02], fov: 22 },
  eyes: { pos: [0.04, 1.71, 0.28], tgt: [0.0, 1.71, 0.03], fov: 18 },
  bust: { pos: [0.3, 1.55, 1.45], tgt: [0, 1.45, 0], fov: 30 },
  full: { pos: [0.0, 1.05, 4.4], tgt: [0, 0.92, 0], fov: 32 },
  side: { pos: [3.6, 1.1, 0.0], tgt: [0, 0.92, 0], fov: 32 },
  back: { pos: [0.0, 1.3, -3.6], tgt: [0, 1.0, 0], fov: 35 },
  wide: { pos: [4.5, 3.2, 6.5], tgt: [0, 0.8, 0], fov: 40 },
};

export class App {
  constructor(container, { quality = 'hq', serverBase = '', assetBase = '/assets' } = {}) {
    this.container = container;
    this.quality = quality;
    this.serverBase = serverBase;
    this.assetBase = assetBase;
    this.clock = new THREE.Clock();
    this.stats = { fps: 0, frameMs: 0, simMs: 0 };
    this.followCam = true;
  }

  async init() {
    const r = this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance', preserveDrawingBuffer: true });
    r.setPixelRatio(Math.min(window.devicePixelRatio, this.quality === 'hq' ? 2 : 1));
    r.setSize(this.container.clientWidth, this.container.clientHeight);
    r.shadowMap.enabled = true;
    r.shadowMap.type = THREE.PCFSoftShadowMap;
    r.toneMapping = THREE.AgXToneMapping;
    r.toneMappingExposure = 0.9;
    r.outputColorSpace = THREE.SRGBColorSpace;
    this.container.appendChild(r.domElement);
    const scene = this.scene = new THREE.Scene();
    const cam = this.camera = new THREE.PerspectiveCamera(30, this.container.clientWidth / this.container.clientHeight, 0.01, 100);
    this.controls = new OrbitControls(cam, r.domElement);
    this.controls.enableDamping = true;
    this.controls.minDistance = 0.12;
    this.setCamera('full');
    this.pmrem = new THREE.PMREMGenerator(r);
    this.keyLight = new THREE.DirectionalLight(0xffffff, 3);
    this.keyLight.castShadow = true;
    this.keyLight.shadow.mapSize.set(this.quality === 'hq' ? 4096 : 2048, this.quality === 'hq' ? 4096 : 2048);
    this.keyLight.shadow.bias = -0.00012;
    this.keyLight.shadow.normalBias = 0.012;
    this.keyLight.shadow.radius = 4;
    const sc = this.keyLight.shadow.camera; sc.left = -1.3; sc.right = 1.3; sc.top = 2.2; sc.bottom = -0.3; sc.near = 0.1; sc.far = 12;
    scene.add(this.keyLight, this.keyLight.target);
    this.rimLight = new THREE.DirectionalLight(0xffffff, 1);
    scene.add(this.rimLight, this.rimLight.target);
    this.world = new World(scene);
    this.character = new Character(scene, { base: `${this.assetBase}/characters/minjun`, quality: this.quality });
    await this.character.load(0);
    this.body = new Body(this.character, this.world);
    this.face = new FaceController(this.character);
    this.gaze = new GazeController(this.character);
    this.lipsync = new LipSync();
    this.clips = await this.loadClips();
    this.api = new DigitalHumanAPI({ character: this.character, body: this.body, face: this.face, gaze: this.gaze, lipsync: this.lipsync,
      world: this.world, clips: this.clips, camera: cam, serverBase: this.serverBase });
    this.mind = new Mind(this.api, this.character.meta.character);
    this.api.mind = this.mind;
    this.mind.s.autonomous = false;      // manual control by default in the dev UI
    await this.setLighting('studio');
    this.setupComposer();
    this.debugObjects();
    window.addEventListener('resize', () => this.resize());
    this.connectBridge();
    this.running = true;
    r.setAnimationLoop(() => this.frame());
    return this;
  }

  async loadClips() {
    const names = await (await fetch(`${this.assetBase}/animations/index.json`)).json();
    const out = {};
    for (const n of names) out[n] = await (await fetch(`${this.assetBase}/animations/${n}.json`)).json();
    return out;
  }

  async setLighting(name) {
    const L = LIGHTS[name];
    if (!L) throw new DHError('INVALID_ARGUMENT', `light preset: ${Object.keys(LIGHTS).join(', ')}`);
    this.lightName = name;
    if (!this._envCache) this._envCache = {};
    if (!this._envCache[L.hdri]) {
      const tex = await new EXRLoader().loadAsync(`${this.assetBase}/hdri/${L.hdri}.exr`);
      tex.mapping = THREE.EquirectangularReflectionMapping;
      this._envCache[L.hdri] = { tex, pm: this.pmrem.fromEquirectangular(tex).texture };
    }
    const E = this._envCache[L.hdri];
    this.scene.environment = E.pm;
    this.scene.environmentIntensity = L.env;
    this.scene.environmentRotation.set(0, L.rot, 0);
    this.scene.background = new THREE.Color(L.bg);
    this.keyLight.intensity = L.key[0];
    this.keyLight.color.set(L.key[2]);
    this.keyOffset = new THREE.Vector3(...L.key[1]);
    this.rimLight.visible = !!L.rim;
    if (L.rim) { this.rimLight.intensity = L.rim[0]; this.rimLight.color.set(L.rim[2]); this.rimOffset = new THREE.Vector3(...L.rim[1]); }
    this.gaze.light = L.lux;
    return name;
  }

  setupComposer() {
    const r = this.renderer;
    const rt = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples: 4 });
    const c = this.composer = new EffectComposer(r, rt);
    c.addPass(new RenderPass(this.scene, this.camera));
    this.gtao = new GTAOPass(this.scene, this.camera, this.container.clientWidth, this.container.clientHeight);
    this.gtao.blendIntensity = 0.9;
    this.gtao.updateGtaoMaterial({ radius: 0.12, distanceExponent: 1.5, thickness: 0.6, scale: 1.0 });
    c.addPass(this.gtao);
    this.bokeh = new BokehPass(this.scene, this.camera, { focus: 0.6, aperture: 0.004, maxblur: 0.006 });
    this.bokeh.enabled = false;
    c.addPass(this.bokeh);
    c.addPass(new OutputPass());
    this.smaa = new SMAAPass(this.container.clientWidth * r.getPixelRatio(), this.container.clientHeight * r.getPixelRatio());
    c.addPass(this.smaa);
    c.setSize(this.container.clientWidth, this.container.clientHeight);
  }

  setQuality(q) {
    this.quality = q;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, q === 'hq' ? 2 : 1));
    this.resize();
    return q;
  }

  setCamera(name) {
    const c = CAMS[name];
    if (!c) throw new DHError('INVALID_ARGUMENT', `camera: ${Object.keys(CAMS).join(', ')}`);
    this.camName = name;
    const base = this.body ? this.body.pos : new THREE.Vector3();
    const q = this.body ? new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), this.body.heading) : new THREE.Quaternion();
    this.camera.position.copy(new THREE.Vector3(...c.pos).applyQuaternion(q).add(base));
    this.controls.target.copy(new THREE.Vector3(...c.tgt).applyQuaternion(q).add(base));
    this.camera.fov = c.fov;
    this.camera.updateProjectionMatrix();
    this.controls.update();
    this._camRel = this.camera.position.clone().sub(base);
    this._tgtRel = this.controls.target.clone().sub(base);
    return name;
  }

  debugObjects() {
    const mk = (c, s = 0.03) => { const m = new THREE.Mesh(new THREE.SphereGeometry(s, 12, 8), new THREE.MeshBasicMaterial({ color: c, depthTest: false })); m.renderOrder = 10; m.visible = false; this.scene.add(m); return m; };
    this.dbg = { com: mk(0xffcc00, 0.035), comGround: mk(0xffcc00, 0.02), footL: mk(0x00ff88), footR: mk(0xff3388), gaze: mk(0x33ccff, 0.02) };
  }
  setDebug(on) { this.debugOn = on; for (const m of Object.values(this.dbg)) m.visible = on; this.character.skeletonHelper.visible = on; }
  setWireframe(on) { for (const m of Object.values(this.character.materials)) m.wireframe = on; this.wireframe = on; }

  resize() {
    const w = this.container.clientWidth, h = this.container.clientHeight;
    this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
    this.composer && this.composer.setSize(w, h);
  }

  // ------------------------------------------------------------------ frame
  frame() {
    const dt = this.fixedDt ?? Math.min(0.05, this.clock.getDelta());
    const t0 = performance.now();
    const ch = this.character, api = this.api, body = this.body;
    this.time = (this.time || 0) + dt;
    this.mind.update(dt);
    // physiology/emotion -> body, eyes, breathing
    const phys = this.face.emotionPhys();
    this.gaze.blinkRate = phys.blink * (1 + this.mind.s.fatigue * 0.6);
    this.gaze.slowBlink = phys.slowBlink + this.mind.s.fatigue * 0.6;
    this.gaze.gazeDown = phys.gazeDown;
    this.gaze.wander = phys.gazeWander;
    this.gaze.arousal = phys.pupil;
    body.breathMul = phys.breath * (1 + this.mind.s.stress * 0.3);
    body.emotionBody = this.face.emotionBody();
    body.fatigue = Math.max(body.fatigue, this.mind.s.fatigue * 0.8);
    if (api._gesture && api._gesture.update(dt)) api._gesture = null;
    api._animTick(dt);
    api._listenTick(this.time);
    body.update(dt);
    const g = this.gaze.update(dt);
    body.headLook = { yaw: g.headYaw * (body.posture === 'lie' ? 0.3 : 1), pitch: g.headPitch };
    // re-apply body layer with updated head look, then FK
    ch.layers.get('body').values.neck_rotation += 0;
    ch.applyPose();
    body.postIK(dt);
    const lids = this.gaze.applyEyes();
    this.lipsync.update();
    const fw = this.face.update(dt, { speech: { active: this.lipsync.active, activity: this.lipsync.activity, weights: this.lipsync.weights }, eyes: lids });
    ch.applyMorphs(fw);
    ch.setPupil(this.gaze.pupilFrac);
    ch.updateEyeUniforms();
    const skin = ch.materials.DH_Skin;
    if (skin) skin.userData.uniforms.uFlush.value = phys.flush + body.exertion * 0.4;
    // lights + camera follow the character
    const p = body.pos;
    this.keyLight.position.copy(p).add(this.keyOffset); this.keyLight.target.position.copy(p).add(new THREE.Vector3(0, 1, 0));
    if (this.rimOffset) { this.rimLight.position.copy(p).add(this.rimOffset); this.rimLight.target.position.copy(p).add(new THREE.Vector3(0, 1.4, 0)); }
    if (this.followCam && this._lastP) { const d = p.clone().sub(this._lastP); this.camera.position.add(d); this.controls.target.add(d); }
    this._lastP = p.clone();
    // distance-based LOD for the hero (detail layers off when small on screen)
    const dist = this.camera.position.distanceTo(ch.worldPos('head'));
    const lod = dist < 3 ? 0 : dist < 8 ? 1 : 2;
    if (lod !== ch.lod) ch.setLOD(lod);
    if (this.debugOn) {
      this.dbg.com.position.copy(body.com); this.dbg.comGround.position.set(body.com.x, 0.005, body.com.z);
      this.dbg.footL.position.copy(body.feet.L.plant); this.dbg.footR.position.copy(body.feet.R.plant);
      this.dbg.footL.material.color.set(body.contacts.L ? 0x00ff88 : 0x555555); this.dbg.footR.material.color.set(body.contacts.R ? 0xff3388 : 0x555555);
      this.dbg.gaze.position.copy(this.gaze.gazePoint);
    }
    this.controls.update();
    const t1 = performance.now();
    if (this.noRender) { /* headless simulation tests */ }
    else if (this.quality === 'hq' && !this.wireframe) {
      this.bokeh.enabled = this.dof;
      if (this.dof) this.bokeh.uniforms.focus.value = this.camera.position.distanceTo(ch.worldPos('head'));
      this.composer.render();
    } else this.renderer.render(this.scene, this.camera);
    const t2 = performance.now();
    this.stats.simMs = this.stats.simMs * 0.9 + (t1 - t0) * 0.1;
    this.stats.frameMs = this.stats.frameMs * 0.9 + (t2 - t0) * 0.1;
    this.stats.fps = this.stats.fps * 0.95 + (1 / Math.max(dt, 1e-3)) * 0.05;
    this.frameCount = (this.frameCount || 0) + 1;
  }

  // Deterministic capture: fixed time step, frames returned as JPEG data URLs (used for the demo video).
  startCapture(fps = 30) {
    this.renderer.setAnimationLoop(null);
    this.fixedDt = 1 / fps;
    this.lipsync.clock = () => this.time;
    this.captured = [];
  }
  async captureFrames(n, { quality = 0.88, every = 1 } = {}) {
    const out = [];
    for (let i = 0; i < n; i++) {
      this.frame();
      if (i % every === 0) out.push(this.renderer.domElement.toDataURL('image/jpeg', quality));
      if (i % 10 === 0) await new Promise((r) => setTimeout(r, 0));   // let promises/timers advance
    }
    return out;
  }
  stopCapture() { this.fixedDt = null; this.lipsync.clock = null; this.renderer.setAnimationLoop(() => this.frame()); }

  perf() {
    const info = this.renderer.info;
    const mem = performance.memory ? { jsHeapMB: +(performance.memory.usedJSHeapSize / 1048576).toFixed(1) } : {};
    return { fps: +this.stats.fps.toFixed(1), frameMs: +this.stats.frameMs.toFixed(2), simMs: +this.stats.simMs.toFixed(2),
      drawCalls: info.render.calls, triangles: info.render.triangles, geometries: info.memory.geometries, textures: info.memory.textures, ...mem };
  }

  // ------------------------------------------------------------------ external control bridge
  connectBridge() {
    if (!this.serverBase && location.protocol === 'file:') return;
    const url = (this.serverBase || location.origin).replace(/^http/, 'ws') + '/ws';
    let ws;
    const open = () => {
      try { ws = new WebSocket(url); } catch (e) { return; }
      ws.onmessage = async (ev) => {
        const msg = JSON.parse(ev.data);
        let reply;
        try {
          const fn = this.api[msg.cmd] || (msg.cmd in this.appCommands() ? this.appCommands()[msg.cmd] : null);
          if (!fn || msg.cmd.startsWith('_')) throw new DHError('UNKNOWN_COMMAND', `unknown command '${msg.cmd}'`);
          const res = await fn.apply(this.api[msg.cmd] ? this.api : this, msg.args || []);
          reply = { id: msg.id, ok: true, result: res === undefined ? null : JSON.parse(JSON.stringify(res, (k, v) => (v && v.isVector3 ? v.toArray() : v))) };
        } catch (e) {
          reply = { id: msg.id, ok: false, error: e.code || 'ERROR', message: e.message };
        }
        ws.send(JSON.stringify(reply));
      };
      ws.onclose = () => setTimeout(open, 2000);
    };
    open();
  }
  appCommands() {
    return { setLighting: (n) => this.setLighting(n), setCamera: (n) => this.setCamera(n), setQuality: (q) => this.setQuality(q),
      perf: () => this.perf(), screenshot: () => this.renderer.domElement.toDataURL('image/jpeg', 0.9) };
  }
}
