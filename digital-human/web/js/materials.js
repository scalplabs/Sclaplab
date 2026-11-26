// Material system for the realtime digital human (three.js r170, WebGL2).
// Binds custom shaders to GLB placeholder materials by name (see rig_meta.json "materials").
import * as THREE from '../vendor/three/three.module.js';

const loader = new THREE.TextureLoader();
const texCache = new Map();

export function tex(url, { srgb = false, repeat = false, aniso = 8 } = {}) {
  const key = url + srgb + repeat;
  if (texCache.has(key)) return texCache.get(key);
  const t = loader.load(url);
  t.flipY = false; // glTF UV convention
  t.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  t.anisotropy = aniso;
  if (repeat) { t.wrapS = t.wrapT = THREE.RepeatWrapping; }
  texCache.set(key, t);
  return t;
}

// ----------------------------------------------------------------------------- SKIN
export function makeSkinMaterial(base, quality = 'hq') {
  const T = base + '/textures/';
  const hi = quality === 'hq';
  const m = new THREE.MeshPhysicalMaterial({
    map: tex(T + (hi ? 'skin_albedo_4k.jpg' : 'skin_albedo_2k.jpg'), { srgb: true }),
    normalMap: tex(T + 'skin_normal_2k.jpg'),
    roughness: 0.5, metalness: 0, ior: 1.4, specularIntensity: 1.0, normalScale: new THREE.Vector2(0.65, 0.65),
    clearcoat: 0.2, clearcoatRoughness: 0.38,
    sheen: 0.12, sheenRoughness: 0.6, sheenColor: new THREE.Color(0.9, 0.82, 0.78),
  });
  m.name = 'skin';
  const U = {
    tRoughSpec: { value: tex(T + 'skin_rough_spec_2k.png') },
    tMasks: { value: tex(T + 'skin_masks_2k.png') },
    tWrinkleN: { value: tex(T + 'skin_wrinkle_normal_2k.jpg') },
    tWrinkleMask: { value: tex(T + 'skin_wrinkle_mask_1k.png') },
    tMicroN: { value: tex(T + 'skin_micro_normal.jpg', { repeat: true }) },
    uWrinkle: { value: new THREE.Vector4() },        // forehead, glabella, crow's feet, nasolabial
    uMicroScale: { value: 15.0 },
    uMicroStrength: { value: 1.0 },
    uSSSWrap: { value: new THREE.Vector3(0.55, 0.25, 0.14) },   // per-channel diffuse wrap (red scatters furthest)
    uSSSNormalMix: { value: new THREE.Vector3(0.25, 0.65, 0.95) }, // detail-normal weight per channel
    uTransColor: { value: new THREE.Color(1.0, 0.22, 0.12) },
    uTransStrength: { value: 0.9 },
    uFlush: { value: 0.0 },                           // emotional blush / exertion redness
    uDebug: { value: 0 },                             // 0 lit, 1 albedo, 2 normal, 3 roughness, 4 sss mask
  };
  m.userData.uniforms = U;
  m.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, U);
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', `#include <common>
        uniform sampler2D tRoughSpec, tMasks, tWrinkleN, tWrinkleMask, tMicroN;
        uniform vec4 uWrinkle; uniform float uMicroScale, uMicroStrength, uTransStrength, uFlush; uniform int uDebug;
        uniform vec3 uSSSWrap, uSSSNormalMix, uTransColor;
        vec3 skinGeoN; float skinThin; vec4 skinMasks; vec4 skinRS;`)
      .replace('#include <normal_fragment_begin>', `#include <normal_fragment_begin>
        skinGeoN = normal;`)
      .replace('vec3 mapN = texture2D( normalMap, vNormalMapUv ).xyz * 2.0 - 1.0;', `
        skinMasks = texture2D(tMasks, vNormalMapUv);
        skinRS = texture2D(tRoughSpec, vNormalMapUv);
        skinThin = skinRS.a;
        float wk = clamp(dot(texture2D(tWrinkleMask, vNormalMapUv), uWrinkle), 0.0, 1.0);
        vec3 nA = texture2D(normalMap, vNormalMapUv).xyz * 2.0 - 1.0;
        vec3 nW = texture2D(tWrinkleN, vNormalMapUv).xyz * 2.0 - 1.0;
        vec3 macroN = normalize(mix(nA, nW, wk));
        vec3 microN = texture2D(tMicroN, vNormalMapUv * uMicroScale).xyz * 2.0 - 1.0;
        microN.xy *= skinMasks.r * uMicroStrength;
        // reoriented normal mapping (macro + micro)
        vec3 t = macroN + vec3(0.0, 0.0, 1.0); vec3 u = microN * vec3(-1.0, -1.0, 1.0);
        vec3 mapN = normalize(t * dot(t, u) - u * t.z);`)
      .replace('#include <lights_physical_fragment>', `#include <lights_physical_fragment>
        material.roughness = clamp(skinRS.r * mix(1.2, 1.0, texture2D(tMicroN, vNormalMapUv * uMicroScale).z) + 0.06, 0.34, 1.0);
        material.specularColor *= (0.25 + 0.9 * skinRS.g) * (0.55 + 0.45 * skinRS.b);
        #ifdef USE_CLEARCOAT
          material.clearcoat = skinMasks.a * 0.3;
        #endif
        material.diffuseColor *= mix(vec3(1.0), vec3(1.08, 0.86, 0.86), uFlush * (0.4 + 0.6 * skinRS.a));
        // scalp under the hair cards: hair-coloured cap (hides card gaps, like painted root shadow)
        material.diffuseColor = mix(material.diffuseColor, vec3(0.018, 0.013, 0.010), smoothstep(0.35, 0.8, skinMasks.b) * 0.92);`)
      .replace('reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );', `
        // --- subsurface approximation: per-channel bent normals + wrapped lighting
        vec3 Nr = normalize(mix(skinGeoN, geometryNormal, uSSSNormalMix.r));
        vec3 Ng = normalize(mix(skinGeoN, geometryNormal, uSSSNormalMix.g));
        vec3 Nb = normalize(mix(skinGeoN, geometryNormal, uSSSNormalMix.b));
        vec3 ndl = vec3(dot(Nr, directLight.direction), dot(Ng, directLight.direction), dot(Nb, directLight.direction));
        vec3 wrapD = clamp((ndl + uSSSWrap) / (1.0 + uSSSWrap), 0.0, 1.0);
        wrapD *= wrapD * (3.0 - 2.0 * wrapD) * 0.35 + wrapD * 0.65;
        reflectedLight.directDiffuse += wrapD * directLight.color * BRDF_Lambert( material.diffuseColor );
        // --- transmission through thin tissue (ears, nostrils, eyelids, fingers)
        vec3 Lt = normalize(directLight.direction + skinGeoN * 0.35);
        float tr = pow(clamp(dot(geometryViewDir, -Lt), 0.0, 1.0), 3.0) * smoothstep(0.25, 0.85, skinThin);
        reflectedLight.directDiffuse += tr * uTransStrength * directLight.color * uTransColor * material.diffuseColor;`)
      .replace('#include <dithering_fragment>', `#include <dithering_fragment>
        if (uDebug == 1) gl_FragColor = vec4(diffuseColor.rgb, 1.0);
        else if (uDebug == 2) gl_FragColor = vec4(normal * 0.5 + 0.5, 1.0);
        else if (uDebug == 3) gl_FragColor = vec4(vec3(material.roughness), 1.0);
        else if (uDebug == 4) gl_FragColor = vec4(skinMasks.rgb, 1.0);`);
  };
  m.customProgramCacheKey = () => 'dh_skin';
  return m;
}

// ----------------------------------------------------------------------------- EYES
export function makeEyeMaterial(base, eyeMeta) {
  const T = base + '/textures/';
  const m = new THREE.MeshPhysicalMaterial({
    map: tex(T + 'eye_albedo_2k.jpg', { srgb: true }), normalMap: tex(T + 'eye_normal_1k.jpg'),
    roughness: 0.32, ior: 1.376, specularIntensity: 0.4, sheen: 0,
  });
  m.name = 'eye';
  const U = {
    uPupil: { value: 0.36 },                       // pupil diameter fraction of iris
    uPupil0: { value: eyeMeta.pupil_fraction_nominal },
    uIrisUV: { value: eyeMeta.iris_uv_radius },
    uIrisRadius: { value: eyeMeta.iris_diameter_m / 2 },
    uChamber: { value: 0.0026 },                   // anterior chamber depth at the axis (m)
    uEyeFwd: { value: new THREE.Vector3(0, 0, 1) },
    uEyeRight: { value: new THREE.Vector3(1, 0, 0) },
    uEyeUp: { value: new THREE.Vector3(0, 1, 0) },
  };
  m.userData.uniforms = U;
  m.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, U);
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec3 vWPos;')
      .replace('#include <worldpos_vertex>', '#include <worldpos_vertex>\nvWPos = (modelMatrix * vec4(transformed,1.0)).xyz;');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', `#include <common>
        varying vec3 vWPos;
        uniform float uPupil, uPupil0, uIrisUV, uIrisRadius, uChamber;
        uniform vec3 uEyeFwd, uEyeRight, uEyeUp;
        vec2 eyeUV(vec2 uv) {
          // refraction parallax through the cornea + physiological pupil dilation
          vec2 d = uv - 0.5; float r = length(d) / uIrisUV;
          if (r < 1.0) {
            vec3 V = normalize(cameraPosition - vWPos);
            vec3 Vl = vec3(dot(V, uEyeRight), dot(V, uEyeUp), dot(V, uEyeFwd));
            vec3 Nc = normalize(vec3(d / uIrisUV * 0.55, 1.0));
            vec3 Tr = refract(-Vl, Nc, 1.0 / 1.376);
            float h = uChamber * (1.0 - r * r);
            vec2 off = Tr.xy / max(-Tr.z, 0.2) * h;      // metres in iris plane
            d += off / uIrisRadius * uIrisUV;
            r = length(d) / uIrisUV;
            float rr;
            if (r < uPupil) rr = r / uPupil * uPupil0;
            else rr = uPupil0 + (r - uPupil) / (1.0 - uPupil) * (1.0 - uPupil0);
            if (r < 1.0) d = (r > 1e-5 ? d / r : d) * rr * uIrisUV;
          }
          return 0.5 + d;
        }`)
      .replace('#include <map_fragment>', `
        vec4 sampledDiffuseColor = texture2D(map, eyeUV(vMapUv));
        if (length(vMapUv - 0.5) < uIrisUV) sampledDiffuseColor.rgb *= 1.75;   // iris albedo boost (thin stroma scatters)
        diffuseColor *= sampledDiffuseColor;`);
  };
  m.customProgramCacheKey = () => 'dh_eye';
  return m;
}

export function makeCorneaMaterial(quality = 'hq') {
  if (quality !== 'hq') {   // realtime LOD: specular-only coat (no screen-space transmission pass)
    return new THREE.MeshPhysicalMaterial({ name: 'cornea', color: 0x000000, roughness: 0.03, ior: 1.376, specularIntensity: 1.0,
      transparent: true, opacity: 0.18, depthWrite: false, envMapIntensity: 1.5, premultipliedAlpha: true });
  }
  return new THREE.MeshPhysicalMaterial({
    name: 'cornea', color: 0xffffff, transmission: 1.0, thickness: 0.0005, roughness: 0.0, ior: 1.376,
    specularIntensity: 1.0, transparent: true, depthWrite: false, envMapIntensity: 1.4,
  });
}

export function makeTearMaterial(quality = 'hq') {
  if (quality !== 'hq') {
    return new THREE.MeshPhysicalMaterial({ name: 'tearfilm', color: 0x000000, roughness: 0.03, transparent: true, opacity: 0.25, depthWrite: false, envMapIntensity: 1.6 });
  }
  return new THREE.MeshPhysicalMaterial({
    name: 'tearfilm', color: 0xffffff, transmission: 1.0, thickness: 0.0002, roughness: 0.02, ior: 1.336,
    transparent: true, depthWrite: false, envMapIntensity: 1.6,
  });
}

export function makeEyeOcclusionMaterial() {
  const m = new THREE.ShaderMaterial({
    name: 'eye_occlusion', transparent: true, depthWrite: false,
    uniforms: { uStrength: { value: 0.75 } },
    vertexShader: `#include <common>
      #include <skinning_pars_vertex>
      #include <morphtarget_pars_vertex>
      varying vec2 vUv;
      void main(){ vUv = uv;
        #include <skinbase_vertex>
        #include <begin_vertex>
        #include <morphtarget_vertex>
        #include <skinning_vertex>
        gl_Position = projectionMatrix * modelViewMatrix * vec4(transformed, 1.0); }`,
    fragmentShader: `uniform float uStrength; varying vec2 vUv;
      void main(){ float a = pow(1.0 - clamp(vUv.y, 0.0, 1.0), 2.2) * uStrength; gl_FragColor = vec4(0.05, 0.03, 0.03, a); }`,
  });
  return m;
}

// ----------------------------------------------------------------------------- HAIR / CARDS
export function makeHairCardMaterial(url, color = 0x1a120d) {
  const m = new THREE.MeshPhysicalMaterial({
    name: 'hair_cards', map: tex(url, { srgb: true }), color, alphaTest: 0.3, side: THREE.DoubleSide,
    roughness: 0.5, anisotropy: 0.7, anisotropyRotation: Math.PI / 2, sheen: 0.15, sheenRoughness: 0.5,
    sheenColor: new THREE.Color(0.12, 0.08, 0.06), specularIntensity: 0.5,
  });
  m.alphaToCoverage = true;
  return m;
}

export function makeCardMaterial(url, name, tint = 0x2a1d16, alphaTest = 0.45) {
  const m = new THREE.MeshStandardMaterial({ name, map: tex(url, { srgb: true }), color: tint, alphaTest,
                                             side: THREE.DoubleSide, roughness: 0.55, transparent: false });
  m.alphaToCoverage = true;
  return m;
}

export function makeTeethMaterial(base) {
  return new THREE.MeshPhysicalMaterial({ name: 'teeth', map: tex(base + '/textures/teeth.png', { srgb: true }),
    roughness: 0.2, clearcoat: 0.6, clearcoatRoughness: 0.1, sheen: 0.2, envMapIntensity: 0.6 });
}
export function makeTongueMaterial(base) {
  return new THREE.MeshPhysicalMaterial({ name: 'tongue', map: tex(base + '/textures/tongue.png', { srgb: true }),
    roughness: 0.35, clearcoat: 0.8, clearcoatRoughness: 0.2, envMapIntensity: 0.4 });
}
export function makeCaruncleMaterial() {
  return new THREE.MeshPhysicalMaterial({ name: 'caruncle', color: 0xb5615c, roughness: 0.15, clearcoat: 1.0 });
}
export function makeClothMaterial(base) {
  const T = base + '/textures/';
  const ao = tex(T + 'shirt_jeans_ao.jpg');
  const m = new THREE.MeshPhysicalMaterial({ name: 'cloth', map: tex(T + 'shirt_jeans_diffuse.jpg', { srgb: true }),
    normalMap: tex(T + 'shirt_jeans_normal.jpg'), aoMap: ao, aoMapIntensity: 0.9, roughness: 0.85,
    sheen: 0.6, sheenRoughness: 0.75, sheenColor: new THREE.Color(0.5, 0.55, 0.65) });
  return m;
}
export function makeShoeMaterial(base) {
  return new THREE.MeshPhysicalMaterial({ name: 'shoes', map: tex(base + '/textures/shoes_diffuse.jpg', { srgb: true }),
    roughness: 0.55, clearcoat: 0.2 });
}
