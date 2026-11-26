// Body motion system: base pose, idle/physiology layer, locomotion with foot planting + IK, actions.
import * as THREE from '../vendor/three/three.module.js';
import { twoBoneIK, setBoneWorldQuaternion, Spring, organic } from './ik.js';

const D2R = Math.PI / 180, R2D = 180 / Math.PI;
const UP = new THREE.Vector3(0, 1, 0);
const lerp = THREE.MathUtils.lerp, clamp = THREE.MathUtils.clamp;
const smooth = (x) => { x = clamp(x, 0, 1); return x * x * (3 - 2 * x); };

// gait parameters as a function of speed (m/s)
function gaitParams(v) {
  const run = smooth((v - 1.9) / 0.6);             // walk->run transition ~2.2 m/s
  const freq = lerp(0.55 + 0.27 * v, 0.85 + 0.15 * v, run);   // strides per second
  return {
    run, freq: Math.max(0.5, freq),
    duty: lerp(0.62 - 0.02 * v, clamp(0.42 - 0.02 * v, 0.28, 0.42), run),
    clearance: lerp(0.07, 0.16 + 0.015 * v, run),
    bob: lerp(0.022, 0.045, run), sway: lerp(0.022, 0.012, run),
    pelvisYaw: lerp(5, 9, run), lean: lerp(2 + 1.5 * v, 6 + 1.6 * v, run),
    armSwing: lerp(10 + 6 * v, 26 + 5 * v, run), elbow: lerp(12 + 4 * v, 80, run), crouch: lerp(0.01 * v, 0.06 + 0.006 * v, run),
    stanceWidth: lerp(0.085, 0.045, run),
  };
}

export class Body {
  constructor(character, world) {
    this.ch = character;
    this.world = world;
    this.pos = new THREE.Vector3();
    this.heading = 0;                         // radians, 0 = facing +Z
    this.vel = new THREE.Vector3();
    this.desiredVel = new THREE.Vector3();
    this.faceDir = null;                      // optional facing override (radians) e.g. backward walking
    this.phase = 0;
    this.t = 0;
    this.speedCap = 1.4;
    this.goal = null;                         // {pos, speed, faceAtEnd, onArrive, tol}
    this.action = null;                       // current action object
    this.queue = [];
    this.posture = 'stand';                   // stand | sit | squat | lie
    this.pelvisOffset = new THREE.Vector3();
    this.feet = {};
    this.handTargets = { L: null, R: null };
    this.grip = { L: 0, R: 0 };
    this.held = { L: null, R: null };
    this.fatigue = 0;
    this.exertion = 0;                        // 0..1 from locomotion -> breathing rate
    this.breathRate = 14;                     // breaths/min
    this.breathPhase = 0;
    this.emotionBody = {};
    this.gestureLayer = {};
    this.headLook = { yaw: 0, pitch: 0 };
    this.weightShift = new Spring(0, 1.2);
    this.nextShift = 4 + Math.random() * 6;
    this.shiftTarget = 0;
    this.slip = { max: 0, last: 0 };
    this.contacts = { L: true, R: true };
    this.debug = {};
    this._init();
  }

  _init() {
    const ch = this.ch;
    const inv = ch.root.quaternion.clone().invert();
    for (const s of ['L', 'R']) {
      const f = ch.worldPos(`foot.${s}`);
      this.feet[s] = {
        neutral: new THREE.Vector3(f.x, 0, f.z),       // character-space ankle ground projection
        plant: new THREE.Vector3(f.x, 0, f.z), planted: true, liftPos: new THREE.Vector3(f.x, 0, f.z), heading: 0,
        bindQ: ch.bone(`foot.${s}`).getWorldQuaternion(new THREE.Quaternion()).premultiply(inv),
      };
    }
    this.ankleH = ch.ankleHeight;
    this.hipH = ch.hipHeight;
  }

  // ------------------------------------------------------------------ commands (used by API / AI)
  moveTo(pos, { speed = 1.4, face = null, tol = 0.08, backward = false, strafe = false } = {}) {
    return new Promise((resolve) => {
      if (this.posture !== 'stand') this.queue.push(() => this.moveTo(pos, { speed, face, tol, backward, strafe }).then(resolve));
      this.goal = { pos: new THREE.Vector3(pos.x, 0, pos.z), speed, face, tol, backward, strafe, resolve };
      if (this.posture !== 'stand' && !this.action) this.startAction(new StandAction(this));
    });
  }
  stop() {
    if (this.goal) { this.goal.resolve && this.goal.resolve({ stopped: true }); this.goal = null; }
    this.desiredVel.set(0, 0, 0);
  }
  startAction(a) {
    if (this.action && this.action.cancel) this.action.cancel();
    this.action = a;
    return a.promise;
  }

  facingVec(h = this.heading) { return new THREE.Vector3(Math.sin(h), 0, Math.cos(h)); }
  rightVec(h = this.heading) { return new THREE.Vector3(-Math.cos(h), 0, Math.sin(h)); }   // character's right

  // ------------------------------------------------------------------ per-frame update (before FK)
  update(dt) {
    this.t += dt;
    const ch = this.ch;
    // --- navigation / steering
    let target = new THREE.Vector3();
    if (this.goal) {
      const g = this.goal;
      const to = g.pos.clone().sub(this.pos); to.y = 0;
      const d = to.length();
      if (d < g.tol && this.vel.length() < 0.25) {
        const r = g.resolve; this.goal = null;
        if (g.face !== null && g.face !== undefined) this.turnTo = g.face;
        r && r({ arrived: true, pos: this.pos.clone() });
      } else {
        // arrival: v = min(vmax, sqrt(2 a d))
        const vmax = Math.min(g.speed, Math.sqrt(2 * 1.2 * Math.max(0, d - g.tol * 0.5)) + 0.05);
        // slow down while the heading error is large (turn first, then accelerate) unless strafing/backing
        const want = Math.atan2(to.x, to.z) + (g.backward ? Math.PI : 0);
        const err = Math.abs(angDiff(want, this.heading));
        const turnScale = g.strafe ? 1 : Math.max(0.15, Math.cos(Math.min(err, Math.PI / 2)) ** 2);
        target = to.normalize().multiplyScalar(vmax * turnScale);
        target.add(this.world.avoid(this.pos, target, 0.35, g.pos));   // obstacle steering
      }
    }
    this.desiredVel.copy(target);
    // acceleration limits (inertia)
    const accel = this.vel.length() > 2.2 ? 4.5 : 1.8;
    const dv = this.desiredVel.clone().sub(this.vel);
    const maxdv = (dv.dot(this.vel) < 0 ? accel * 1.6 : accel) * dt;
    if (dv.length() > maxdv) dv.setLength(maxdv);
    this.vel.add(dv);
    const speed = this.vel.length();
    // facing: turn toward velocity (or keep facing for backward / strafe), limited turn rate
    let wantH = this.heading;
    if (this.goal && speed > 0.05) {
      const vh = Math.atan2(this.vel.x, this.vel.z);
      wantH = this.goal.backward ? vh + Math.PI : this.goal.strafe ? this.heading : vh;
    } else if (this.turnTo !== undefined && this.turnTo !== null) {
      wantH = this.turnTo;
      if (Math.abs(angDiff(wantH, this.heading)) < 0.02) this.turnTo = null;
    }
    const turnRate = speed > 2 ? 2.2 : 3.2;  // rad/s
    const dh = clamp(angDiff(wantH, this.heading), -turnRate * dt, turnRate * dt);
    this.heading += dh;
    this.turnVel = dh / Math.max(dt, 1e-4);
    // integrate root
    this.pos.addScaledVector(this.vel, dt);
    this.pos.y = this.world.groundHeight(this.pos.x, this.pos.z, true);
    ch.root.position.copy(this.pos);
    ch.root.quaternion.setFromAxisAngle(UP, this.heading);
    ch.root.updateMatrixWorld(true);
    this.exertion = lerp(this.exertion, clamp(speed / 6, 0, 1), dt * 0.3);
    this.fatigue = clamp(this.fatigue + dt * (speed > 3 ? 0.004 : -0.0005), 0, 1);

    // --- actions
    if (this.action) {
      const done = this.action.update(dt);
      if (done) { this.action = null; const nx = this.queue.shift(); nx && nx(); }
    }

    // --- compose layers
    const L = {};
    this._basePose(L);
    this._idle(L, dt, speed);
    this._locomotion(L, dt, speed);
    if (this.action && this.action.pose) this.action.pose(L);
    for (const [k, v] of Object.entries(this.emotionBody)) L[k] = (L[k] || 0) + v * (this.posture === 'lie' ? 0 : 1);
    for (const [k, v] of Object.entries(this.gestureLayer)) L[k] = (L[k] || 0) + v;
    L.neck_rotation = (L.neck_rotation || 0) + this.headLook.yaw;
    L.neck_flexion = (L.neck_flexion || 0) - this.headLook.pitch;
    ch.setLayer('body', L, 1);
    ch.rootOffset.copy(this.pelvisOffset);
  }

  _basePose(L) {
    // relaxed standing: arms hang (A-pose rest -> adduct), slight elbow flexion, palms toward thighs, fingers curled
    for (const s of ['L', 'R']) {
      L[`shoulder_abduction_${s}`] = -38;
      L[`shoulder_flexion_${s}`] = 3;
      L[`elbow_flexion_${s}`] = 12;
      L[`forearm_pronation_${s}`] = 0;
      L[`wrist_flexion_${s}`] = 4;
      for (let f = 2; f <= 5; f++) {
        const g = this.grip[s];
        L[`finger${f}_1_flexion_${s}`] = lerp(12 + f * 3, 80, g);
        L[`finger${f}_2_flexion_${s}`] = lerp(22 + f * 3, 95, g);
        L[`finger${f}_3_flexion_${s}`] = lerp(14, 60, g);
      }
      L[`finger1_2_flexion_${s}`] = lerp(10, 40, this.grip[s]);
      L[`finger1_3_flexion_${s}`] = lerp(8, 35, this.grip[s]);
    }
  }

  _idle(L, dt, speed) {
    const t = this.t;
    // breathing: rate from emotion, exertion, fatigue; inhale/exhale asymmetric (I:E ~ 1:1.5)
    const rate = this.breathRate * (this.breathMul || 1) * (1 + 1.6 * this.exertion) / 60;
    this.breathPhase = (this.breathPhase + dt * rate) % 1;
    const ph = this.breathPhase;
    const br = ph < 0.4 ? Math.sin((ph / 0.4) * Math.PI / 2) : Math.cos(((ph - 0.4) / 0.6) * Math.PI / 2);
    const depth = (0.6 + 0.8 * this.exertion) * (this.deepBreath || 1);
    this.breathValue = br * depth;
    L.spine_flexion = (L.spine_flexion || 0) - 1.4 * br * depth;       // thoracic extension on inhale
    for (const s of ['L', 'R']) L[`clavicle_elevation_${s}`] = (L[`clavicle_elevation_${s}`] || 0) + 1.6 * br * depth;
    L.neck_flexion = (L.neck_flexion || 0) + 0.8 * br * depth;
    // posture: fatigue slump
    L.spine_flexion += 6 * this.fatigue;
    if (speed < 0.15 && this.posture === 'stand' && !(this.action && this.action.locksFeet)) {
      // weight shift between legs (occasional) + continuous postural sway (multi-scale, non-repeating)
      this.nextShift -= dt;
      if (this.nextShift <= 0) { this.shiftTarget = (Math.random() - 0.5) * 2 * (0.5 + this.fatigue); this.nextShift = 5 + Math.random() * 12; }
      const ws = this.weightShift.update(this.shiftTarget, dt);
      const sway = organic(t * 0.5, 11) * 0.006, swayZ = organic(t * 0.4, 12) * 0.008;
      const right = this.rightVec();
      this.pelvisOffset.set(0, -Math.abs(ws) * 0.008, 0)
        .addScaledVector(new THREE.Vector3(-1, 0, 0), ws * 0.035 + sway).add(new THREE.Vector3(0, 0, swayZ));
      L.spine_lateral = (L.spine_lateral || 0) + ws * 2.5;
      L.pelvis_tilt = (L.pelvis_tilt || 0) + organic(t, 13) * 1.2;
      L.neck_rotation = (L.neck_rotation || 0) + organic(t * 0.6, 14) * 2.0;
      L.neck_lateral = (L.neck_lateral || 0) - ws * 2 + organic(t * 0.5, 15) * 1.5;
      for (const s of ['L', 'R']) {   // finger micro-movements
        L[`finger2_1_flexion_${s}`] += organic(t * 1.3, s === 'L' ? 21 : 22) * 4;
        L[`finger4_1_flexion_${s}`] += organic(t * 1.1, s === 'L' ? 23 : 24) * 4;
        L[`shoulder_flexion_${s}`] += organic(t * 0.7, s === 'L' ? 25 : 26) * 1.5;
      }
      this.debug.weightShift = ws;
      void right;
    }
  }

  _locomotion(L, dt, speed) {
    if (this.posture !== 'stand' || (this.action && this.action.locksFeet)) return;
    const gp = gaitParams(Math.max(speed, 0.3));
    const moving = speed > 0.08 || this._settling;
    const fwd = this.facingVec(), right = this.rightVec();
    // gait phase
    if (moving) this.phase = (this.phase + dt * gp.freq) % 1;
    const localV = new THREE.Vector3(this.vel.dot(right) * -1, 0, this.vel.dot(fwd));   // x=left, z=fwd
    const back = this.goal && this.goal.backward ? -1 : 1;
    const gait = smooth(speed / 0.5);
    this.debug.gait = { speed, freq: gp.freq, duty: gp.duty, phase: this.phase, run: gp.run };
    // pelvis: bob (2/stride), sway, rotation
    const bobPh = Math.cos(4 * Math.PI * (this.phase - gp.duty * 0.5));
    const bob = (gp.run > 0.5 ? -1 : 1) * gp.bob * bobPh * gait - gp.crouch * gait;
    const swayAmt = gp.sway * Math.sin(2 * Math.PI * this.phase) * gait;
    if (moving) {
      this.pelvisOffset.set(swayAmt, bob - 0.01 * gait, 0);
      // stairs / slopes: pelvis follows the average foot ground height above root height
      const gh = (this.world.groundHeight(this.feet.L.plant.x, this.feet.L.plant.z) + this.world.groundHeight(this.feet.R.plant.x, this.feet.R.plant.z)) / 2;
      this.pelvisOffset.y += gh - this.pos.y;
    }
    const swing = Math.sin(2 * Math.PI * this.phase) * gait * back;
    L.pelvis_tilt = (L.pelvis_tilt || 0) + gp.lean * gait * 0.4 * back;
    L.spine_flexion = (L.spine_flexion || 0) + gp.lean * gait * back + clamp(this.vel.length() - this.desiredVel.length(), -1, 1) * -3;
    L.spine_rotation = (L.spine_rotation || 0) - gp.pelvisYaw * 0.8 * swing;     // thorax counter-rotates
    const turnLean = clamp(this.turnVel * speed * 2.5, -8, 8);
    L.spine_lateral = (L.spine_lateral || 0) + turnLean;                                  // lean into turns
    L.neck_lateral = (L.neck_lateral || 0) - turnLean * 0.85;                             // keep head upright (vestibular)
    L.neck_rotation = (L.neck_rotation || 0) + gp.pelvisYaw * 0.5 * swing;        // head stabilisation
    for (const s of ['L', 'R']) {
      const sgn = s === 'L' ? 1 : -1;
      // arm swings opposite to the ipsilateral leg (left leg forward at phase 0.25 -> left arm back)
      L[`shoulder_flexion_${s}`] += -sgn * gp.armSwing * swing;
      L[`elbow_flexion_${s}`] += (gp.elbow - 12) * gait + 6 * Math.max(0, sgn * swing) * gait;
      L[`shoulder_abduction_${s}`] += 4 * gp.run * gait;
    }
    // foot targets
    for (const s of ['L', 'R']) this._footStep(s, gp, dt, moving, speed);
    // settle feet back to neutral when stopping
    if (!moving) this._settle(dt);
  }

  _footStep(s, gp, dt, moving, speed) {
    const F = this.feet[s];
    const off = s === 'L' ? 0 : 0.5;
    const fp = (this.phase + off) % 1;
    const inStance = fp < gp.duty;
    const fwd = this.facingVec();
    const neutralW = this.ch.root.localToWorld(F.neutral.clone().setY(0));
    const latOff = neutralW.clone().sub(this.pos); latOff.y = 0;
    latOff.setLength(Math.max(gp.stanceWidth, 0.04));
    if (!moving) return;
    if (inStance) {
      if (!F.planted) {         // touchdown -> lock in world
        F.planted = true;
        F.plant.y = this.world.groundHeight(F.plant.x, F.plant.z);
        F.heading = this.heading;
      }
      F.stanceT = fp / gp.duty;
    } else {
      if (F.planted) { F.planted = false; F.liftPos.copy(F.plant); }
      const sw = (fp - gp.duty) / (1 - gp.duty);          // 0..1 swing progress
      // predicted landing: root position at the middle of the next stance + lateral offset
      const tToMid = ((1 - fp) + gp.duty * 0.5) / gp.freq;
      const land = this.pos.clone().addScaledVector(this.vel, tToMid).add(latOff);
      land.y = this.world.groundHeight(land.x, land.z);
      const m = sw * sw * (3 - 2 * sw);
      F.plant.lerpVectors(F.liftPos, land, m);
      const apex = Math.max(F.liftPos.y, land.y) + gp.clearance;
      F.plant.y = lerp(F.liftPos.y, land.y, m) + (apex - Math.max(F.liftPos.y, land.y)) * Math.sin(Math.PI * sw) + Math.max(0, (Math.max(F.liftPos.y, land.y) - lerp(F.liftPos.y, land.y, m))) * Math.sin(Math.PI * sw);
      F.swingT = sw;
      F.heading = lerp(F.heading, this.heading, Math.min(1, dt * 8));
    }
    this.contacts[s] = inStance;
    void speed; void fwd;
  }

  _settle(dt) {
    for (const s of ['L', 'R']) {
      const F = this.feet[s];
      const n = this.ch.root.localToWorld(F.neutral.clone());
      n.y = this.world.groundHeight(n.x, n.z);
      if (F.plant.distanceTo(n) > 0.04 && !this._stepping) {
        this._stepping = { s, from: F.plant.clone(), to: n, t: 0 };
        F.planted = false; this.contacts[s] = false;
      }
    }
    if (this._stepping) {
      const st = this._stepping;
      st.t += dt / 0.45;
      const F = this.feet[st.s];
      const m = smooth(st.t);
      F.plant.lerpVectors(st.from, st.to, m);
      F.plant.y = lerp(st.from.y, st.to.y, m) + 0.05 * Math.sin(Math.PI * Math.min(1, st.t));
      F.heading = this.heading;
      if (st.t >= 1) { this._stepping = null; F.planted = true; this.contacts[st.s] = true; }
    } else {
      for (const s of ['L', 'R']) this.feet[s].heading = lerp(this.feet[s].heading, this.heading, Math.min(1, dt * 3));
    }
  }

  // ------------------------------------------------------------------ IK (after FK)
  postIK(dt) {
    const ch = this.ch;
    if (this.posture !== 'lie') {
      for (const s of ['L', 'R']) {
        const F = this.feet[s];
        const gp = gaitParams(Math.max(this.vel.length(), 0.3));
        // foot roll: heel strike (toe up) -> flat -> heel off (toe-off)
        let pitch = 0, ankleLift = 0;
        if (this.vel.length() > 0.08 && this.posture === 'stand') {
          if (F.planted) {
            const st = F.stanceT || 0;
            pitch = st < 0.15 ? lerp(12, 0, st / 0.15) : st > 0.7 ? -lerp(0, 28 + 10 * gp.run, (st - 0.7) / 0.3) : 0;
            if (st > 0.7) ankleLift = Math.sin(-pitch * D2R) * 0.13;   // heel rises around the ball of the foot
          } else {
            const sw = F.swingT || 0;
            pitch = sw < 0.3 ? lerp(-30, 0, sw / 0.3) : lerp(0, 12, (sw - 0.3) / 0.7);
          }
        }
        const target = F.plant.clone();
        target.y += this.ankleH + ankleLift;
        const qYaw = new THREE.Quaternion().setFromAxisAngle(UP, F.heading);
        const right = new THREE.Vector3(1, 0, 0).applyQuaternion(qYaw);
        const qPitch = new THREE.Quaternion().setFromAxisAngle(right, -pitch * D2R);
        const footQ = qPitch.multiply(qYaw).multiply(F.bindQ);
        const knee = ch.worldPos(`lowerleg01.${s}`);
        const pole = knee.clone().add(this.facingVec(F.heading).multiplyScalar(0.6));
        const r = twoBoneIK(ch.bone(`upperleg01.${s}`), ch.bone(`lowerleg01.${s}`), ch.bone(`foot.${s}`), target, pole,
                            { keepEndRot: footQ });
        if (pitch < -5) {   // toes extend at push-off
          for (let k = 1; k <= 5; k++) {
            const tb = ch.bone(`toe${k}-1.${s}`);
            if (tb) { const ax = ch.dofAxes[`toe_flexion_${s}`][k - 1]; if (ax) tb.quaternion.multiply(new THREE.Quaternion().setFromAxisAngle(ax.axis, pitch * 0.9 * D2R)); }
          }
        }
        // slip metric: planted foot world motion between frames
        if (F.planted && F._last) this.slip.last = Math.max(this.slip.last * 0.98, F.plant.distanceTo(F._last) / Math.max(dt, 1e-4));
        F._last = F.planted ? F.plant.clone() : null;
        this.debug[`ik_${s}`] = r.dist;
      }
    }
    // hands
    for (const s of ['L', 'R']) {
      const ht = this.handTargets[s];
      if (!ht) continue;
      const w = ht.weight ?? 1;
      const sh = ch.worldPos(`upperarm01.${s}`);
      const pole = sh.clone().add(new THREE.Vector3(s === 'L' ? 0.4 : -0.4, -0.5, -0.3).applyQuaternion(ch.root.quaternion));
      twoBoneIK(ch.bone(`upperarm01.${s}`), ch.bone(`lowerarm01.${s}`), ch.bone(`wrist.${s}`), ht.pos, pole,
                { weight: w, keepEndRot: ht.rot || null });
    }
    // held objects follow the hand
    for (const s of ['L', 'R']) {
      const o = this.held[s];
      if (o) {
        const hb = ch.bone(`wrist.${s}`);
        hb.updateMatrixWorld(true);
        o.matrixAutoUpdate = false;
        o.matrix.multiplyMatrices(hb.matrixWorld, o.userData.gripOffset);
        o.matrix.decompose(o.position, o.quaternion, o.scale);
        o.matrixWorldNeedsUpdate = true;
      }
    }
    this.com = this.centerOfMass();
  }

  // Segment-mass COM (Winter, 2009 anthropometric fractions)
  centerOfMass() {
    const ch = this.ch;
    const segs = [['head', 0.081], ['spine01', 0.216], ['spine03', 0.139], ['root', 0.142],
      ['upperarm02.L', 0.028], ['upperarm02.R', 0.028], ['lowerarm02.L', 0.022], ['lowerarm02.R', 0.022],
      ['upperleg02.L', 0.1], ['upperleg02.R', 0.1], ['lowerleg02.L', 0.0465], ['lowerleg02.R', 0.0465], ['foot.L', 0.0145], ['foot.R', 0.0145]];
    const c = new THREE.Vector3(); let m = 0;
    for (const [b, w] of segs) { const bb = ch.bone(b); if (bb) { c.addScaledVector(bb.getWorldPosition(new THREE.Vector3()), w); m += w; } }
    return c.divideScalar(m);
  }

  // hold / release
  attach(s, obj) {
    const hb = this.ch.bone(`wrist.${s}`);
    hb.updateMatrixWorld(true);
    obj.updateMatrixWorld(true);
    obj.userData.gripOffset = new THREE.Matrix4().copy(hb.matrixWorld).invert().multiply(obj.matrixWorld);
    this.held[s] = obj;
  }
  detach(s, worldPos) {
    const o = this.held[s];
    if (!o) return null;
    this.held[s] = null;
    o.matrixAutoUpdate = true;
    if (worldPos) o.position.copy(worldPos);
    o.updateMatrixWorld(true);
    return o;
  }
}

function angDiff(a, b) { let d = a - b; while (d > Math.PI) d -= 2 * Math.PI; while (d < -Math.PI) d += 2 * Math.PI; return d; }

// =================================================================== ACTIONS
class Action {
  constructor(body, dur = 1) {
    this.b = body; this.t = 0; this.dur = dur; this.done = false;
    this.promise = new Promise((r) => (this._resolve = r));
  }
  finish(v = { ok: true }) { this.done = true; this._resolve(v); return true; }
  cancel() { this._resolve({ ok: false, cancelled: true }); }
}

export class SitAction extends Action {
  constructor(body, seat) {  // seat: {pos: Vector3 seat point (top of cushion), heading}
    super(body, 1.9);
    this.seat = seat; this.locksFeet = true;
    this.startPos = body.pos.clone();
    // feet: settle to a natural shoulder-width stance under the knees before lowering
    this.footFrom = {}; this.footTo = {};
    for (const s of ['L', 'R']) {
      const F = body.feet[s];
      this.footFrom[s] = F.plant.clone();
      const n = body.ch.root.localToWorld(F.neutral.clone().add(new THREE.Vector3(s === 'L' ? 0.04 : -0.04, 0, 0.06)));
      n.y = body.world.groundHeight(n.x, n.z);
      this.footTo[s] = n;
    }
  }
  update(dt) {
    const b = this.b;
    this.t += dt;
    for (const s of ['L', 'R']) {
      const k = smooth((this.t - (s === 'L' ? 0 : 0.2)) / 0.3);
      const F = b.feet[s];
      F.plant.lerpVectors(this.footFrom[s], this.footTo[s], k);
      F.plant.y += 0.05 * Math.sin(Math.PI * k);
      F.heading = b.heading;
    }
    this.t2 = Math.max(0, this.t - 0.4);
    const x = smooth(this.t2 / (this.dur - 0.4));
    // pelvis: lean forward early, descend and move back onto the seat
    const seatLocal = b.ch.root.worldToLocal(this.seat.pos.clone());
    const hipToSeat = this.seat.pos.y + 0.09 - b.hipH;
    this.drop = lerp(0, hipToSeat, smooth((this.t2 / (this.dur - 0.4) - 0.15) / 0.85));
    b.pelvisOffset.set(0, this.drop, lerp(0, seatLocal.z + 0.06, x));
    this.x = x;
    if (this.t >= this.dur) { b.posture = 'sit'; return this.finish({ ok: true, posture: 'sit' }); }
    return false;
  }
  pose(L) {
    const x = this.x || 0, bell = Math.sin(Math.PI * Math.min(1, x));
    L.spine_flexion = (L.spine_flexion || 0) + 22 * bell;
    for (const s of ['L', 'R']) { L[`shoulder_flexion_${s}`] += 20 * x; L[`elbow_flexion_${s}`] += 30 * x; }
  }
}

export class SeatedPose {   // persistent posture layer while sitting: hands rest on the thighs (IK)
  constructor(body, seat) { this.b = body; this.seat = seat; this.locksFeet = true; this.t = 0; }
  update(dt) {
    this.t += dt;
    const b = this.b, w = smooth(this.t / 0.6);
    for (const s of ['L', 'R']) {
      const hip = b.ch.worldPos(`upperleg01.${s}`), knee = b.ch.worldPos(`lowerleg01.${s}`);
      const p = hip.clone().lerp(knee, 0.62).add(new THREE.Vector3(0, 0.075, 0));
      b.handTargets[s] = { pos: p, weight: w };
    }
    return false;
  }
  cancel() { this.b.handTargets = { L: null, R: null }; }
  pose(L) { for (const s of ['L', 'R']) { L[`wrist_flexion_${s}`] += 12; L[`forearm_pronation_${s}`] = (L[`forearm_pronation_${s}`] || 0) + 25; } L.spine_flexion += 3; }
}

export class StandAction extends Action {
  constructor(body) { super(body, 1.5); this.locksFeet = true; this.from = body.pelvisOffset.clone(); this.fromPosture = body.posture; body.handTargets = { L: null, R: null }; }
  update(dt) {
    const b = this.b;
    this.t += dt;
    const p = this.t / this.dur;
    this.x = p;
    // shift COM over the feet (trunk flexion) before rising
    const rise = smooth((p - 0.25) / 0.75);
    b.pelvisOffset.set(lerp(this.from.x, 0, rise), lerp(this.from.y, 0, rise), lerp(this.from.z, 0, smooth(p / 0.6)));
    if (this.t >= this.dur) {
      b.posture = 'stand'; b.pelvisOffset.set(0, 0, 0);
      if (b.lieQ) b.lieQ = null;
      return this.finish({ ok: true, posture: 'stand' });
    }
    return false;
  }
  pose(L) { const bell = Math.sin(Math.PI * clamp(this.x || 0, 0, 1)); L.spine_flexion = (L.spine_flexion || 0) + 30 * bell; for (const s of ['L', 'R']) L[`shoulder_flexion_${s}`] += 25 * bell; }
}

export class SquatAction extends Action {
  constructor(body, depth = 0.42, hold = true) { super(body, 1.1); this.depth = depth; this.hold = hold; this.locksFeet = true; }
  update(dt) {
    this.t += dt;
    this.x = smooth(this.t / this.dur);
    this.b.pelvisOffset.set(0, -this.depth * this.x, -0.08 * this.x);
    if (this.t >= this.dur && !this.reported) { this.reported = true; this.b.posture = 'squat'; this._resolve({ ok: true, posture: 'squat' }); }
    return false;   // stays until StandAction replaces it
  }
  pose(L) { const x = this.x || 0; L.spine_flexion += 28 * x; L.neck_flexion -= 15 * x; for (const s of ['L', 'R']) { L[`shoulder_flexion_${s}`] += 35 * x; L[`elbow_flexion_${s}`] += 25 * x; } }
}

export class LieAction extends Action {
  // lie supine on the floor (or a bed surface height)
  constructor(body, surfaceY = 0) { super(body, 3.2); this.surfaceY = surfaceY; this.locksFeet = true; }
  update(dt) {
    const b = this.b;
    this.t += dt;
    const p = this.t / this.dur;
    this.p = p;
    const down = smooth(p / 0.55), recline = smooth((p - 0.45) / 0.55);
    b.pelvisOffset.set(0, lerp(0, this.surfaceY + 0.11 - b.hipH, down), lerp(0, -0.25, recline));
    b.lieRecline = recline;
    if (recline > 0.02) b.posture = 'lie';
    if (this.t >= this.dur && !this.reported) { this.reported = true; this._resolve({ ok: true, posture: 'lie' }); }
    return false;
  }
  pose(L) {
    const p = this.p || 0, down = smooth(p / 0.55), r = smooth((p - 0.45) / 0.55);
    L.pelvis_tilt = (L.pelvis_tilt || 0) - 88 * r;     // whole body rotates back about the pelvis
    for (const s of ['L', 'R']) {
      L[`hip_flexion_${s}`] = (L[`hip_flexion_${s}`] || 0) + lerp(85 * down, 3, r);
      L[`knee_flexion_${s}`] = (L[`knee_flexion_${s}`] || 0) + lerp(100 * down, 8, r);
      L[`shoulder_abduction_${s}`] += 10 * r;
    }
    L.spine_flexion += 25 * down * (1 - r);
    L.neck_flexion += 10 * r;
  }
  cancel() { this.b.lieRecline = 0; super.cancel(); }
}

export class ReachAction extends Action {
  // reach a world point with a hand; optional grab / release
  constructor(body, side, getPos, { mode = 'reach', object = null, place = null, dur = 1.0, hold = 0.25 } = {}) {
    super(body, dur * 2 + hold);
    Object.assign(this, { side, getPos, mode, object, place, reachDur: dur, hold });
  }
  update(dt) {
    const b = this.b, s = this.side;
    this.t += dt;
    const tgt = this.getPos();
    const shoulder = b.ch.worldPos(`upperarm01.${s}`);
    const reachLen = b.ch.armLength * 0.98;
    const need = shoulder.distanceTo(tgt);
    // if out of reach vertically -> bend trunk / knees (crouch) proportional to height deficit
    const low = clamp((1.0 - tgt.y) / 0.8, 0, 1);
    this.bend = clamp((need - reachLen) / 0.5, 0, 1) + low;
    const phase = this.t < this.reachDur ? smooth(this.t / this.reachDur) : this.t < this.reachDur + this.hold ? 1 : 1 - smooth((this.t - this.reachDur - this.hold) / this.reachDur);
    this.phase = phase;
    b.pelvisOffset.set(0, -0.35 * low * phase, -0.05 * low * phase);
    b.handTargets[s] = { pos: tgt, weight: phase };
    if (this.t >= this.reachDur && !this.acted) {
      this.acted = true;
      if (this.mode === 'grab' && this.object) { b.grip[s] = 0.7; b.attach(s, this.object); }
      if (this.mode === 'release') { const o = b.detach(s, this.place); b.grip[s] = 0; this.released = o; }
    }
    if (this.mode === 'grab' && this.t < this.reachDur) b.grip[s] = 0.2 * phase;
    if (this.t >= this.dur) { b.handTargets[s] = null; b.pelvisOffset.set(0, 0, 0); return this.finish({ ok: true, mode: this.mode }); }
    return false;
  }
  pose(L) { const ph = this.phase || 0; L.spine_flexion += 35 * clamp(this.bend, 0, 1.2) * ph; for (const s of ['L', 'R']) L[`knee_flexion_${s}`] = (L[`knee_flexion_${s}`] || 0); }
}

export class GestureAction extends Action {
  constructor(body, name, { dur = null, side = 'R', target = null } = {}) {
    const D = { wave: 2.4, nod: 0.9, shake: 1.1, shrug: 1.3, open_palms: 1.6, think: 2.5, beat: 0.45, point: 2.2, handshake: 3.0 };
    super(body, dur || D[name] || 1.2);
    Object.assign(this, { name, side, target });
  }
  update(dt) {
    this.t += dt;
    const b = this.b;
    const p = this.t / this.dur;
    const env = Math.sin(Math.PI * clamp(p, 0, 1)) ** 0.6;    // ease in/out envelope
    const L = {};
    const s = this.side, o = s === 'R' ? 'L' : 'R';
    switch (this.name) {
      case 'wave': L[`shoulder_abduction_${s}`] = 150 * env; L[`elbow_flexion_${s}`] = 75 * env; L[`forearm_pronation_${s}`] = -60 * env;
        L[`shoulder_rotation_${s}`] = 18 * env * Math.sin(this.t * 2 * Math.PI * 2.0); L.neck_lateral = (s === 'R' ? 4 : -4) * env; break;
      case 'nod': L.neck_flexion = 12 * Math.sin(this.t * 2 * Math.PI * 2.2) * env; break;
      case 'shake': L.neck_rotation = 14 * Math.sin(this.t * 2 * Math.PI * 2.4) * env; break;
      case 'shrug': for (const x of ['L', 'R']) { L[`clavicle_elevation_${x}`] = 22 * env; L[`elbow_flexion_${x}`] = 60 * env; L[`forearm_pronation_${x}`] = -70 * env; L[`shoulder_abduction_${x}`] = 15 * env; } L.neck_lateral = 6 * env; break;
      case 'open_palms': for (const x of ['L', 'R']) { L[`shoulder_flexion_${x}`] = 25 * env; L[`elbow_flexion_${x}`] = 70 * env; L[`forearm_pronation_${x}`] = -75 * env; L[`shoulder_abduction_${x}`] = 10 * env; } break;
      case 'think': L[`shoulder_flexion_${s}`] = 40 * env; L[`elbow_flexion_${s}`] = 135 * env; L[`shoulder_abduction_${s}`] = -10 * env; L[`wrist_flexion_${s}`] = -20 * env;
        L.neck_flexion = -6 * env; L.neck_lateral = 5 * env; L[`shoulder_flexion_${o}`] = 25 * env; L[`elbow_flexion_${o}`] = 85 * env; break;
      case 'beat': L[`elbow_flexion_${s}`] = 25 * env; L[`wrist_flexion_${s}`] = -18 * env; L[`shoulder_flexion_${s}`] = 12 * env; break;
      case 'point': {
        if (this.target) {
          const dir = this.target.clone().sub(b.ch.worldPos(`upperarm01.${s}`)).applyQuaternion(b.ch.root.quaternion.clone().invert()).normalize();
          const elev = Math.asin(clamp(dir.y, -1, 1)) * R2D;
          const az = Math.atan2(dir.x * (s === 'L' ? 1 : -1), dir.z) * R2D;     // + = outward
          L[`shoulder_flexion_${s}`] = clamp(90 + elev, 0, 170) * env * clamp(1 - az / 120, 0, 1);
          L[`shoulder_abduction_${s}`] = (clamp(az, -30, 90) + 20) * env;
          L[`elbow_flexion_${s}`] = -8 * env;
        }
        for (let f = 3; f <= 5; f++) { L[`finger${f}_1_flexion_${s}`] = 70 * env; L[`finger${f}_2_flexion_${s}`] = 80 * env; }
        L[`finger2_1_flexion_${s}`] = -15 * env; L[`finger2_2_flexion_${s}`] = -20 * env; L[`finger2_3_flexion_${s}`] = -12 * env;
        L[`finger1_2_flexion_${s}`] = 30 * env; break;
      }
      case 'handshake': {
        const f = b.facingVec(), r = b.rightVec();
        const pos = b.pos.clone().addScaledVector(f, 0.42).addScaledVector(r, 0.08).add(new THREE.Vector3(0, 1.0 + 0.03 * Math.sin(this.t * 2 * Math.PI * 2.4) * (p > 0.3 && p < 0.8 ? 1 : 0), 0));
        b.handTargets.R = { pos, weight: env };
        b.grip.R = 0.45 * env;
        L.forearm_pronation_R = -50 * env;
        if (this.t >= this.dur) { b.handTargets.R = null; b.grip.R = 0; }
        break;
      }
      default: break;
    }
    b.gestureLayer = L;
    if (this.t >= this.dur) { b.gestureLayer = {}; return this.finish({ ok: true, gesture: this.name }); }
    return false;
  }
}

export class DoorAction extends Action {
  // door: world.door {hinge, handleWorld(), setAngle(a)}; assumes the character stands at door.approach
  constructor(body, door) { super(body, 3.0); this.door = door; }
  update(dt) {
    const b = this.b; this.t += dt;
    const d = this.door;
    const reach = smooth(this.t / 0.8), open = smooth((this.t - 0.8) / 1.6), release = smooth((this.t - 2.5) / 0.5);
    d.setAngle(open * d.maxAngle);
    b.handTargets.R = { pos: d.handleWorld(), weight: reach * (1 - release) };
    b.grip.R = 0.6 * reach * (1 - release);
    this.lean = open * (1 - release);
    if (this.t >= this.dur) { b.handTargets.R = null; b.grip.R = 0; return this.finish({ ok: true, door: 'open' }); }
    return false;
  }
  pose(L) { L.spine_rotation += 10 * (this.lean || 0); L.spine_flexion += 6 * (this.lean || 0); }
}
