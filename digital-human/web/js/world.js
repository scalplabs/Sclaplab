// Environment: ground height field (stairs), obstacles, interactable objects.
import * as THREE from '../vendor/three/three.module.js';

export class World {
  constructor(scene) {
    this.scene = scene;
    this.group = new THREE.Group();
    this.group.name = 'World';
    scene.add(this.group);
    this.objects = {};      // id -> {id, type, object3D, ...}
    this.obstacles = [];    // {c: Vector3, r}
    this.stairs = null;
    this._build();
  }

  _mat(c, r = 0.7, extra = {}) { return new THREE.MeshPhysicalMaterial({ color: c, roughness: r, ...extra }); }

  _build() {
    // floor
    const floor = new THREE.Mesh(new THREE.CircleGeometry(14, 96), this._mat(0x6b6760, 0.85));
    floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; floor.name = 'floor';
    this.group.add(floor);
    // wooden chair
    const chair = new THREE.Group(); chair.name = 'chair';
    const wood = this._mat(0x5a3a22, 0.55, { clearcoat: 0.3 });
    const seat = new THREE.Mesh(new THREE.BoxGeometry(0.46, 0.04, 0.44), wood); seat.position.y = 0.45;
    const back = new THREE.Mesh(new THREE.BoxGeometry(0.46, 0.5, 0.03), wood); back.position.set(0, 0.72, -0.21);
    chair.add(seat, back);
    for (const [x, z] of [[-0.2, -0.19], [0.2, -0.19], [-0.2, 0.19], [0.2, 0.19]]) {
      const leg = new THREE.Mesh(new THREE.BoxGeometry(0.035, 0.45, 0.035), wood); leg.position.set(x, 0.225, z); chair.add(leg);
    }
    chair.position.set(-1.6, 0, -0.6); chair.rotation.y = Math.PI / 2;   // seat faces +X
    chair.traverse((o) => { o.castShadow = o.receiveShadow = true; });
    this.group.add(chair);
    this.add({ id: 'chair', type: 'chair', object3D: chair, seatHeight: 0.47,
               seatPoint: () => chair.localToWorld(new THREE.Vector3(0, 0.47, 0.0)),
               approach: () => chair.localToWorld(new THREE.Vector3(0, 0, 0.42)), facing: () => chair.rotation.y });
    this.obstacles.push({ c: chair.position.clone(), r: 0.32, id: 'chair' });
    // table with a cup
    const table = new THREE.Group(); table.name = 'table';
    const top = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.04, 0.6), this._mat(0x8a8178, 0.4)); top.position.y = 0.74;
    table.add(top);
    for (const [x, z] of [[-0.45, -0.25], [0.45, -0.25], [-0.45, 0.25], [0.45, 0.25]]) {
      const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.72), this._mat(0x333333, 0.3, { metalness: 0.8 }));
      leg.position.set(x, 0.36, z); table.add(leg);
    }
    table.position.set(1.4, 0, -0.5);
    table.traverse((o) => { o.castShadow = o.receiveShadow = true; });
    this.group.add(table);
    this.add({ id: 'table', type: 'table', object3D: table, surfaceHeight: 0.76 });
    this.obstacles.push({ c: table.position.clone(), r: 0.55, id: 'table' });
    const cup = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.034, 0.1, 32), this._mat(0xe8e4da, 0.25, { clearcoat: 0.8 }));
    cup.position.set(1.15, 0.81, -0.35); cup.castShadow = true; cup.name = 'cup';
    this.group.add(cup);
    this.add({ id: 'cup', type: 'item', object3D: cup, graspOffset: new THREE.Vector3(0, 0, 0) });
    // door (frame + hinged leaf)
    const door = new THREE.Group(); door.name = 'door';
    const frameM = this._mat(0xd9d4c8, 0.6);
    const l = new THREE.Mesh(new THREE.BoxGeometry(0.08, 2.1, 0.12), frameM); l.position.set(-0.5, 1.05, 0);
    const r = l.clone(); r.position.x = 0.5;
    const t = new THREE.Mesh(new THREE.BoxGeometry(1.08, 0.08, 0.12), frameM); t.position.y = 2.14;
    const hinge = new THREE.Group(); hinge.position.set(-0.46, 0, 0);
    const leaf = new THREE.Mesh(new THREE.BoxGeometry(0.9, 2.04, 0.04), this._mat(0x7b5e43, 0.5)); leaf.position.set(0.45, 1.02, 0);
    const handle = new THREE.Mesh(new THREE.SphereGeometry(0.03, 16, 12), this._mat(0xb0a070, 0.2, { metalness: 1 }));
    handle.position.set(0.8, 1.0, 0.05);
    hinge.add(leaf, handle);
    door.add(l, r, t, hinge);
    door.position.set(0, 0, -3.2);
    door.traverse((o) => { o.castShadow = o.receiveShadow = true; });
    this.group.add(door);
    this.add({ id: 'door', type: 'door', object3D: door, maxAngle: 1.4, angle: 0,
               setAngle: (a) => { hinge.rotation.y = a; this.objects.door.angle = a; },
               handleWorld: () => handle.getWorldPosition(new THREE.Vector3()),
               approach: () => door.localToWorld(new THREE.Vector3(0.55, 0, 0.55)), facing: () => Math.PI });
    // stairs: 5 steps rising toward -X
    const st = new THREE.Group(); st.name = 'stairs';
    const rise = 0.17, run = 0.3, n = 5, w = 1.1;
    for (let i = 0; i < n; i++) {
      const s = new THREE.Mesh(new THREE.BoxGeometry(run, rise * (i + 1), w), this._mat(0x9a948a, 0.8));
      s.position.set(-i * run, rise * (i + 1) / 2, 0); s.castShadow = s.receiveShadow = true; st.add(s);
    }
    const landing = new THREE.Mesh(new THREE.BoxGeometry(1.2, rise * n, w), this._mat(0x9a948a, 0.8));
    landing.position.set(-n * run - 0.45, rise * n / 2, 0); landing.castShadow = landing.receiveShadow = true; st.add(landing);
    st.position.set(-2.6, 0, 2.6);
    this.group.add(st);
    this.stairs = { origin: st.position.clone(), rise, run, n, w, landingLen: 1.2 };
    this.add({ id: 'stairs', type: 'stairs', object3D: st, bottom: () => st.localToWorld(new THREE.Vector3(0.5, 0, 0)),
               top: () => st.localToWorld(new THREE.Vector3(-n * run - 0.4, 0, 0)) });
    // bed / mat for lying down
    const mat = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.06, 2.0), this._mat(0x3f5566, 0.9));
    mat.position.set(2.6, 0.03, 2.2); mat.receiveShadow = true; mat.name = 'mat';
    this.group.add(mat);
    this.add({ id: 'mat', type: 'bed', object3D: mat, surfaceHeight: 0.06, approach: () => new THREE.Vector3(2.6, 0, 1.55), facing: () => Math.PI });
  }

  add(o) { this.objects[o.id] = o; return o; }

  // ground height at (x,z). smooth=true for root/pelvis (ramps between step edges)
  groundHeight(x, z, smooth = false) {
    const S = this.stairs;
    if (!S) return 0;
    const lx = S.origin.x - x + S.run / 2, lz = z - S.origin.z;   // stairs rise toward -X
    if (Math.abs(lz) > S.w / 2 || lx < 0) return 0;
    if (lx > S.n * S.run + S.landingLen) return 0;
    if (smooth) return Math.min(S.n * S.rise, (lx / S.run) * S.rise);
    const i = Math.min(S.n, Math.floor(lx / S.run) + 1);
    return i * S.rise;
  }

  // steering: repulsion from obstacle circles along desired direction
  avoid(pos, vel, radius, goal = null) {
    const out = new THREE.Vector3();
    if (vel.lengthSq() < 1e-6) return out;
    for (const o of this.obstacles) {
      const d = new THREE.Vector3(pos.x - o.c.x, 0, pos.z - o.c.z);
      const dist = d.length();
      let lim = o.r + radius + 0.25;
      // a goal placed next to an obstacle (chair approach, table edge) must stay reachable
      if (goal) lim = Math.min(lim, Math.hypot(goal.x - o.c.x, goal.z - o.c.z) * 0.85);
      if (dist < lim && dist > 1e-4) {
        // push sideways (tangent) so the agent goes around instead of stopping
        const tangent = new THREE.Vector3(-d.z, 0, d.x).normalize();
        if (tangent.dot(vel) < 0) tangent.negate();
        out.addScaledVector(d.normalize(), (lim - dist) * 1.5).addScaledVector(tangent, (lim - dist) * vel.length());
      }
    }
    return out;
  }

  list() { return Object.values(this.objects).map((o) => ({ id: o.id, type: o.type, position: o.object3D.getWorldPosition(new THREE.Vector3()).toArray().map((v) => +v.toFixed(3)) })); }
}
