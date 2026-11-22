// The world: characters live ON a laptop keyboard; the laptop screen is the backdrop wall. Lamp cone, rubber duck, window + night city behind, bokeh lights, dust.
import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { rng, facet } from './chars.js';
import { screenTex } from './ui.js';

const M = (color, o = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.8, flatShading: true, ...o });
export const KEY_TOP = 1.75;     // y of the key tops (characters' floor)

export function buildSet(scene) {
  const S = {};
  // ---- sky + stars + city (far)
  const skyC = document.createElement('canvas'); skyC.width = 4; skyC.height = 256; const sg = skyC.getContext('2d');
  const gr = sg.createLinearGradient(0, 0, 0, 256); gr.addColorStop(0, '#05061a'); gr.addColorStop(.6, '#12165a'); gr.addColorStop(1, '#262c86'); sg.fillStyle = gr; sg.fillRect(0, 0, 4, 256);
  const skyT = new THREE.CanvasTexture(skyC); skyT.colorSpace = THREE.SRGBColorSpace;
  const sky = new THREE.Mesh(new THREE.PlaneGeometry(3000, 1400), new THREE.MeshBasicMaterial({ map: skyT, fog: false })); sky.position.set(0, 300, -1100); scene.add(sky);
  { const r = rng(5), n = 240, p = new Float32Array(n * 3); for (let i = 0; i < n; i++) { p[i * 3] = (r() - .5) * 2400; p[i * 3 + 1] = 120 + r() * 800; p[i * 3 + 2] = -1050; }
    const gg = new THREE.BufferGeometry(); gg.setAttribute('position', new THREE.BufferAttribute(p, 3)); scene.add(new THREE.Points(gg, new THREE.PointsMaterial({ color: 0xbfc4ff, size: 2.2, sizeAttenuation: false, transparent: true, opacity: .7 }))); }
  const winC = document.createElement('canvas'); winC.width = 128; winC.height = 256; const wg = winC.getContext('2d');
  wg.fillStyle = '#0c0d2a'; wg.fillRect(0, 0, 128, 256); { const r = rng(9); for (let y = 6; y < 256; y += 16) for (let x = 6; x < 128; x += 16) if (r() < .42) { wg.fillStyle = r() < .85 ? '#ffd27a' : '#fff2c8'; wg.fillRect(x, y, 9, 9); } }
  const winT = new THREE.CanvasTexture(winC); winT.colorSpace = THREE.SRGBColorSpace; winT.wrapS = winT.wrapT = THREE.RepeatWrapping; winT.magFilter = THREE.NearestFilter;
  const city = new THREE.Group(); scene.add(city);
  { const r = rng(17);
    for (let row = 0; row < 3; row++) for (let i = 0; i < 26; i++) {
      const k = 1 + row * .7, w = (14 + r() * 26) * k, h = (20 + r() * (row === 0 ? 45 : 62)) * k, d = 20 * k, z = -170 - row * 140 - r() * 40, x = (-260 + i * 21 + r() * 12) * k;
      const t = winT.clone(); t.needsUpdate = true; t.repeat.set(w / 26, h / 48); t.offset.set(r(), r());
      const mat = new THREE.MeshStandardMaterial({ color: row === 0 ? 0x10133a : 0x161a50, emissive: 0xffffff, emissiveMap: t, emissiveIntensity: row === 0 ? .95 : .7, roughness: 1, map: t });
      const b = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat); b.position.set(x, -20 * k + h / 2 + 18, z); city.add(b); } }
  // ---- window wall
  const wall = M(0x0b0b20, { roughness: 1 });
  const WZ = -62, mk = (w, h, x, y) => { const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, 3), wall); m.position.set(x, y, WZ); scene.add(m); return m; };
  mk(500, 80, 0, 118); mk(190, 320, -190, 20); mk(190, 320, 190, 20); mk(3.2, 140, 0, 56); mk(140, 3.2, 0, 70);
  // ---- desk + deep floor
  const desk = new THREE.Mesh(new THREE.BoxGeometry(180, 3, 110), M(0x241c36, { roughness: .6 })); desk.position.set(0, -1.5, 0); desk.receiveShadow = true; scene.add(desk);
  // ---- laptop: deck + keys + hinge + screen wall
  const alu = M(0x2a2937, { roughness: .45, metalness: .5, flatShading: false });
  const deck = new THREE.Mesh(new RoundedBoxGeometry(46, 1.2, 30, 2, .4), alu); deck.position.set(0, .6, 0); deck.receiveShadow = true; scene.add(deck);
  { const kg = new RoundedBoxGeometry(2.0, .55, 2.0, 1, .12), km = M(0x1a1926, { roughness: .55 }), COLS = 17, ROWS = 6, keys = new THREE.InstancedMesh(kg, km, COLS * ROWS), o = new THREE.Object3D(); let k = 0;
    for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) { o.position.set((c - (COLS - 1) / 2) * 2.5, 1.48, -10.5 + r * 2.5); o.updateMatrix(); keys.setMatrixAt(k++, o.matrix); }
    keys.castShadow = keys.receiveShadow = true; scene.add(keys);
    const pad = new THREE.Mesh(new RoundedBoxGeometry(14, .25, 8, 1, .1), M(0x353346, { roughness: .35 })); pad.position.set(0, 1.28, 11); scene.add(pad); }
  const lid = new THREE.Group(); lid.position.set(0, 1.0, -14.5); lid.rotation.x = -0.1; scene.add(lid);
  const lidBox = new THREE.Mesh(new RoundedBoxGeometry(46, 28, 1.2, 2, .4), alu); lidBox.position.set(0, 14, -.5); lidBox.castShadow = lidBox.receiveShadow = true; lid.add(lidBox);
  const scrMat = new THREE.MeshBasicMaterial({ map: screenTex, toneMapped: false, color: new THREE.Color(1.15, 1.12, 1.25) });
  const scr = new THREE.Mesh(new THREE.PlaneGeometry(44, 26.5), scrMat); scr.position.set(0, 14, .15); lid.add(scr); S.screen = scr;
  // screen light: cool violet spill onto the cast + keyboard edge
  const spill = new THREE.PointLight(0x8f7dff, 85, 60, 1.6); spill.position.set(0, 10, -10); scene.add(spill); S.spill = spill;
  const edge = new THREE.PointLight(0x7f6cff, 40, 40, 1.8); edge.position.set(0, 3, 14); scene.add(edge);
  // ---- lamp cone (top-left of frame, hangs in many close-ups) + warm spot
  { const lamp = new THREE.Group(); lamp.position.set(-22, 30, 2); scene.add(lamp);
    const shade = new THREE.Mesh(new THREE.CylinderGeometry(3.2, 7.5, 7, 9, 1, true), new THREE.MeshStandardMaterial({ color: 0xfff0cc, emissive: 0xffd9a0, emissiveIntensity: 2.4, side: THREE.DoubleSide, flatShading: true })); lamp.add(shade);
    const arm = new THREE.Mesh(new THREE.CylinderGeometry(.35, .35, 40, 6), M(0x2a2232)); arm.position.set(-3, 22, -3); arm.rotation.z = .2; lamp.add(arm);
    const key = new THREE.SpotLight(0xffb878, 700, 160, .5, .8, 1.3); key.position.set(-17, 21, 27); key.target.position.set(0, 4, 2); key.castShadow = true; key.shadow.mapSize.set(2048, 2048); key.shadow.bias = -0.0004; key.shadow.radius = 4; scene.add(key, key.target); S.key = key;
    const warmFill = new THREE.PointLight(0xffc48a, 60, 60, 1.6); warmFill.position.set(-18, 18, 6); scene.add(warmFill); }
  // ---- rubber duck (left, on the desk)
  { const duck = new THREE.Group(); duck.position.set(-30, 0, 9); duck.rotation.y = 1.0; duck.scale.setScalar(1.25); scene.add(duck); S.duck = duck;
    const yel = M(0xf2b53a, { roughness: .55, emissive: 0x3a2204, emissiveIntensity: .5 }), org = M(0xf08a2a);
    const bd = new THREE.Mesh(facet(new THREE.IcosahedronGeometry(4.2, 1), .6, 701), yel); bd.scale.set(1.15, .9, 1); bd.position.y = 4; duck.add(bd);
    const hd = new THREE.Mesh(facet(new THREE.IcosahedronGeometry(2.6, 1), .4, 702), yel); hd.position.set(2.2, 8.4, 0); duck.add(hd);
    const bk = new THREE.Mesh(new THREE.BoxGeometry(2.4, .8, 1.8), org); bk.position.set(4.6, 8.0, 0); duck.add(bk);
    const tl = new THREE.Mesh(new THREE.ConeGeometry(1.4, 2.6, 4), yel); tl.position.set(-4.7, 5.4, 0); tl.rotation.z = 1.2; duck.add(tl);
    for (const s of [-1, 1]) { const ey = new THREE.Mesh(new THREE.CircleGeometry(.32, 8), new THREE.MeshBasicMaterial({ color: 0x120a14 })); ey.position.set(3.6, 9.2, s * 1.9); ey.rotation.y = s > 0 ? 0 : Math.PI; duck.add(ey); }
    duck.traverse((o) => { if (o.isMesh) { o.castShadow = o.receiveShadow = true; } }); }
  { const dl = new THREE.PointLight(0xffc890, 220, 60, 1.5); dl.position.set(-20, 16, 20); scene.add(dl); }
  // ---- bokeh string lights (far, behind screen top)
  { const bm = new THREE.MeshBasicMaterial({ color: new THREE.Color(4.5, 3.4, 1.9), toneMapped: false }); S.bulbs = []; const n = 15;
    for (let i = 0; i < n; i++) { const u = (i + .5) / n, x = -74 + 148 * u, y = 52 - 7 * 4 * u * (1 - u) + Math.sin(i * 2.3) * .6; const b = new THREE.Mesh(new THREE.IcosahedronGeometry(1.15, 1), bm.clone()); b.position.set(x, y, -34); scene.add(b); S.bulbs.push(b); } }
  // ---- dust + snow bokeh
  const soft = (() => { const c = document.createElement('canvas'); c.width = c.height = 64; const x = c.getContext('2d'); const gg = x.createRadialGradient(32, 32, 0, 32, 32, 32); gg.addColorStop(0, 'rgba(255,255,255,1)'); gg.addColorStop(.45, 'rgba(255,255,255,.6)'); gg.addColorStop(1, 'rgba(255,255,255,0)'); x.fillStyle = gg; x.fillRect(0, 0, 64, 64); return new THREE.CanvasTexture(c); })();
  const mkP = (n, seed, box, size, color, opacity) => {
    const r = rng(seed), base = new Float32Array(n * 4); for (let i = 0; i < n * 4; i++) base[i] = r();
    const gg = new THREE.BufferGeometry(), pos = new Float32Array(n * 3); gg.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    const pts = new THREE.Points(gg, new THREE.PointsMaterial({ map: soft, size, color, transparent: true, opacity, depthWrite: false, sizeAttenuation: true, blending: THREE.AdditiveBlending })); pts.frustumCulled = false; scene.add(pts);
    return { update(t, speed, sway) { for (let i = 0; i < n; i++) { const b = base.subarray(i * 4, i * 4 + 4); const fall = ((b[1] - t * speed * (.6 + .8 * b[3])) % 1 + 1) % 1;
      pos[i * 3] = box[0] + b[0] * (box[1] - box[0]) + Math.sin(t * .7 + b[2] * 20) * sway; pos[i * 3 + 1] = box[2] + fall * (box[3] - box[2]); pos[i * 3 + 2] = box[4] + b[2] * (box[5] - box[4]); } gg.attributes.position.needsUpdate = true; } };
  };
  S.snow = mkP(900, 41, [-150, 150, -50, 150, -150, -66], 1.5, 0xdfe4ff, .8);
  S.dust = mkP(160, 43, [-45, 45, 3, 40, -14, 30], .5, 0xffe2b8, .55);
  // ---- ambient
  scene.add(new THREE.HemisphereLight(0x4a4fb0, 0x140f20, 1.0));
  const moon = new THREE.DirectionalLight(0x6f78ff, 1.0); moon.position.set(-30, 80, -120); scene.add(moon);
  scene.fog = new THREE.Fog(0x0b0c2a, 260, 1300);
  return S;
}
export function animateSet(S, t) {
  S.snow.update(t, .03, 2.5); S.dust.update(t, -.007, 2.2);
  S.bulbs.forEach((b, i) => { const f = .85 + .15 * Math.sin(t * 1.3 + i * 2.1) * Math.sin(t * .37 + i); b.material.color.setRGB(4.5 * f, 3.4 * f, 1.9 * f); });
}
