// Gaze / oculomotor model: saccades (main sequence), micro-saccades, fixational drift, smooth pursuit,
// binocular vergence, head-eye coordination, lid-follow, stochastic blinking, pupil dynamics.
import * as THREE from '../vendor/three/three.module.js';
import { Spring } from './ik.js';

const R2D = 180 / Math.PI;

export class GazeController {
  constructor(character) {
    this.ch = character;
    this.target = null;                      // {object3D | Vector3 | fn}
    this.mode = 'idle';                     // idle | fixate | pursue | avert | contact
    this.gazePoint = new THREE.Vector3(0, 1.65, 2.0);   // current (eye) fixation point, world
    this.saccade = null;
    this.nextSaccade = 0.3;
    this.nextMicro = 0.4;
    this.microOff = new THREE.Vector2();
    this.drift = new THREE.Vector2();
    this.blinkT = -1;
    this.blinkDur = 0.25;
    this.nextBlink = 1.5 + Math.random() * 3;
    this.headYaw = new Spring(0, 0.18);
    this.headPitch = new Spring(0, 0.2);
    this.pupil = new Spring(0.38, 0.35);
    this.light = 0.5;                       // scene luminance proxy 0..1 (set by app from lighting)
    this.arousal = 0;
    this.blinkRate = 1;                     // multiplier (emotion/fatigue)
    this.slowBlink = 0;
    this.gazeDown = 0;
    this.wander = 1;
    this.talking = false;
    this.contactPhase = 0;
    this.contactPart = 'eyes';
    this.lidL = 0; this.lidR = 0;
    this.stats = { saccades: 0, blinks: 0, micro: 0 };
  }

  lookAt(target, mode = 'fixate') { this.target = target; this.mode = target ? mode : 'idle'; this.nextSaccade = 0; }
  blink() { if (this.blinkT < 0) { this.blinkT = 0; this.blinkDur = 0.2 + Math.random() * 0.08; } }

  _targetPoint() {
    const t = this.target;
    if (!t) return null;
    if (t.isVector3) return t.clone();
    if (t.isObject3D) return t.getWorldPosition(new THREE.Vector3());
    if (typeof t === 'function') return t();
    return null;
  }

  _eyeOrigin() {
    return this.ch.worldPos('eye.L').add(this.ch.worldPos('eye.R')).multiplyScalar(0.5);
  }

  // choose where to look next when idle / during conversation
  _pickFixation(base) {
    const o = this._eyeOrigin();
    const fwd = new THREE.Vector3(0, 0, 1).applyQuaternion(this.ch.root.quaternion);
    if (this.mode === 'contact' && base) {
      // faces: alternate between eyes and mouth, sometimes look away (social gaze statistics)
      const r = Math.random();
      this.contactPart = r < 0.62 ? 'eyes' : r < 0.8 ? 'mouth' : 'away';
      if (this.contactPart === 'eyes') return base.clone().add(new THREE.Vector3((Math.random() < 0.5 ? -1 : 1) * 0.032, 0, 0));
      if (this.contactPart === 'mouth') return base.clone().add(new THREE.Vector3(0, -0.075, 0));
      const side = new THREE.Vector3().crossVectors(fwd, new THREE.Vector3(0, 1, 0));
      return base.clone().add(side.multiplyScalar((Math.random() - 0.5) * 0.9)).add(new THREE.Vector3(0, (Math.random() - 0.6) * 0.4, 0));
    }
    if (base) return base;
    // idle scanning: forward-biased random points in the environment
    const yaw = (Math.random() - 0.5) * 1.6 * this.wander;
    const pitch = (Math.random() - 0.55) * 0.5 - this.gazeDown * 0.35;
    const dir = fwd.clone().applyAxisAngle(new THREE.Vector3(0, 1, 0), yaw);
    dir.y += Math.tan(pitch);
    return o.clone().add(dir.normalize().multiplyScalar(1.5 + Math.random() * 4));
  }

  update(dt) {
    const o = this._eyeOrigin();
    const tp = this._targetPoint();
    // --- saccade / pursuit scheduling
    this.nextSaccade -= dt;
    if (this.mode === 'pursue' && tp) {
      // smooth pursuit: track continuously with gain < 1, catch-up saccade if error > 2 deg
      const err = angleBetween(this.gazePoint.clone().sub(o), tp.clone().sub(o));
      if (err > 2 && !this.saccade) this._startSaccade(tp);
      else if (!this.saccade) this.gazePoint.lerp(tp, 1 - Math.exp(-dt * 9));
    } else if (this.nextSaccade <= 0 && !this.saccade) {
      const dest = this.mode === 'fixate' ? tp : this._pickFixation(tp);
      if (dest) this._startSaccade(dest);
      const base = this.mode === 'contact' ? (this.contactPart === 'away' ? 0.6 : 1.4) : this.mode === 'fixate' ? 0.9 : 1.6;
      this.nextSaccade = base * (0.5 + Math.random()) / Math.max(0.3, this.wander);
    } else if (this.mode === 'fixate' && tp && !this.saccade) {
      // re-centre if target moved
      if (angleBetween(this.gazePoint.clone().sub(o), tp.clone().sub(o)) > 1.5) this._startSaccade(tp);
    }
    if (this.saccade) {
      const s = this.saccade;
      s.t += dt;
      const x = Math.min(1, s.t / s.dur);
      const m = x * x * x * (10 - 15 * x + 6 * x * x);     // minimum-jerk profile
      this.gazePoint.lerpVectors(s.from, s.to, m);
      if (x >= 1) {
        this.saccade = null;
        // gaze-evoked blink for large saccades
        if (s.amp > 25 && Math.random() < 0.45) this.blink();
      }
    }
    // micro-saccades + drift during fixation
    this.nextMicro -= dt;
    if (this.nextMicro <= 0) {
      const a = (0.1 + Math.random() * 0.35) / R2D, th = Math.random() * Math.PI * 2;
      this.microOff.set(Math.cos(th) * a, Math.sin(th) * a);
      this.nextMicro = 0.4 + Math.random() * 1.4;
      this.stats.micro++;
    }
    this.drift.x += (Math.random() - 0.5) * dt * 0.002 - this.drift.x * dt * 2;
    this.drift.y += (Math.random() - 0.5) * dt * 0.002 - this.drift.y * dt * 2;

    // --- head-eye coordination: head takes over the part of eccentricity beyond ~12 deg
    const charInv = this.ch.root.quaternion.clone().invert();
    const dLocal = this.gazePoint.clone().sub(o).applyQuaternion(charInv).normalize();
    const yaw = Math.atan2(dLocal.x, dLocal.z) * R2D, pitch = Math.asin(THREE.MathUtils.clamp(dLocal.y, -1, 1)) * R2D;
    const share = (a, thr) => (Math.abs(a) > thr ? (Math.abs(a) - thr * 0.7) * Math.sign(a) * 0.85 : a * 0.15);
    this.headYawDeg = this.headYaw.update(THREE.MathUtils.clamp(share(yaw, 12), -70, 70), dt);
    this.headPitchDeg = this.headPitch.update(THREE.MathUtils.clamp(share(pitch, 10), -40, 35), dt);
    // --- blinks
    this.nextBlink -= dt;
    const rate = (17 / 60) * this.blinkRate * (this.talking ? 1.35 : 1);  // ~17 / min baseline
    if (this.nextBlink <= 0) {
      this.blink();
      this.nextBlink = -Math.log(Math.random()) / rate + 0.25;
      if (Math.random() < 0.08) this.nextBlink = 0.35;                       // occasional double blink
    }
    let blinkW = 0;
    if (this.blinkT >= 0) {
      this.blinkT += dt;
      const dur = this.blinkDur * (1 + this.slowBlink * 0.8);
      const close = dur * 0.3;
      if (this.blinkT < close) blinkW = Math.sin((this.blinkT / close) * Math.PI / 2);
      else if (this.blinkT < dur) blinkW = Math.cos(((this.blinkT - close) / (dur - close)) * Math.PI / 2) ** 1.5;
      else { this.blinkT = -1; this.stats.blinks++; }
    }
    // --- pupil: light reflex + arousal + near-response
    const dist = this.gazePoint.distanceTo(o);
    const lightTerm = 0.62 - 0.4 * this.light;              // dark -> dilated
    const near = dist < 0.5 ? (0.5 - dist) * 0.25 : 0;
    this.pupilFrac = this.pupil.update(THREE.MathUtils.clamp(lightTerm + this.arousal * 0.5 - near, 0.2, 0.75), dt);
    this.blinkW = blinkW;
    this.yaw = yaw; this.pitch = pitch;
    return { headYaw: this.headYawDeg, headPitch: this.headPitchDeg, blink: blinkW };
  }

  _startSaccade(dest) {
    const o = this._eyeOrigin();
    const amp = angleBetween(this.gazePoint.clone().sub(o), dest.clone().sub(o));
    if (amp < 0.3) { this.gazePoint.copy(dest); return; }
    const dur = (21 + 2.2 * amp) / 1000;                       // main sequence (ms)
    this.saccade = { from: this.gazePoint.clone(), to: dest.clone(), t: 0, dur, amp };
    this.stats.saccades++;
  }

  // post-pose: rotate eye bones to fixation point (+micro offsets), return lid-follow morph weights
  applyEyes() {
    const out = {};
    for (const s of ['L', 'R']) {
      const eb = this.ch.bone(`eye.${s}`);
      const p = eb.getWorldPosition(new THREE.Vector3());
      const head = this.ch.bone('head');
      const hq = head.getWorldQuaternion(new THREE.Quaternion());
      const hqBind = this.ch.headBindInv || (this.ch.headBindInv = head.getWorldQuaternion(new THREE.Quaternion()).premultiply(this.ch.root.quaternion.clone().invert()).invert());
      const headFrame = hq.clone().multiply(hqBind);           // current head orientation relative to bind
      const d = this.gazePoint.clone().sub(p).applyQuaternion(headFrame.clone().invert()).normalize();
      let yaw = Math.atan2(d.x, d.z) + this.microOff.x + this.drift.x;
      let pitch = Math.asin(THREE.MathUtils.clamp(d.y, -1, 1)) + this.microOff.y + this.drift.y;
      yaw = THREE.MathUtils.clamp(yaw * R2D, -45, 45); pitch = THREE.MathUtils.clamp(pitch * R2D, -35, 30);
      this.ch.eyeAngles = this.ch.eyeAngles || {};
      this.ch.eyeAngles[s] = { yaw, pitch };
      // rotate eye bone: compose yaw/pitch using probed DOF axes
      const ax = this.ch.dofAxes;
      const ya = ax[`eye_yaw_${s}`][0], pa = ax[`eye_pitch_${s}`][0];
      eb.quaternion.copy(this.ch.restQuat[eb.name])
        .multiply(new THREE.Quaternion().setFromAxisAngle(ya.axis, yaw / R2D))
        .multiply(new THREE.Quaternion().setFromAxisAngle(pa.axis, pitch / R2D));
      eb.updateMatrixWorld(true);
      const side = s === 'L' ? 'Left' : 'Right';
      // lid follow: ARKit eyeLook shapes (left eye: "in" = toward nose = character right = negative yaw)
      out[`eyeLookUp${side}`] = Math.max(0, pitch / 30);
      out[`eyeLookDown${side}`] = Math.max(0, -pitch / 35);
      const inward = s === 'L' ? -yaw : yaw;
      out[`eyeLookIn${side}`] = Math.max(0, inward / 40);
      out[`eyeLookOut${side}`] = Math.max(0, -inward / 40);
      out[`eyeBlink${side}`] = Math.min(1, this.blinkW + Math.max(0, -pitch / 35) * 0.25);
    }
    return out;
  }
}

function angleBetween(a, b) { return a.angleTo(b) * R2D; }
