// Character: GLB loading, material binding, skeleton access, anatomical joint DOFs, morph control,
// pose-space correctives, expression wrinkle drivers and LOD.
import * as THREE from '../vendor/three/three.module.js';
import { GLTFLoader } from '../vendor/three/jsm/loaders/GLTFLoader.js';
import { MeshoptDecoder } from '../vendor/three/jsm/libs/meshopt_decoder.module.js';
import * as M from './materials.js';

export const sanitize = (n) => n.replace(/\s/g, '_').replace(/[\[\]\.:\/]/g, '');
const D2R = Math.PI / 180;

// Anatomical degrees of freedom. dir = character-space direction (x=left, y=up, z=forward) the probe
// point (child joint) must move toward for a POSITIVE angle. 'twist' = rotation about the bone axis,
// positive = front of limb turns toward character-left. Limits from rig_meta.joint_limits (human AROM).
const S = (side) => (side === 'L' ? 1 : -1);
function dofTable() {
  const t = {};
  const add = (name, bone, child, dir, limit, opts = {}) => { t[name] = { bone, child, dir, limit, ...opts }; };
  // spine: total angle is distributed over 5 vertebral segments
  add('spine_flexion', ['spine05', 'spine04', 'spine03', 'spine02', 'spine01'], 'neck01', [0, 0, 1], [-25, 75], { split: [0.15, 0.2, 0.22, 0.23, 0.2] });
  add('spine_lateral', ['spine05', 'spine04', 'spine03', 'spine02', 'spine01'], 'neck01', [1, 0, 0], [-30, 30], { split: [0.15, 0.2, 0.22, 0.23, 0.2] });
  add('spine_rotation', ['spine05', 'spine04', 'spine03', 'spine02', 'spine01'], 'neck01', null, [-35, 35], { twist: true, split: [0.1, 0.15, 0.2, 0.25, 0.3] });
  add('neck_flexion', ['neck01', 'neck02', 'neck03', 'head'], null, [0, 0, 1], [-50, 60], { split: [0.25, 0.25, 0.2, 0.3], probe: 'tail' });
  add('neck_lateral', ['neck01', 'neck02', 'neck03', 'head'], null, [1, 0, 0], [-40, 40], { split: [0.25, 0.25, 0.2, 0.3], probe: 'tail' });
  add('neck_rotation', ['neck01', 'neck02', 'neck03', 'head'], null, null, [-75, 75], { twist: true, split: [0.2, 0.25, 0.25, 0.3] });
  for (const s of ['L', 'R']) {
    const x = S(s);
    add(`clavicle_elevation_${s}`, `clavicle.${s}`, `shoulder01.${s}`, [0, 1, 0], [-10, 35]);
    add(`clavicle_protraction_${s}`, `clavicle.${s}`, `shoulder01.${s}`, [0, 0, 1], [-15, 20]);
    add(`shoulder_flexion_${s}`, `upperarm01.${s}`, `lowerarm01.${s}`, [0, 0, 1], [-50, 170]);
    add(`shoulder_abduction_${s}`, `upperarm01.${s}`, `lowerarm01.${s}`, [x, 0.0, 0], [-60, 170], { probeUp: true });
    add(`shoulder_rotation_${s}`, `upperarm01.${s}`, `lowerarm01.${s}`, null, [-70, 90], { twist: true });
    add(`elbow_flexion_${s}`, `lowerarm01.${s}`, `wrist.${s}`, [0, 0, 1], [0, 145]);
    add(`forearm_pronation_${s}`, `lowerarm02.${s}`, `wrist.${s}`, null, [-80, 85], { twist: true });
    add(`wrist_flexion_${s}`, `wrist.${s}`, `finger3-1.${s}`, [-x, 0, 0.3], [-70, 80]);
    add(`wrist_deviation_${s}`, `wrist.${s}`, `finger3-1.${s}`, [0, 0, 1], [-20, 35]);
    for (let f = 1; f <= 5; f++) {
      for (let k = 1; k <= 3; k++) {
        const nm = `finger${f}-${k}.${s}`;
        const ch = k < 3 ? `finger${f}-${k + 1}.${s}` : null;
        add(`finger${f}_${k}_flexion_${s}`, nm, ch, [-x, 0, 0.4], f === 1 ? [-15, 70] : [-20, k === 1 ? 90 : 105], { probe: ch ? 'child' : 'tail' });
      }
      if (f > 1) add(`finger${f}_spread_${s}`, `finger${f}-1.${s}`, `finger${f}-2.${s}`, [0, 0, 1], [-20, 20]);
    }
    add(`hip_flexion_${s}`, `upperleg01.${s}`, `lowerleg01.${s}`, [0, 0, 1], [-20, 125]);
    add(`hip_abduction_${s}`, `upperleg01.${s}`, `lowerleg01.${s}`, [x, 0, 0], [-30, 45]);
    add(`hip_rotation_${s}`, `upperleg01.${s}`, `lowerleg01.${s}`, null, [-40, 45], { twist: true });
    add(`knee_flexion_${s}`, `lowerleg01.${s}`, `foot.${s}`, [0, 0, -1], [0, 145]);
    add(`ankle_dorsiflexion_${s}`, `foot.${s}`, null, [0, 1, 0], [-50, 25], { probe: 'tail' });
    add(`ankle_inversion_${s}`, `foot.${s}`, null, [-x, 0, 0], [-20, 35], { probe: 'tail' });
    add(`toe_flexion_${s}`, [`toe1-1.${s}`, `toe2-1.${s}`, `toe3-1.${s}`, `toe4-1.${s}`, `toe5-1.${s}`], null, [0, -1, 0], [-50, 60], { probe: 'tail', split: [1, 1, 1, 1, 1] });
    add(`eye_yaw_${s}`, `eye.${s}`, null, [1, 0, 0], [-45, 45], { probe: 'tail' });
    add(`eye_pitch_${s}`, `eye.${s}`, null, [0, 1, 0], [-35, 30], { probe: 'tail' });
  }
  add('pelvis_tilt', 'root', 'spine05', [0, 0, 1], [-25, 25], { probe: 'child' });
  // whole-body pitch about the pelvis (lying down / getting up), not an anatomical joint
  add('body_pitch', 'root', 'spine05', [0, 0, 1], [-95, 60], { probe: 'child' });
  return t;
}

export class Character {
  constructor(scene, opts = {}) {
    this.scene = scene;
    this.base = opts.base || '/assets/characters/minjun';
    this.quality = opts.quality || 'hq';
    this.root = new THREE.Group();          // world transform (setPosition / setRotation)
    this.root.name = 'DigitalHuman';
    scene.add(this.root);
    this.dofs = dofTable();
    this.dofValues = {};                    // final per-frame anatomical angles (deg)
    this.layers = new Map();               // name -> {weight, values:{dof:deg}}
    this.morphTargets = new Map();          // name -> [[mesh, index], ...]
    this.morphValues = {};
    this.manualMorph = {};                  // setBlendshape overrides (0..1 or null)
    this.manualJoint = {};                  // setJointRotation raw local euler (deg) overrides
    this.rootOffset = new THREE.Vector3();  // pelvis translation from animation layers (m)
  }

  async load(lod = 0) {
    this.meta = await (await fetch(`${this.base}/rig_meta.json`)).json();
    const gltf = await new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).loadAsync(`${this.base}/minjun_lod${lod}.glb`);
    this.gltf = gltf;
    this.model = gltf.scene;
    this.root.add(this.model);
    this.meshes = [];
    this.model.traverse((o) => {
      if (o.isSkinnedMesh || o.isMesh) {
        this.meshes.push(o);
        o.castShadow = true;
        o.receiveShadow = true;
        o.frustumCulled = false;
      }
    });
    this.bindMaterials();
    // bones
    this.bones = {};
    this.model.traverse((o) => { if (o.isBone) this.bones[o.name] = o; });
    this.restQuat = {};
    this.restPos = {};
    for (const [n, b] of Object.entries(this.bones)) { this.restQuat[n] = b.quaternion.clone(); this.restPos[n] = b.position.clone(); }
    // morphs
    for (const m of this.meshes) {
      if (!m.morphTargetDictionary) continue;
      for (const [name, idx] of Object.entries(m.morphTargetDictionary)) {
        if (!this.morphTargets.has(name)) this.morphTargets.set(name, []);
        this.morphTargets.get(name).push([m, idx]);
      }
    }
    this.morphNames = [...this.morphTargets.keys()];
    this.model.updateMatrixWorld(true);
    this.probeDofs();
    this.captureEyeBind();
    this.skeletonHelper = new THREE.SkeletonHelper(this.model);
    this.skeletonHelper.visible = false;
    this.scene.add(this.skeletonHelper);
    this.measure();
    return this;
  }

  bone(name) { return this.bones[sanitize(name)] || this.bones[name]; }

  bindMaterials() {
    const B = this.base;
    const mk = {
      DH_Skin: () => M.makeSkinMaterial(B, this.quality),
      DH_EyeSclera: () => M.makeEyeMaterial(B, this.meta.eye),
      DH_Cornea: () => M.makeCorneaMaterial(this.quality), DH_TearFilm: () => M.makeTearMaterial(this.quality),
      DH_EyeOcclusion: () => M.makeEyeOcclusionMaterial(), DH_Caruncle: () => M.makeCaruncleMaterial(),
      DH_Teeth: () => M.makeTeethMaterial(B), DH_Tongue: () => M.makeTongueMaterial(B),
      DH_Eyebrows_Card: () => M.makeCardMaterial(B + '/textures/eyebrow.png', 'brow_card', 0x4a3628, 0.32),
      DH_Eyelashes_Card: () => M.makeCardMaterial(B + '/textures/eyelashes.png', 'lash_card', 0x3a2a20, 0.72),
      DH_HairCards: () => M.makeHairCardMaterial(B + '/textures/hair_card_atlas.png', 0xb0a090),
      DH_male_casualsuit01: () => M.makeClothMaterial(B), DH_shoes06: () => M.makeShoeMaterial(B),
    };
    this.materials = {};
    for (const m of this.meshes) {
      const nm = (m.material.name || '').replace(/_rt$/, '');
      if (!this.materials[nm] && mk[nm]) this.materials[nm] = mk[nm]();
      if (this.materials[nm]) m.material = this.materials[nm];
      if (['DH_Cornea', 'DH_TearFilm', 'DH_EyeOcclusion'].includes(nm)) { m.castShadow = false; m.renderOrder = 2; }
      if (nm === 'DH_EyeOcclusion') m.renderOrder = 3;
      if (['DH_Eyelashes_Card', 'DH_Eyebrows_Card', 'DH_HairCards'].includes(nm)) m.renderOrder = 1;
      m.userData.dhMaterial = nm;
    }
  }

  // ---------------------------------------------------------------- anatomical DOF probing
  _charDir(v) { // character-space vector -> world
    return v.clone().applyQuaternion(this.root.quaternion);
  }

  _probePoint(spec, boneName) {
    const b = this.bone(boneName);
    if (spec.probe === 'tail' || !spec.child) {
      // a point 10 cm along the bone's +Y (bones point along local Y)
      return () => b.localToWorld(new THREE.Vector3(0, 0.1, 0));
    }
    const c = this.bone(spec.child);
    return () => c.getWorldPosition(new THREE.Vector3());
  }

  // Exact anatomical axes: for a swing DOF the rotation axis is (bone direction x desired motion direction),
  // evaluated in world space at the bind pose and converted to each bone's local frame. Twist DOFs rotate about the
  // bone direction (mirrored for the right side so equal values give mirror-symmetric motion).
  probeDofs() {
    this.model.updateMatrixWorld(true);
    this.dofAxes = {};
    const wp = (n) => this.bone(n).getWorldPosition(new THREE.Vector3());
    const palm = {};
    for (const s of ['L', 'R']) {
      const handDir = wp(`finger3-1.${s}`).sub(wp(`wrist.${s}`)).normalize();
      const across = wp(`finger2-1.${s}`).sub(wp(`finger5-1.${s}`)).normalize();
      palm[s] = (s === 'L' ? handDir.clone().cross(across) : across.clone().cross(handDir)).normalize();
      this.palmDir = palm;
    }
    for (const [name, spec] of Object.entries(this.dofs)) {
      const bonesList = Array.isArray(spec.bone) ? spec.bone : [spec.bone];
      const side = /_L$/.test(name) ? 'L' : /_R$/.test(name) ? 'R' : null;
      const out = [];
      for (const bn of bonesList) {
        const b = this.bone(bn);
        if (!b) { out.push(null); continue; }
        const head = b.getWorldPosition(new THREE.Vector3());
        let tip;
        if (spec.child && spec.probe !== 'tail' && !Array.isArray(spec.bone)) tip = wp(spec.child);
        else if (Array.isArray(spec.bone) && spec.child) tip = wp(spec.child);
        else tip = b.localToWorld(new THREE.Vector3(0, 0.1, 0));
        const boneDir = tip.sub(head).normalize();
        let worldAxis;
        if (spec.twist) {
          worldAxis = boneDir.clone().multiplyScalar(side === 'R' ? -1 : 1);
        } else {
          let dir;
          if (/^(wrist_flexion|finger\d_\d_flexion)/.test(name)) dir = palm[side].clone();
          else dir = new THREE.Vector3(...spec.dir).normalize();
          worldAxis = boneDir.clone().cross(dir);
          if (worldAxis.lengthSq() < 1e-6) worldAxis.set(1, 0, 0);
          worldAxis.normalize();
        }
        const wq = b.getWorldQuaternion(new THREE.Quaternion());
        out.push({ axis: worldAxis.applyQuaternion(wq.invert()).normalize() });
      }
      this.dofAxes[name] = out;
    }
    // bind-pose anatomical angles (MakeHuman rest has bent elbows ~46 deg): DOF values are absolute anatomical
    // angles, the applied rotation is (value - rest)
    this.dofRest = {};
    const ang = (a, b, c) => { const u = wp(b).sub(wp(a)).normalize(), v = wp(c).sub(wp(b)).normalize(); return Math.acos(Math.max(-1, Math.min(1, u.dot(v)))) * 180 / Math.PI; };
    for (const s of ['L', 'R']) {
      this.dofRest[`elbow_flexion_${s}`] = ang(`upperarm01.${s}`, `lowerarm01.${s}`, `wrist.${s}`);
      this.dofRest[`knee_flexion_${s}`] = ang(`upperleg01.${s}`, `lowerleg01.${s}`, `foot.${s}`);
    }
  }

  // ---------------------------------------------------------------- layers
  setLayer(name, values, weight = 1) { this.layers.set(name, { values, weight }); }
  clearLayer(name) { this.layers.delete(name); }

  // compose all layers -> bone local rotations
  applyPose() {
    const v = {};
    for (const { values, weight } of this.layers.values()) {
      if (weight <= 0) continue;
      for (const [k, a] of Object.entries(values)) v[k] = (v[k] || 0) + a * weight;
    }
    for (const [k, a] of Object.entries(this.manualDof || {})) if (a !== null && a !== undefined) v[k] = a;
    // clamp to anatomical range
    for (const k of Object.keys(v)) {
      const sp = this.dofs[k];
      if (sp) v[k] = Math.max(sp.limit[0], Math.min(sp.limit[1], v[k]));
    }
    for (const k of Object.keys(this.dofRest || {})) if (!(k in v)) v[k] = 0;
    this.dofValues = v;
    // reset bones
    for (const [n, b] of Object.entries(this.bones)) { b.quaternion.copy(this.restQuat[n]); b.position.copy(this.restPos[n]); }
    const axes = { x: new THREE.Vector3(1, 0, 0), y: new THREE.Vector3(0, 1, 0), z: new THREE.Vector3(0, 0, 1) };
    const q = new THREE.Quaternion();
    // deterministic order: twist after swing
    const order = Object.keys(v).sort((a, b) => (this.dofs[a]?.twist ? 1 : 0) - (this.dofs[b]?.twist ? 1 : 0));
    for (const k of order) {
      const sp = this.dofs[k];
      const ax = this.dofAxes[k];
      if (!sp || !ax) continue;
      const bonesList = Array.isArray(sp.bone) ? sp.bone : [sp.bone];
      const split = sp.split || bonesList.map(() => 1);
      bonesList.forEach((bn, i) => {
        const b = this.bone(bn);
        const a = ax[i];
        if (!b || !a) return;
        b.quaternion.multiply(q.setFromAxisAngle(a.axis, (v[k] - (this.dofRest[k] || 0)) * split[i] * D2R));
      });
    }
    // raw manual joint overrides (local euler, degrees, relative to rest)
    for (const [bn, e] of Object.entries(this.manualJoint)) {
      const b = this.bone(bn);
      if (b && e) b.quaternion.copy(this.restQuat[b.name]).multiply(q.setFromEuler(new THREE.Euler(e.x * D2R, e.y * D2R, e.z * D2R, 'XYZ')));
    }
    const r = this.bone('root');
    if (r) r.position.add(this.rootOffsetLocal(this.rootOffset));
    this.model.updateMatrixWorld(true);
  }

  rootOffsetLocal(off) {
    // pelvis offset given in character space (m) -> root bone parent space
    const r = this.bone('root');
    const p = r.parent;
    const m = new THREE.Matrix4().copy(p.matrixWorld).invert();
    const w0 = this.root.localToWorld(new THREE.Vector3(0, 0, 0));
    const w1 = this.root.localToWorld(off.clone());
    return w1.applyMatrix4(m).sub(w0.applyMatrix4(m));
  }

  // ---------------------------------------------------------------- morphs
  setMorph(name, w) {
    const list = this.morphTargets.get(name);
    if (!list) return false;
    for (const [m, i] of list) m.morphTargetInfluences[i] = w;
    this.morphValues[name] = w;
    return true;
  }

  applyMorphs(faceWeights) {
    const all = { ...faceWeights };
    // pose-space correctives from final joint angles
    for (const [name, c] of Object.entries(this.meta.correctives || {})) {
      const side = name.endsWith('_L') ? 'L' : 'R';
      const map = { elbowFlex: `elbow_flexion_${side}`, kneeFlex: `knee_flexion_${side}`, shoulderUp: `shoulder_abduction_${side}`,
                    shoulderFwd: `shoulder_flexion_${side}`, hipFlex: `hip_flexion_${side}`, wristFlex: `wrist_flexion_${side}` };
      const key = Object.keys(map).find((k) => name.includes(k));
      const ang = (this.dofValues[map[key]] || 0) - ((this.dofRest || {})[map[key]] || 0);
      const base = key === 'shoulderUp' ? 45 : 0;   // rest A-pose already ~45 deg abducted
      all[name] = Math.max(0, Math.min(1, (ang - base) / (c.full_deg - base)));
    }
    for (const [k, v] of Object.entries(this.manualMorph)) if (v !== null && v !== undefined) all[k] = v;
    for (const name of this.morphNames) this.setMorph(name, all[name] || 0);
    // expression wrinkle maps
    const skin = this.materials.DH_Skin;
    if (skin) {
      const wd = this.meta.wrinkle_drivers;
      const w = ['wrinkle_forehead', 'wrinkle_glabella', 'wrinkle_crowsfeet', 'wrinkle_nasolabial'].map((k) =>
        Math.min(1, Object.entries(wd[k]).reduce((s, [m, f]) => s + (all[m] || 0) * f, 0) * 1.4));
      skin.userData.uniforms.uWrinkle.value.set(...w);
    }
  }

  // ---------------------------------------------------------------- eyes
  captureEyeBind() {
    this.eyeBind = {};
    for (const s of ['L', 'R']) {
      const b = this.bone(`eye.${s}`);
      this.eyeBind[s] = b.getWorldQuaternion(new THREE.Quaternion()).premultiply(this.root.quaternion.clone().invert()).invert();
    }
  }

  updateEyeUniforms() {
    const m = this.materials.DH_EyeSclera;
    if (!m) return;
    // the shader uses one set of axes; average both eyes (they differ by vergence only a few degrees)
    const q = this.bone('eye.L').getWorldQuaternion(new THREE.Quaternion()).multiply(this.eyeBind.L.clone().premultiply(new THREE.Quaternion()));
    const U = m.userData.uniforms;
    U.uEyeFwd.value.set(0, 0, 1).applyQuaternion(q);
    U.uEyeRight.value.set(1, 0, 0).applyQuaternion(q);
    U.uEyeUp.value.set(0, 1, 0).applyQuaternion(q);
  }

  setPupil(f) { const m = this.materials.DH_EyeSclera; if (m) m.userData.uniforms.uPupil.value = f; }

  measure() {
    const bb = new THREE.Box3().setFromObject(this.model);
    this.bounds = bb;
    this.heightM = bb.max.y - bb.min.y;
    const g = (n) => this.bone(n).getWorldPosition(new THREE.Vector3());
    this.legLength = g('upperleg01.L').distanceTo(g('lowerleg01.L')) + g('lowerleg01.L').distanceTo(g('foot.L'));
    this.hipHeight = g('upperleg01.L').y;
    this.ankleHeight = g('foot.L').y;
    this.armLength = g('upperarm01.L').distanceTo(g('lowerarm01.L')) + g('lowerarm01.L').distanceTo(g('wrist.L'));
  }

  // world-space helpers
  worldPos(boneName) { return this.bone(boneName).getWorldPosition(new THREE.Vector3()); }

  setLOD(level) {
    // LOD policy for this hero instance: disable expensive layers instead of swapping meshes
    for (const m of this.meshes) {
      const nm = m.userData.dhMaterial;
      if (level >= 1 && ['DH_EyeOcclusion', 'DH_TearFilm', 'DH_Caruncle'].includes(nm)) m.visible = false;
      else if (level >= 2 && ['DH_Eyelashes_Card', 'DH_Teeth', 'DH_Tongue', 'DH_Cornea'].includes(nm)) m.visible = false;
      else m.visible = true;
    }
    const skin = this.materials.DH_Skin;
    if (skin) skin.userData.uniforms.uMicroStrength.value = level === 0 ? 1 : 0;
    this.lod = level;
  }
}
