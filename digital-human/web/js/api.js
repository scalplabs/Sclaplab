// Public programmatic control API for the digital human. Every method validates input and either returns a
// value or a Promise resolving when the action completes. Errors are thrown as DHError {code, message}.
// Exposed in the page as window.DH and over the WebSocket bridge (server /api/control).
import * as THREE from '../vendor/three/three.module.js';
import { EMOTIONS } from './face.js';
import { SitAction, StandAction, SquatAction, LieAction, ReachAction, GestureAction, DoorAction, SeatedPose } from './motion.js';

export class DHError extends Error {
  constructor(code, message) { super(message); this.code = code; this.name = 'DHError'; }
  toJSON() { return { error: this.code, message: this.message }; }
}
const need = (cond, code, msg) => { if (!cond) throw new DHError(code, msg); };
const isNum = (x) => typeof x === 'number' && Number.isFinite(x);
const vec = (p, name = 'position') => {
  if (Array.isArray(p)) p = { x: p[0], y: p[1], z: p[2] };
  need(p && isNum(p.x) && isNum(p.z), 'INVALID_ARGUMENT', `${name} must be {x, y?, z} numbers (metres)`);
  return new THREE.Vector3(p.x, isNum(p.y) ? p.y : 0, p.z);
};

export const GESTURES = ['wave', 'nod', 'shake', 'shrug', 'open_palms', 'think', 'beat', 'point', 'handshake'];

export class DigitalHumanAPI {
  constructor(ctx) {
    Object.assign(this, ctx);   // character, body, face, gaze, lipsync, world, mind, clips, camera, serverBase
    this.listening = false;
    this.ikTargets = {};
    this.animLayers = {};
    this.events = new EventTarget();
  }

  // -------------------------------------------------------------- transform
  /** setPosition({x,z}) – teleport (m). Returns new position. */
  setPosition(p) {
    const v = vec(p);
    this.body.stop();
    this.body.pos.set(v.x, this.world.groundHeight(v.x, v.z, true), v.z);
    this.body.vel.set(0, 0, 0);
    for (const s of ['L', 'R']) { const F = this.body.feet[s]; F.plant.copy(this.character.root.localToWorld(F.neutral.clone()).add(v.clone().sub(this.character.root.position))); F.planted = true; }
    this.character.root.position.copy(this.body.pos);
    return this.body.pos.toArray();
  }

  /** setRotation(deg) – heading about the vertical axis, degrees (0 = facing +Z). */
  setRotation(deg) {
    need(isNum(deg), 'INVALID_ARGUMENT', 'rotation must be a number in degrees');
    this.body.heading = THREE.MathUtils.degToRad(deg);
    this.body.turnTo = null;
    return deg;
  }

  /** moveTo(pos, {speed 0.1..7, face deg?, backward?, strafe?}) – generic locomotion. Resolves on arrival. */
  moveTo(pos, opts = {}) {
    const v = vec(pos);
    const speed = opts.speed ?? 1.4;
    need(isNum(speed) && speed >= 0.1 && speed <= 7.5, 'OUT_OF_RANGE', 'speed must be 0.1..7.5 m/s');
    need(Math.hypot(v.x, v.z) < 13, 'UNREACHABLE', 'target outside the walkable area (radius 13 m)');
    for (const o of this.world.obstacles) need(Math.hypot(v.x - o.c.x, v.z - o.c.z) > o.r * 0.6, 'UNREACHABLE', `target inside obstacle '${o.id}'`);
    // gaze leads locomotion: look along the path (a point ~3 m ahead, slightly down), then restore attention
    const prevTarget = this.gaze.target, prevMode = this.gaze.mode;
    if (!opts.keepGaze) this.gaze.lookAt(() => {
      const b = this.body, ahead = b.vel.lengthSq() > 0.01 ? b.vel.clone().normalize() : b.facingVec();
      if (opts.backward) ahead.negate();
      return b.pos.clone().addScaledVector(ahead, 3).add(new THREE.Vector3(0, 1.1, 0));
    }, 'idle');
    return this.body.moveTo(v, { speed, face: isNum(opts.face) ? THREE.MathUtils.degToRad(opts.face) : null, backward: !!opts.backward, strafe: !!opts.strafe })
      .then((r) => { if (!opts.keepGaze) this.gaze.lookAt(prevTarget, prevMode); return r; });
  }
  walkTo(pos, opts = {}) { return this.moveTo(pos, { speed: 1.35, ...opts }); }
  runTo(pos, opts = {}) { return this.moveTo(pos, { speed: 3.6, ...opts }); }
  sprintTo(pos, opts = {}) { return this.moveTo(pos, { speed: 6.5, ...opts }); }
  walkBackward(distance = 1.5) {
    const f = this.body.facingVec();
    return this.moveTo(this.body.pos.clone().addScaledVector(f, -distance), { speed: 0.8, backward: true });
  }
  sidestep(distance = 1.0) {
    const r = this.body.rightVec();
    return this.moveTo(this.body.pos.clone().addScaledVector(r, distance), { speed: 0.7, strafe: true });
  }
  /** stop() – decelerate and stand still, cancelling navigation and the current action. */
  stop() {
    this.body.stop();
    if (this.body.action && !(this.body.action instanceof SeatedPose)) { this.body.action.cancel?.(); this.body.action = null; }
    this.body.handTargets = { L: null, R: null };
    this.body.gestureLayer = {};
    return true;
  }

  // -------------------------------------------------------------- posture
  /** sit(chairId='chair') – walk to the chair, turn, sit. */
  async sit(chairId = 'chair') {
    const c = this.world.objects[chairId];
    need(c && c.type === 'chair', 'NOT_FOUND', `no chair '${chairId}'`);
    if (this.body.posture === 'sit') return { ok: true, posture: 'sit' };
    if (this.body.posture !== 'stand') await this.stand();
    const ap = c.approach();
    await this.walkTo(ap, { face: THREE.MathUtils.radToDeg(c.facing()) });
    await this._waitTurn();
    const r = await this.body.startAction(new SitAction(this.body, { pos: c.seatPoint(), heading: c.facing() }));
    this.body.action = new SeatedPose(this.body, c);
    return r;
  }
  /** stand() – rise from any posture. */
  stand() {
    if (this.body.posture === 'stand' && !(this.body.action instanceof SquatAction)) return Promise.resolve({ ok: true, posture: 'stand' });
    return this.body.startAction(new StandAction(this.body));
  }
  squat(depth = 0.42) { need(isNum(depth) && depth > 0.1 && depth <= 0.55, 'OUT_OF_RANGE', 'depth 0.1..0.55 m'); return this.body.startAction(new SquatAction(this.body, depth)); }
  async lieDown(bedId = 'mat') {
    const m = this.world.objects[bedId];
    need(m, 'NOT_FOUND', `no surface '${bedId}'`);
    if (this.body.posture !== 'stand') await this.stand();
    await this.walkTo(m.approach(), { face: THREE.MathUtils.radToDeg(m.facing()) });
    await this._waitTurn();
    return this.body.startAction(new LieAction(this.body, m.surfaceHeight || 0));
  }
  _waitTurn() { return new Promise((r) => { const chk = () => (this.body.turnTo == null ? r() : setTimeout(chk, 50)); chk(); }); }

  // -------------------------------------------------------------- gaze / eyes / breathing
  /** lookAt(target, {mode}) – target: 'user' | objectId | {x,y,z} | null (free gaze). mode: fixate|contact|pursue|idle */
  lookAt(target, { mode } = {}) {
    let t = null;
    if (target === 'user') { t = () => this.userPosition(true); mode = mode || 'contact'; }
    else if (typeof target === 'string') {
      const o = this.world.objects[target];
      need(o, 'NOT_FOUND', `unknown object '${target}'`);
      t = o.object3D; mode = mode || 'fixate';
    } else if (target) { t = vec(target, 'target'); mode = mode || 'fixate'; }
    need(!mode || ['fixate', 'contact', 'pursue', 'idle', 'avert'].includes(mode), 'INVALID_ARGUMENT', 'mode must be fixate|contact|pursue|idle|avert');
    this.gaze.lookAt(t, t ? mode : 'idle');
    this.mind.s.attention = target === null ? null : typeof target === 'string' ? target : 'point';
    return { target: target ?? null, mode: t ? mode : 'idle' };
  }
  lookAround() { this.gaze.lookAt(null, 'idle'); this.mind.s.attention = null; return true; }
  /** blink({double}) – trigger a blink now. */
  blink({ double = false } = {}) { this.gaze.blink(); if (double) setTimeout(() => this.gaze.blink(), 320); return true; }
  /** breathe({rate 6..40 /min, depth 0.3..2.5, deep}) – override breathing (null resets to automatic). */
  breathe({ rate = null, depth = null, deep = false } = {}) {
    if (rate !== null) need(isNum(rate) && rate >= 6 && rate <= 40, 'OUT_OF_RANGE', 'rate 6..40 breaths/min');
    if (depth !== null) need(isNum(depth) && depth >= 0.3 && depth <= 2.5, 'OUT_OF_RANGE', 'depth 0.3..2.5');
    this.body.breathRate = rate ?? 14;
    this.body.deepBreath = deep ? 2.2 : depth ?? 1;
    if (deep) setTimeout(() => { this.body.deepBreath = 1; }, 6000);
    return { rate: this.body.breathRate, depth: this.body.deepBreath };
  }

  // -------------------------------------------------------------- speech
  /** speak(text, {lang 'ko'|'en', emotion, intensity, provider}) – TTS + phoneme lip-sync. Resolves when done. */
  async speak(text, opts = {}) {
    need(typeof text === 'string' && text.trim().length > 0, 'INVALID_ARGUMENT', 'text must be a non-empty string');
    need(text.length <= 600, 'OUT_OF_RANGE', 'max 600 characters per utterance');
    if (opts.emotion) this.setEmotion(opts.emotion, opts.intensity ?? 0.6);
    this.listening = false;
    let speech = null;
    try {
      const r = await fetch(this.serverBase + '/api/tts', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, lang: opts.lang, emotion: opts.emotion || this.face.emotion.name, intensity: opts.intensity ?? this.face.emotion.intensity, provider: opts.provider }) });
      speech = await r.json();
      if (!r.ok) throw new DHError('TTS_FAILED', speech.detail || speech.error);
    } catch (e) {
      // offline fallback: browser speech synthesis, estimated timing (APPROXIMATE)
      this.lastSpeech = { text, method: 'browser_speechSynthesis_estimated (approximate)', error: String(e.message || e) };
      this.gaze.talking = true;
      await this.lipsync.speakFallback(text, opts.lang || (/[가-힣]/.test(text) ? 'ko' : 'en'));
      this.gaze.talking = false;
      return this.lastSpeech;
    }
    this.lastSpeech = speech;
    this.mind.s.conversation.push({ role: 'assistant', text, t: Date.now() });
    this.gaze.talking = true;
    if (this.mind.s.perception.userPresent) this.lookAt('user', { mode: 'contact' });
    this.events.dispatchEvent(new CustomEvent('speech', { detail: speech }));
    await this.lipsync.play(speech, {
      baseUrl: this.serverBase,
      onWord: (w) => {
        // prosody-driven co-speech behaviour: beats on stressed/long words, occasional nods
        if ((w.stress >= 2 || (w.end - w.start) > 0.35) && Math.random() < 0.55 && !this.body.action) this.gesture('beat', { side: Math.random() < 0.7 ? 'R' : 'L' });
        else if (Math.random() < 0.12) this.face.expression = { browInnerUp: 0.25 };
        setTimeout(() => { this.face.expression = {}; }, 250);
      },
    });
    this.gaze.talking = false;
    return { ok: true, duration: speech.duration, method: speech.method, phones: speech.phones.length };
  }

  /** listen(on=true, {mic}) – attentive listening: eye contact, back-channel nods; optional microphone VAD. */
  async listen(on = true, { mic = false } = {}) {
    this.listening = !!on;
    if (on) {
      this.lookAt('user', { mode: 'contact' });
      this.setEmotion('focus', 0.25);
      if (mic && !this._mic) {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const ctx = this.lipsync.ctx || new AudioContext();
        this.lipsync.ctx = ctx;
        const an = ctx.createAnalyser(); ctx.createMediaStreamSource(stream).connect(an);
        this._mic = { an, buf: new Float32Array(an.fftSize), speaking: false, lastVoice: 0 };
      }
    } else {
      this.setEmotion('neutral', 0);
    }
    return { listening: this.listening };
  }
  _listenTick(t) {
    if (!this.listening) return;
    let voiced = false;
    if (this._mic) {
      this._mic.an.getFloatTimeDomainData(this._mic.buf);
      const rms = Math.sqrt(this._mic.buf.reduce((s, x) => s + x * x, 0) / this._mic.buf.length);
      voiced = rms > 0.02;
      if (voiced) this._mic.lastVoice = t;
      // end of a user phrase -> back-channel nod
      if (!voiced && this._mic.speaking && t - this._mic.lastVoice > 0.35 && Math.random() < 0.7) this.gesture('nod');
      this._mic.speaking = voiced;
    } else if (!this._nextNod || t > this._nextNod) {
      if (this._nextNod) this.gesture('nod');
      this._nextNod = t + 3 + Math.random() * 5;
    }
  }

  /** converse(text) – full loop: LLM intent (server) -> emotion, gesture, action, speech, memory. */
  async converse(text) {
    need(typeof text === 'string' && text.trim(), 'INVALID_ARGUMENT', 'text required');
    this.mind.s.conversation.push({ role: 'user', text, t: Date.now() });
    this.setEmotion('focus', 0.3);
    this.gesture('think');
    const ctx = { name: this.mind.s.name, age: this.mind.s.age, personality: this.mind.s.personality,
      state: { mood: this.mind.s.mood, fatigue: +this.mind.s.fatigue.toFixed(2), emotion: this.face.emotion },
      objects: Object.keys(this.world.objects), memories: this.recall(text).map((m) => m.text),
      history: this.mind.s.conversation.slice(-12) };
    const r = await fetch(this.serverBase + '/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, context: ctx }) });
    const intent = await r.json();
    if (intent.remember) this.remember(intent.remember, { tags: ['user'], importance: 0.8 });
    this.setEmotion(intent.emotion || 'neutral', intent.intensity ?? 0.5);
    if (intent.gesture && intent.gesture !== 'none') this.gesture(intent.gesture);
    const speaking = this.speak(intent.reply, { lang: intent.language, emotion: intent.emotion, intensity: intent.intensity });
    if (intent.action && intent.action !== 'none') {
      const map = { walk_to: () => this.walkTo(this.userPosition().clone().lerp(this.body.pos, 0.6)), sit: () => this.sit(), stand: () => this.stand(),
        wave: () => this.gesture('wave'), look_at: () => this.lookAt(intent.action_target || 'user'), pick_up: () => this.interactWith(intent.action_target || 'cup', 'pick'),
        handshake: () => this.gesture('handshake'), open_door: () => this.interactWith('door', 'open') };
      map[intent.action] && speaking.then(() => map[intent.action]());
    }
    await speaking;
    return intent;
  }

  // -------------------------------------------------------------- face
  /** setEmotion(name, intensity 0..1 | 0..100%) – blends continuously. */
  setEmotion(name, intensity = 1, opts = {}) {
    need(EMOTIONS[name], 'INVALID_ARGUMENT', `emotion must be one of ${Object.keys(EMOTIONS).join(', ')}`);
    if (intensity > 1) intensity = intensity / 100;
    need(isNum(intensity) && intensity >= 0 && intensity <= 1, 'OUT_OF_RANGE', 'intensity 0..1 (or 0..100)');
    this.face.setEmotion(name, intensity, opts);
    this.mind.s.emotion = { name, intensity };
    return { name, intensity };
  }
  /** setExpression({arkitName: 0..1, ...}) – additive named expression on top of emotion (null/{} clears). */
  setExpression(weights) {
    if (!weights) { this.face.expression = {}; return {}; }
    for (const [k, v] of Object.entries(weights)) {
      need(this.character.morphTargets.has(k), 'NOT_FOUND', `unknown blendshape '${k}'`);
      need(isNum(v) && v >= -1 && v <= 1, 'OUT_OF_RANGE', `${k} must be 0..1`);
    }
    this.face.expression = { ...weights };
    return this.face.expression;
  }
  /** setBlendshape(name, weight|null) – hard override of one morph target (null releases). */
  setBlendshape(name, w) {
    need(this.character.morphTargets.has(name), 'NOT_FOUND', `unknown blendshape '${name}'`);
    if (w === null) { delete this.character.manualMorph[name]; return null; }
    need(isNum(w) && w >= (name === 'mouthClose' ? -1 : 0) && w <= 1, 'OUT_OF_RANGE', 'weight 0..1');
    this.character.manualMorph[name] = w;
    return w;
  }

  // -------------------------------------------------------------- skeleton
  /** setJointRotation(joint, value|null)
   *   anatomical: setJointRotation('elbow_flexion_L', 90)    (degrees, clamped to human range, see joints())
   *   raw bone:   setJointRotation('upperarm01.L', {x,y,z})  (local Euler degrees relative to bind pose) */
  setJointRotation(joint, value) {
    if (this.character.dofs[joint]) {
      this.character.manualDof = this.character.manualDof || {};
      if (value === null) { delete this.character.manualDof[joint]; return null; }
      need(isNum(value), 'INVALID_ARGUMENT', 'anatomical joint value must be degrees');
      const [lo, hi] = this.character.dofs[joint].limit;
      const v = Math.max(lo, Math.min(hi, value));
      this.character.manualDof[joint] = v;
      return { joint, value: v, clamped: v !== value, limit: [lo, hi] };
    }
    need(this.character.bone(joint), 'NOT_FOUND', `unknown joint '${joint}' (see joints())`);
    if (value === null) { delete this.character.manualJoint[joint]; return null; }
    need(value && isNum(value.x ?? 0) && isNum(value.y ?? 0) && isNum(value.z ?? 0), 'INVALID_ARGUMENT', '{x,y,z} degrees');
    this.character.manualJoint[joint] = { x: value.x || 0, y: value.y || 0, z: value.z || 0 };
    return this.character.manualJoint[joint];
  }
  joints() { return { anatomical: Object.fromEntries(Object.entries(this.character.dofs).map(([k, v]) => [k, v.limit])), bones: Object.keys(this.character.bones) }; }
  /** setJointTarget(effector, pos|null, {weight}) – IK target. effector: hand_L|hand_R|foot_L|foot_R|head */
  setJointTarget(effector, pos, { weight = 1 } = {}) {
    need(['hand_L', 'hand_R', 'foot_L', 'foot_R', 'head'].includes(effector), 'INVALID_ARGUMENT', 'effector: hand_L|hand_R|foot_L|foot_R|head');
    if (pos === null) {
      if (effector.startsWith('hand')) this.body.handTargets[effector.slice(-1)] = null;
      if (effector === 'head') this.lookAround();
      delete this.ikTargets[effector];
      return null;
    }
    const v = vec(pos);
    need(isNum(weight) && weight >= 0 && weight <= 1, 'OUT_OF_RANGE', 'weight 0..1');
    if (effector.startsWith('hand')) {
      const s = effector.slice(-1);
      const dist = v.distanceTo(this.character.worldPos(`upperarm01.${s}`));
      this.body.handTargets[s] = { pos: v, weight };
      this.ikTargets[effector] = v;
      return { effector, reachable: dist <= this.character.armLength, distance: +dist.toFixed(3) };
    }
    if (effector === 'head') { this.lookAt(v); return { effector }; }
    const s = effector.slice(-1);
    this.body.feet[s].plant.copy(v);
    return { effector };
  }

  // -------------------------------------------------------------- animation clips
  /** playAnimation(name, {loop, speed, weight}) – keyframed DOF clips from assets/animations. */
  playAnimation(name, { loop = false, speed = 1, weight = 1 } = {}) {
    need(this.clips[name], 'NOT_FOUND', `unknown clip '${name}'. available: ${Object.keys(this.clips).join(', ')}`);
    need(isNum(speed) && speed > 0 && speed <= 4, 'OUT_OF_RANGE', 'speed 0..4');
    return new Promise((resolve) => { this.animLayers[name] = { clip: this.clips[name], t: 0, loop, speed, weight, resolve }; });
  }
  /** blendAnimation(a, b, w) – plays two clips with weights (1-w, w) e.g. walk-style variants or emotions */
  blendAnimation(a, b, w = 0.5, opts = {}) {
    need(this.clips[a] && this.clips[b], 'NOT_FOUND', 'unknown clip');
    need(isNum(w) && w >= 0 && w <= 1, 'OUT_OF_RANGE', 'w 0..1');
    return Promise.all([this.playAnimation(a, { ...opts, weight: 1 - w }), this.playAnimation(b, { ...opts, weight: w })]);
  }
  stopAnimation(name) { if (name) delete this.animLayers[name]; else this.animLayers = {}; }
  _animTick(dt) {
    const out = {};
    for (const [n, L] of Object.entries(this.animLayers)) {
      L.t += dt * L.speed;
      const c = L.clip;
      if (L.t > c.duration) { if (L.loop) L.t %= c.duration; else { delete this.animLayers[n]; L.resolve({ ok: true, clip: n }); continue; } }
      const fadeIn = Math.min(1, L.t / 0.25), fadeOut = L.loop ? 1 : Math.min(1, (c.duration - L.t) / 0.25);
      for (const [dof, keys] of Object.entries(c.tracks)) out[dof] = (out[dof] || 0) + sampleKeys(keys, L.t) * L.weight * fadeIn * fadeOut;
    }
    this.character.setLayer('clips', out, 1);
  }

  // -------------------------------------------------------------- gestures / manipulation
  /** gesture(name, {side, target}) – wave|nod|shake|shrug|open_palms|think|beat|point|handshake */
  gesture(name, opts = {}) {
    need(GESTURES.includes(name), 'INVALID_ARGUMENT', `gesture must be one of ${GESTURES.join(', ')}`);
    if (name === 'point' && opts.target) opts.target = typeof opts.target === 'string' ? this.world.objects[opts.target].object3D.getWorldPosition(new THREE.Vector3()) : vec(opts.target);
    const g = new GestureAction(this.body, name, opts);
    // gestures run in parallel with locomotion/posture: separate slot
    if (this._gesture) this._gesture.cancel();
    this._gesture = g;
    if (name === 'point' && opts.target) this.lookAt(opts.target);
    return g.promise;
  }
  /** reachFor(target, {side}) – IK reach to a point or object without grasping. */
  async reachFor(target, { side = 'R' } = {}) {
    const getPos = this._targetGetter(target);
    await this._approachIfFar(getPos(), 0.55);
    return this.body.startAction(new ReachAction(this.body, side, getPos, { mode: 'reach' }));
  }
  /** grabObject(id, {side}) – walk to, reach, grasp and hold an item. */
  async grabObject(id, { side = 'R' } = {}) {
    const o = this.world.objects[id];
    need(o && o.type === 'item', 'NOT_FOUND', `no graspable item '${id}'`);
    need(!this.body.held[side], 'BUSY', `${side} hand already holds an object`);
    const getPos = () => o.object3D.getWorldPosition(new THREE.Vector3());
    await this._approachIfFar(getPos(), 0.5);
    const r = await this.body.startAction(new ReachAction(this.body, side, getPos, { mode: 'grab', object: o.object3D }));
    return { ...r, holding: id };
  }
  /** releaseObject({side, at}) – place held object at a position (or table surface in front). */
  async releaseObject({ side = 'R', at = null } = {}) {
    const obj = this.body.held[side];
    need(obj, 'NOT_HOLDING', `${side} hand is empty`);
    let p = at ? vec(at) : null;
    if (!p) { const t = this.world.objects.table; p = t.object3D.localToWorld(new THREE.Vector3(-0.2, 0.81, 0.1)); }
    await this._approachIfFar(p, 0.5);
    return this.body.startAction(new ReachAction(this.body, side, () => p, { mode: 'release', place: p }));
  }
  /** interactWith(id, verb) – high-level: chair:sit, cup:pick|drink|place, door:open, stairs:climb|descend, mat:lie, user:greet|handshake */
  async interactWith(id, verb = null) {
    const o = id === 'user' ? { type: 'user' } : this.world.objects[id];
    need(o, 'NOT_FOUND', `unknown object '${id}'`);
    switch (o.type) {
      case 'chair': return this.sit(id);
      case 'bed': return this.lieDown(id);
      case 'item': {
        if (verb === 'place') return this.releaseObject();
        const r = await this.grabObject(id);
        if (verb === 'drink' || verb === null) await this.playAnimation('drink');
        return r;
      }
      case 'door': {
        await this.walkTo(o.approach(), { face: THREE.MathUtils.radToDeg(o.facing()) });
        await this._waitTurn();
        return this.body.startAction(new DoorAction(this.body, o));
      }
      case 'stairs': {
        const from = verb === 'descend' ? o.top() : o.bottom(), to = verb === 'descend' ? o.bottom() : o.top();
        await this.walkTo(from);
        return this.walkTo(to, { speed: 0.9 });
      }
      case 'user': {
        await this.walkTo(this.userPosition().clone().lerp(this.body.pos, 0.55));
        return this.gesture(verb === 'handshake' ? 'handshake' : 'wave');
      }
      default: throw new DHError('UNSUPPORTED', `no interaction for '${o.type}'`);
    }
  }
  async _approachIfFar(p, dist) {
    const d = new THREE.Vector3(p.x - this.body.pos.x, 0, p.z - this.body.pos.z);
    if (d.length() > dist + 0.15) {
      const stand = new THREE.Vector3(p.x, 0, p.z).addScaledVector(d.normalize(), -dist);
      await this.walkTo(stand);
    }
    this.body.turnTo = Math.atan2(p.x - this.body.pos.x, p.z - this.body.pos.z);
    await this._waitTurn();
  }
  _targetGetter(t) {
    if (typeof t === 'string') { const o = this.world.objects[t]; need(o, 'NOT_FOUND', `unknown object '${t}'`); return () => o.object3D.getWorldPosition(new THREE.Vector3()); }
    const v = vec(t, 'target');
    return () => v;
  }

  // -------------------------------------------------------------- memory / goals / behaviour
  /** remember(text, {tags, importance 0..1}) */
  remember(text, opts = {}) { need(typeof text === 'string' && text, 'INVALID_ARGUMENT', 'text required'); return this.mind.remember(text, opts); }
  /** recall(query, k=5) -> [{t, kind, text, tags, importance}] */
  recall(query, k = 5) { need(typeof query === 'string', 'INVALID_ARGUMENT', 'query string required'); return this.mind.recall(query, k); }
  /** setGoal({type: go_to|sit|fetch|open_door|greet, target, priority}) – queued if one is active */
  setGoal(goal) {
    need(goal && ['go_to', 'sit', 'fetch', 'open_door', 'greet'].includes(goal.type), 'INVALID_ARGUMENT', 'goal.type: go_to|sit|fetch|open_door|greet');
    if (goal.type === 'go_to') vec(goal.target, 'goal.target');
    if (this.mind.s.goal) this.mind.s.goalQueue.push(goal); else this.mind.s.goal = goal;
    return { active: this.mind.s.goal, queued: this.mind.s.goalQueue.length };
  }
  /** updateBehavior({autonomous, needs:{fatigue,hunger,thirst,stress,focus}, personality, decideEvery}) */
  updateBehavior(p = {}) {
    const s = this.mind.s;
    if ('autonomous' in p) s.autonomous = !!p.autonomous;
    for (const k of ['fatigue', 'hunger', 'thirst', 'stress', 'focus']) {
      if (p.needs && k in p.needs) { need(isNum(p.needs[k]) && p.needs[k] >= 0 && p.needs[k] <= 1, 'OUT_OF_RANGE', `${k} 0..1`); s[k] = p.needs[k]; }
    }
    if (p.personality) Object.assign(s.personality, p.personality);
    if (p.decideEvery) this.mind.decideEvery = p.decideEvery;
    if (p.relationship) Object.assign(s.relationships.user, p.relationship);
    return this.getState();
  }
  getState() {
    const s = this.mind.snapshot();
    s.body = { position: this.body.pos.toArray().map((v) => +v.toFixed(3)), heading_deg: +THREE.MathUtils.radToDeg(this.body.heading).toFixed(1),
      speed: +this.body.vel.length().toFixed(3), posture: this.body.posture, contacts: this.body.contacts,
      com: this.body.com ? this.body.com.toArray().map((v) => +v.toFixed(3)) : null,
      holding: Object.fromEntries(Object.entries(this.body.held).map(([k, v]) => [k, v ? v.name : null])) };
    s.face = { emotion: this.face.emotion, pupil: +(this.gaze.pupilFrac || 0).toFixed(3), blinks: this.gaze.stats.blinks, saccades: this.gaze.stats.saccades };
    s.speech = { speaking: this.lipsync.active, listening: this.listening, last: this.lastSpeech ? { method: this.lastSpeech.method, duration: this.lastSpeech.duration } : null };
    return s;
  }

  userPosition(eyes = false) {
    const c = this.camera.position.clone();
    if (!eyes) c.y = 0;
    return c;
  }
}

export function sampleKeys(keys, t) {
  if (t <= keys[0][0]) return keys[0][1];
  for (let i = 1; i < keys.length; i++) {
    if (t <= keys[i][0]) {
      const [t0, v0] = keys[i - 1], [t1, v1] = keys[i];
      const x = (t - t0) / (t1 - t0), s = x * x * (3 - 2 * x);
      return v0 + (v1 - v0) * s;
    }
  }
  return keys[keys.length - 1][1];
}
