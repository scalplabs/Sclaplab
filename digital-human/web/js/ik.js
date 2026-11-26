// Inverse kinematics utilities operating on three.js bones in world space.
import * as THREE from '../vendor/three/three.module.js';

const _v1 = new THREE.Vector3(), _v2 = new THREE.Vector3(), _q = new THREE.Quaternion(), _q2 = new THREE.Quaternion();

// Rotate `bone` (world-space delta) so that the world vector from `from` to `to` (both world points that move
// rigidly with the bone) aligns with `targetDir`.
export function aimBone(bone, from, to, targetDir, weight = 1) {
  const cur = _v1.subVectors(to, from).normalize();
  const tgt = _v2.copy(targetDir).normalize();
  const delta = _q.setFromUnitVectors(cur, tgt);
  if (weight < 1) delta.slerp(new THREE.Quaternion(), 1 - weight);
  rotateBoneWorld(bone, delta);
}

export function rotateBoneWorld(bone, deltaWorld) {
  const parentQ = bone.parent.getWorldQuaternion(_q2);
  const wq = bone.getWorldQuaternion(new THREE.Quaternion());
  wq.premultiply(deltaWorld);
  bone.quaternion.copy(parentQ.invert().multiply(wq));
  bone.updateMatrixWorld(true);
}

export function setBoneWorldQuaternion(bone, wq) {
  const parentQ = bone.parent.getWorldQuaternion(_q2);
  bone.quaternion.copy(parentQ.invert().multiply(wq));
  bone.updateMatrixWorld(true);
}

/**
 * Analytic two-bone IK.
 * upper/lower/end: bones (end = bone whose head is the effector joint, e.g. foot or wrist)
 * target: world position for end joint; pole: world point the middle joint should point toward.
 * Returns {reached, dist} . Keeps end bone world orientation if keepEndRot.
 */
export function twoBoneIK(upper, lower, end, target, pole, { weight = 1, keepEndRot = null, softness = 0.02 } = {}) {
  const a = upper.getWorldPosition(new THREE.Vector3());
  const b = lower.getWorldPosition(new THREE.Vector3());
  const c = end.getWorldPosition(new THREE.Vector3());
  const endRot = keepEndRot || end.getWorldQuaternion(new THREE.Quaternion());
  const lab = a.distanceTo(b), lcb = b.distanceTo(c);
  const tgt = new THREE.Vector3().lerpVectors(c, target, weight);
  let lat = a.distanceTo(tgt);
  const maxL = (lab + lcb) * (1 - 1e-4);
  // soft IK: ease the last few % of extension to avoid knee/elbow snapping
  const soft = maxL * softness;
  const reached = lat <= maxL;
  if (lat > maxL - soft) {
    const over = lat - (maxL - soft);
    lat = maxL - soft + soft * (1 - Math.exp(-over / soft));
  }
  lat = Math.max(lat, Math.abs(lab - lcb) + 1e-4);
  const dir = new THREE.Vector3().subVectors(tgt, a).normalize();
  // pole plane
  const pv = new THREE.Vector3().subVectors(pole, a);
  const bend = pv.sub(dir.clone().multiplyScalar(pv.dot(dir))).normalize();
  if (!isFinite(bend.x) || bend.lengthSq() < 1e-8) bend.set(0, 0, 1);
  // angle at a
  const cosA = (lab * lab + lat * lat - lcb * lcb) / (2 * lab * lat);
  const angA = Math.acos(Math.max(-1, Math.min(1, cosA)));
  const bNew = a.clone().add(dir.clone().multiplyScalar(Math.cos(angA) * lab)).add(bend.clone().multiplyScalar(Math.sin(angA) * lab));
  const cNew = a.clone().add(dir.clone().multiplyScalar(lat));
  // apply: upper so that a->b aligns with a->bNew (but must also fix the twist: rotate in bend plane)
  aimBone(upper, a, b, _v1.subVectors(bNew, a).clone());
  const b2 = lower.getWorldPosition(new THREE.Vector3());
  const c2 = end.getWorldPosition(new THREE.Vector3());
  aimBone(lower, b2, c2, new THREE.Vector3().subVectors(cNew, b2));
  setBoneWorldQuaternion(end, endRot);
  return { reached, dist: target.distanceTo(cNew) };
}

// Aim a chain of bones (e.g. spine+neck+head) so the last bone's forward points at target, distributing rotation.
export function lookAtChain(bones, weights, forwardLocal, target, maxAngle = Math.PI / 2) {
  for (let i = 0; i < bones.length; i++) {
    const b = bones[i];
    const p = b.getWorldPosition(new THREE.Vector3());
    const last = bones[bones.length - 1];
    const fw = forwardLocal.clone().applyQuaternion(last.getWorldQuaternion(new THREE.Quaternion())).normalize();
    const want = target.clone().sub(last.getWorldPosition(new THREE.Vector3())).normalize();
    const full = new THREE.Quaternion().setFromUnitVectors(fw, want);
    const ang = 2 * Math.acos(Math.min(1, Math.abs(full.w)));
    if (ang > maxAngle) full.slerp(new THREE.Quaternion(), 1 - maxAngle / ang);
    const part = new THREE.Quaternion().slerp(full, weights[i]);
    rotateBoneWorld(b, part);
    void p;
  }
}

// Critically damped spring (for smoothing scalar or vector targets)
export class Spring {
  constructor(value = 0, halflife = 0.12) { this.x = value; this.v = 0; this.h = halflife; }
  update(target, dt) {
    const y = (4 * Math.LN2) / Math.max(this.h, 1e-4) / 2;
    const j0 = this.x - target, j1 = this.v + j0 * y;
    const e = Math.exp(-y * dt);
    this.x = e * (j0 + j1 * dt) + target;
    this.v = e * (this.v - j1 * y * dt);
    return this.x;
  }
}

export class VecSpring {
  constructor(v = new THREE.Vector3(), halflife = 0.15) { this.x = v.clone(); this.v = new THREE.Vector3(); this.h = halflife; }
  update(target, dt) {
    const y = (4 * Math.LN2) / Math.max(this.h, 1e-4) / 2;
    const j0 = this.x.clone().sub(target), j1 = this.v.clone().add(j0.clone().multiplyScalar(y));
    const e = Math.exp(-y * dt);
    this.x.copy(j0.add(j1.clone().multiplyScalar(dt)).multiplyScalar(e).add(target));
    this.v.copy(this.v.clone().sub(j1.multiplyScalar(y * dt)).multiplyScalar(e));
    return this.x;
  }
}

// Smooth multi-octave noise (incommensurate frequencies -> no visible loop)
export function organic(t, seed = 0, freqs = [0.13, 0.31, 0.77]) {
  let s = 0, a = 1, n = 0;
  for (let i = 0; i < freqs.length; i++) {
    const f = freqs[i] * (1 + 0.1 * Math.sin(seed * 12.9898 + i));
    s += a * Math.sin(t * f * 2 * Math.PI + seed * 7.13 + i * 1.7) * Math.cos(t * f * 0.618 * 2 * Math.PI + seed * 3.1);
    n += a; a *= 0.5;
  }
  return s / n;
}
