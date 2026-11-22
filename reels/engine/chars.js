// Low-poly cast: FOUNDER (indigo suit, cream block shoes, spiky hair) and CLAWD (coral block robot: two slit eyes, 4 stub legs, NO mouth).
import * as THREE from 'three';

export const rng = (s) => () => { s |= 0; s = (s + 0x6D2B79F5) | 0; let t = Math.imul(s ^ (s >>> 15), 1 | s); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
export const strSeed = (str) => { let h = 2166136261; for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; };

const M = (color, o = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.78, metalness: 0.0, flatShading: true, ...o });

export function facet(geo, amt, seed = 1) {
  const p = geo.attributes.position, r = rng(seed), map = new Map();
  for (let i = 0; i < p.count; i++) {
    const k = `${p.getX(i).toFixed(3)},${p.getY(i).toFixed(3)},${p.getZ(i).toFixed(3)}`;
    if (!map.has(k)) map.set(k, [(r() - .5) * amt, (r() - .5) * amt, (r() - .5) * amt]);
    const d = map.get(k); p.setXYZ(i, p.getX(i) + d[0], p.getY(i) + d[1], p.getZ(i) + d[2]);
  }
  geo.computeVertexNormals(); return geo;
}
const box = (w, h, d, mat, seed, j = 0.05) => { const g = facet(new THREE.BoxGeometry(w, h, d, 2, 2, 2), j * Math.min(w, h, d), seed); const m = new THREE.Mesh(g, mat); m.castShadow = m.receiveShadow = true; return m; };
const sharp = (w, h, d, mat) => { const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat); m.castShadow = m.receiveShadow = true; return m; };
const piv = (x = 0, y = 0, z = 0) => { const g = new THREE.Group(); g.position.set(x, y, z); return g; };

// ---------------------------------------------------------------- FOUNDER
export function makeFounder() {
  const skin = M(0xf4a98f, { emissive: 0x2e1008, emissiveIntensity: .55 }), suit = M(0x4a4f5c, { roughness: .85 }), suitD = M(0x2c2f38, { roughness: .9 }), lapel = M(0x5d6372, { roughness: .8 }),
    pants = M(0x30333d), shoe = M(0xe9d7b2, { roughness: .6 }), hair = M(0x1c1526, { roughness: .9 }), hairW = M(0x7a4a2a, { roughness: .9, emissive: 0x2a1204 }),
    black = new THREE.MeshBasicMaterial({ color: 0x120a14 }), mouthM = new THREE.MeshBasicMaterial({ color: 0x3a0f18 }), nose = M(0xff9a5a, { emissive: 0x4a1e08 });
  const root = piv(); root.name = 'founder';
  const hips = piv(0, 2.15, 0); root.add(hips);
  const torso = piv(); hips.add(torso);
  const chest = box(1.5, 1.75, 0.95, suit, 11); chest.position.y = 0.95; torso.add(chest);
  const sh = box(1.95, 0.4, 1.0, suit, 12); sh.position.y = 1.8; torso.add(sh);                       // shoulder pads
  const lapL = sharp(0.34, 1.0, 0.1, lapel); lapL.position.set(-0.3, 1.3, 0.52); lapL.rotation.z = -0.22; torso.add(lapL);
  const lapR = sharp(0.34, 1.0, 0.1, lapel); lapR.position.set(0.3, 1.3, 0.52); lapR.rotation.z = 0.22; torso.add(lapR);
  const shirt = sharp(0.34, 1.1, 0.08, M(0xdcd8ff)); shirt.position.set(0, 1.25, 0.5); torso.add(shirt);
  const belt = sharp(1.5, 0.2, 0.98, suitD); belt.position.y = 0.08; torso.add(belt);
  const neck = piv(0, 1.95, 0); torso.add(neck);
  const head = piv(0, 0.12, 0); neck.add(head);
  const skull = new THREE.Mesh(facet(new THREE.IcosahedronGeometry(1, 1), 0.16, 21), skin); skull.scale.set(1.12, 0.98, 1.0); skull.position.y = 0.9; skull.castShadow = true; head.add(skull);
  const earL = new THREE.Mesh(facet(new THREE.IcosahedronGeometry(0.22, 0), .05, 22), skin); earL.position.set(-1.1, 0.88, 0); head.add(earL);
  const earR = earL.clone(); earR.position.x = 1.1; head.add(earR);
  const cap = new THREE.Mesh(facet(new THREE.IcosahedronGeometry(1.06, 1), 0.18, 23), hair); cap.scale.set(1.1, 0.5, 1.05); cap.position.set(0, 1.6, -0.16); head.add(cap);
  const r = rng(77);
  for (let i = 0; i < 9; i++) {
    const a = -1.25 + i * 0.32, sp = new THREE.Mesh(facet(new THREE.ConeGeometry(0.32, 0.85 + r() * 0.35, 4), 0.05, 30 + i), i > 5 ? hairW : hair);
    sp.position.set(Math.sin(a) * 0.82, 1.82 + r() * 0.1, Math.cos(a) * 0.35 - 0.3); sp.rotation.set(-0.35 + r() * 0.3, r(), Math.sin(a) * -0.55); head.add(sp);
  }
  const fringe = new THREE.Mesh(facet(new THREE.ConeGeometry(0.3, 0.6, 4), 0.04, 40), hair); fringe.position.set(0.32, 1.78, 0.7); fringe.rotation.set(1.9, 0, -0.5); head.add(fringe);
  const face = piv(0, 0.9, 0.93); head.add(face);
  const eyeG = new THREE.CircleGeometry(0.105, 10);
  const eyeL = new THREE.Mesh(eyeG, black); eyeL.position.set(-0.36, 0.2, 0.02); face.add(eyeL);
  const eyeR = eyeL.clone(); eyeR.position.x = 0.36; face.add(eyeR);
  const browL = new THREE.Mesh(new THREE.PlaneGeometry(0.28, 0.06), black); browL.position.set(-0.36, 0.42, 0.03); face.add(browL);
  const browR = browL.clone(); browR.position.x = 0.36; face.add(browR);
  const noseM = new THREE.Mesh(new THREE.ConeGeometry(0.12, 0.34, 3), nose); noseM.rotation.set(Math.PI, 0, 0); noseM.position.set(0, -0.02, 0.1); face.add(noseM);
  const mouth = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), mouthM); mouth.position.set(0, -0.36, 0.03); face.add(mouth);
  const arm = (side) => {
    const s = piv(side * 1.0, 1.75, 0); torso.add(s);
    const up = box(0.44, 1.0, 0.44, suit, 50 + side); up.position.y = -0.48; s.add(up);
    const el = piv(0, -0.95, 0); s.add(el);
    const lo = box(0.4, 0.9, 0.4, suit, 60 + side); lo.position.y = -0.42; el.add(lo);
    const hand = new THREE.Mesh(facet(new THREE.IcosahedronGeometry(0.27, 0), 0.07, 70 + side), M(0xe08a5a)); hand.position.y = -0.95; hand.castShadow = true; el.add(hand);
    return { sh: s, el, hand };
  };
  const L = arm(-1), R = arm(1);
  // phone (right hand)
  const phone = new THREE.Group(); phone.visible = false; R.el.add(phone); phone.position.set(0, -1.0, 0.18); phone.rotation.set(-0.9, 0, 0);
  phone.add(sharp(0.62, 0.07, 1.05, M(0x111118, { roughness: .3 })));
  const pscr = new THREE.Mesh(new THREE.PlaneGeometry(.54, .94), new THREE.MeshBasicMaterial({ color: new THREE.Color(2.6, 2.4, 3.2), toneMapped: false })); pscr.rotation.x = -Math.PI / 2; pscr.position.y = .045; phone.add(pscr);
  const phoneLight = new THREE.PointLight(0xb8a8ff, 0, 9, 1.6); phoneLight.position.set(0, .8, 0); phone.add(phoneLight);
  const leg = (side) => {
    const hp = piv(side * 0.42, 0, 0); hips.add(hp);
    const th = box(0.62, 1.05, 0.64, pants, 80 + side); th.position.y = -0.5; hp.add(th);
    const kn = piv(0, -1.0, 0); hp.add(kn);
    const shn = box(0.56, 0.95, 0.58, pants, 90 + side); shn.position.y = -0.45; kn.add(shn);
    const ft = box(0.7, 0.42, 1.05, shoe, 95 + side, .03); ft.position.set(0, -1.0, 0.2); kn.add(ft);
    return { hp, kn };
  };
  const LL = leg(-1), LR = leg(1);
  const rig = { root, hips, torso, neck, head, face, eyeL, eyeR, browL, browR, mouth, armL: L, armR: R, legL: LL, legR: LR, phone, phoneLight, kind: 'founder' };
  setFMouth(rig, 0, 0, 0); return rig;
}
export function setFMouth(rig, open, round, smile = 0) {
  const w = 0.42 - round * 0.14 + smile * 0.1, h = 0.05 + open * 0.26 + round * open * 0.05;
  rig.mouth.scale.set(w, h, 1); rig.mouth.position.y = -0.36 - open * 0.06 + smile * 0.03;
}
export function setFBlink(rig, b) { const s = Math.max(0.08, 1 - b); rig.eyeL.scale.y = s; rig.eyeR.scale.y = s; }

// ---------------------------------------------------------------- CLAWD (coral block robot)
export function makeClawd() {
  const coral = M(0x9c3329, { roughness: .72, emissive: 0x300a05, emissiveIntensity: .22 }), coralD = M(0xb53f2d, { roughness: .8, emissive: 0x2a0804, emissiveIntensity: .5 }),
    eyeM = new THREE.MeshBasicMaterial({ color: 0x0a0912 });
  const root = piv(); root.name = 'clawd';
  const LEGH = 0.95;
  const legs = [];
  [-1.2, -0.4, 0.4, 1.2].forEach((x, i) => { const lg = sharp(0.52, LEGH, 0.6, coralD); lg.geometry.translate(0, LEGH / 2, 0); lg.position.set(x, 0, 0); root.add(lg); legs.push(lg); });
  const bodyG = piv(0, LEGH, 0); root.add(bodyG);                    // squash pivot at the base of the body
  const body = box(3.5, 3.0, 2.6, coral, 201, .035); body.position.y = 1.5; bodyG.add(body);
  const top = box(3.5, 0.18, 2.6, coral, 202, .02); top.position.y = 3.05; bodyG.add(top);
  const face = piv(0, 1.9, 1.5); bodyG.add(face);
  const eyeL = new THREE.Mesh(new THREE.PlaneGeometry(0.34, 0.86), eyeM); eyeL.position.set(-0.72, 0, 0.02); face.add(eyeL);
  const eyeR = eyeL.clone(); eyeR.position.x = 0.72; face.add(eyeR);
  const arm = (side) => { const p = piv(side * 1.86, 0.9, 0.2); bodyG.add(p); const a = sharp(0.62, 0.5, 0.62, coralD); a.position.x = side * 0.18; p.add(a); return p; };
  const armL = arm(-1), armR = arm(1);
  const rig = { root, bodyG, face, eyeL, eyeR, armL, armR, legs, kind: 'clawd', LEGH };
  return rig;
}
// eye shape: w,h scale + y offset + tilt
export function setCEyes(rig, o) {
  rig.eyeL.scale.set(o.w, o.h, 1); rig.eyeR.scale.set(o.w, o.h, 1);
  rig.eyeL.position.y = o.y; rig.eyeR.position.y = o.y;
  rig.eyeL.rotation.z = o.rot; rig.eyeR.rotation.z = -o.rot;
}
