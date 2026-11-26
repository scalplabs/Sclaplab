// Facial behaviour: emotion profiles (FACS-informed ARKit weights), continuous blending, micro-expressions,
// swallowing, and composition with speech / blink / gaze-lid layers.
import { Spring, organic } from './ik.js';

export const ARKIT = ['browDownLeft', 'browDownRight', 'browInnerUp', 'browOuterUpLeft', 'browOuterUpRight', 'cheekPuff',
  'cheekSquintLeft', 'cheekSquintRight', 'eyeBlinkLeft', 'eyeBlinkRight', 'eyeLookDownLeft', 'eyeLookDownRight',
  'eyeLookInLeft', 'eyeLookInRight', 'eyeLookOutLeft', 'eyeLookOutRight', 'eyeLookUpLeft', 'eyeLookUpRight',
  'eyeSquintLeft', 'eyeSquintRight', 'eyeWideLeft', 'eyeWideRight', 'jawForward', 'jawLeft', 'jawOpen', 'jawRight',
  'mouthClose', 'mouthDimpleLeft', 'mouthDimpleRight', 'mouthFrownLeft', 'mouthFrownRight', 'mouthFunnel', 'mouthLeft',
  'mouthLowerDownLeft', 'mouthLowerDownRight', 'mouthPressLeft', 'mouthPressRight', 'mouthPucker', 'mouthRight',
  'mouthRollLower', 'mouthRollUpper', 'mouthShrugLower', 'mouthShrugUpper', 'mouthSmileLeft', 'mouthSmileRight',
  'mouthStretchLeft', 'mouthStretchRight', 'noseSneerLeft', 'noseSneerRight', 'tongueOut'];

const B = (o) => { // expand symmetric keys "mouthSmile" -> Left/Right
  const r = {};
  for (const [k, v] of Object.entries(o)) {
    if (ARKIT.includes(k) || k.startsWith('tongue') || ['cheekSuck', 'nasolabialDeepen', 'chinDown'].includes(k)) r[k] = v;
    else { r[k + 'Left'] = v; r[k + 'Right'] = v; }
  }
  return r;
};

// Emotion profiles at 100 % intensity. body: posture DOFs (deg); phys: physiology modifiers.
export const EMOTIONS = {
  neutral: { face: {}, body: {}, phys: {} },
  joy: { face: B({ mouthSmile: 0.85, cheekSquint: 0.65, eyeSquint: 0.3, mouthDimple: 0.25, jawOpen: 0.06, browInnerUp: 0.08 }),
         body: { spine_flexion: -4, neck_flexion: -4 }, phys: { breath: 1.1, blink: 1.0, pupil: 0.04, flush: 0.15 } },
  sadness: { face: B({ browInnerUp: 0.8, browDown: 0.15, mouthFrown: 0.65, mouthShrugLower: 0.35, eyeSquint: 0.12, mouthPress: 0.15, eyeLookDown: 0.25 }),
             body: { spine_flexion: 10, neck_flexion: 14, clavicle_protraction_L: 6, clavicle_protraction_R: 6 }, phys: { breath: 0.8, blink: 0.8, gazeDown: 0.6 } },
  anger: { face: B({ browDown: 0.95, eyeSquint: 0.35, eyeWide: 0.12, noseSneer: 0.35, mouthPress: 0.55, mouthFrown: 0.25, jawForward: 0.1 }),
           body: { spine_flexion: 3, neck_flexion: 6, clavicle_elevation_L: 5, clavicle_elevation_R: 5 }, phys: { breath: 1.35, blink: 0.6, pupil: 0.08, flush: 0.5 } },
  fear: { face: B({ browInnerUp: 0.85, browOuterUp: 0.45, eyeWide: 0.85, mouthStretch: 0.55, jawOpen: 0.12 }),
          body: { spine_flexion: 6, neck_flexion: -6, clavicle_elevation_L: 10, clavicle_elevation_R: 10 }, phys: { breath: 1.6, blink: 1.3, pupil: 0.15 } },
  surprise: { face: B({ browInnerUp: 0.9, browOuterUp: 0.9, eyeWide: 0.9, jawOpen: 0.4, mouthFunnel: 0.12 }),
              body: { spine_flexion: -5, neck_flexion: -6 }, phys: { breath: 1.3, blink: 0.4, pupil: 0.12 } },
  disgust: { face: B({ noseSneer: 0.85, mouthUpperUp: 0.55, browDown: 0.45, cheekSquint: 0.3, mouthFrown: 0.3, mouthShrugLower: 0.25 }),
             body: { neck_flexion: -5, neck_rotation: 8, spine_flexion: -3 }, phys: { breath: 0.9 } },
  embarrassment: { face: { ...B({ eyeLookDown: 0.45, browInnerUp: 0.3, mouthPress: 0.3 }), mouthSmileLeft: 0.4, mouthSmileRight: 0.22 },
                   body: { neck_flexion: 12, neck_rotation: -10, spine_flexion: 4 }, phys: { flush: 0.85, blink: 1.4, gazeDown: 0.8 } },
  tension: { face: B({ mouthPress: 0.6, browDown: 0.25, browInnerUp: 0.3, eyeWide: 0.25, mouthStretch: 0.2 }),
             body: { clavicle_elevation_L: 8, clavicle_elevation_R: 8, spine_flexion: 2 }, phys: { breath: 1.3, blink: 1.25, pupil: 0.1 } },
  boredom: { face: { ...B({ eyeBlink: 0.32, mouthFrown: 0.15, browDown: 0.08 }), mouthLeft: 0.2 },
             body: { spine_flexion: 8, neck_lateral: 8, neck_flexion: 5 }, phys: { breath: 0.85, blink: 0.9, gazeWander: 1.6 } },
  focus: { face: B({ browDown: 0.35, eyeSquint: 0.3, mouthPress: 0.25, mouthRollLower: 0.1 }),
           body: { neck_flexion: 6, spine_flexion: 4 }, phys: { breath: 0.9, blink: 0.55, gazeWander: 0.3 } },
  doubt: { face: { browOuterUpLeft: 0.6, browInnerUp: 0.2, browDownRight: 0.5, eyeSquintRight: 0.4, mouthLeft: 0.3, mouthPressLeft: 0.35, mouthFrownLeft: 0.15 },
           body: { neck_lateral: -7, neck_rotation: 6 }, phys: { blink: 0.9 } },
  fatigue: { face: B({ eyeBlink: 0.38, browInnerUp: 0.2, jawOpen: 0.04, mouthFrown: 0.12 }),
             body: { spine_flexion: 12, neck_flexion: 10, clavicle_protraction_L: 8, clavicle_protraction_R: 8 }, phys: { breath: 0.85, blink: 1.6, slowBlink: 1 } },
};
export const EMOTION_KO = { joy: '기쁨', sadness: '슬픔', anger: '분노', fear: '공포', surprise: '놀람', disgust: '혐오',
  embarrassment: '당황', tension: '긴장', boredom: '지루함', focus: '집중', doubt: '의심', fatigue: '피곤함', neutral: '중립' };

export class FaceController {
  constructor(character) {
    this.ch = character;
    this.channels = {};
    this.springs = {};
    for (const n of character.morphNames) this.springs[n] = new Spring(0, 0.09);
    this.emotion = { name: 'neutral', intensity: 0 };
    this.mix = {};             // emotion name -> current weight (blended, so emotions cross-fade)
    this.mixSprings = {};
    this.expression = {};      // setExpression overrides (named ARKit weights, 0..1)
    this.micro = null;
    this.nextMicro = 2 + Math.random() * 4;
    this.nextSwallow = 25 + Math.random() * 40;
    this.swallowT = -1;
    this.t = 0;
  }

  setEmotion(name, intensity = 1, { blendTime = 0.6 } = {}) {
    if (!EMOTIONS[name]) throw new Error(`unknown emotion '${name}'`);
    this.emotion = { name, intensity: Math.max(0, Math.min(1, intensity)), blendTime };
    for (const k of Object.keys(EMOTIONS)) {
      if (!this.mixSprings[k]) this.mixSprings[k] = new Spring(0, blendTime / 2);
      this.mixSprings[k].h = blendTime / 2;
    }
  }

  emotionPhys() {
    const p = { breath: 1, blink: 1, pupil: 0, flush: 0, gazeDown: 0, gazeWander: 1, slowBlink: 0 };
    for (const [k, w] of Object.entries(this.mix)) {
      const ph = EMOTIONS[k].phys;
      for (const [pk, v] of Object.entries(ph)) {
        if (['breath', 'blink', 'gazeWander'].includes(pk)) p[pk] *= 1 + (v - 1) * w;
        else p[pk] += v * w;
      }
    }
    return p;
  }

  emotionBody() {
    const out = {};
    for (const [k, w] of Object.entries(this.mix)) for (const [d, a] of Object.entries(EMOTIONS[k].body)) out[d] = (out[d] || 0) + a * w;
    return out;
  }

  update(dt, layers) {
    this.t += dt;
    // emotion cross-fade
    for (const k of Object.keys(EMOTIONS)) {
      if (!this.mixSprings[k]) this.mixSprings[k] = new Spring(0, 0.3);
      const target = k === this.emotion.name ? this.emotion.intensity : 0;
      this.mix[k] = Math.max(0, this.mixSprings[k].update(target, dt));
    }
    const target = {};
    const add = (o, w = 1) => { for (const [k, v] of Object.entries(o)) target[k] = (target[k] || 0) + v * w; };
    for (const [k, w] of Object.entries(this.mix)) if (w > 1e-3) add(EMOTIONS[k].face, w);
    // living face: slow, low-amplitude organic drift of a few channels (no repetition)
    add({ browInnerUp: 0.03 * (organic(this.t, 1) + 0.5), mouthPressLeft: 0.04 * (organic(this.t, 2) + 0.6),
          mouthPressRight: 0.04 * (organic(this.t, 3) + 0.6), jawOpen: 0.012 * (organic(this.t, 4) + 1) });
    // micro-expressions: 120-450 ms flickers
    this.nextMicro -= dt;
    if (this.nextMicro <= 0 && !this.micro) {
      const pool = [{ browInnerUp: 0.25 }, { mouthPressLeft: 0.3 }, { noseSneerRight: 0.15 }, { browDownLeft: 0.2 },
                    { mouthSmileRight: 0.2 }, { cheekSquintLeft: 0.18 }, { mouthDimpleLeft: 0.25 }, { eyeSquintLeft: 0.2, eyeSquintRight: 0.15 }];
      this.micro = { shape: pool[Math.floor(Math.random() * pool.length)], t: 0, dur: 0.12 + Math.random() * 0.33 };
      this.nextMicro = 3 + Math.random() * 7;
    }
    if (this.micro) {
      this.micro.t += dt;
      const x = this.micro.t / this.micro.dur;
      if (x >= 1) this.micro = null;
      else add(this.micro.shape, Math.sin(Math.PI * x));
    }
    // swallowing (every ~30-70 s, suppressed while speaking)
    this.nextSwallow -= dt;
    if (this.nextSwallow <= 0 && !(layers.speech && layers.speech.active)) { this.swallowT = 0; this.nextSwallow = 30 + Math.random() * 40; }
    if (this.swallowT >= 0) {
      this.swallowT += dt;
      const x = this.swallowT / 0.9;
      if (x >= 1) this.swallowT = -1;
      else add({ mouthPressLeft: 0.5, mouthPressRight: 0.5, mouthRollLower: 0.2, chinDown: 0.35, tongueUp: 0.6 }, Math.sin(Math.PI * x));
    }
    // speech layer replaces mouth / jaw / tongue channels proportionally to speaking activity
    if (layers.speech) {
      const sp = layers.speech;
      const a = sp.activity || 0;
      for (const k of Object.keys(target)) {
        if (/^(mouth|jaw|tongue)/.test(k) && !/Smile|Frown|Dimple/.test(k)) target[k] *= 1 - 0.7 * a;
      }
      add(sp.weights || {});
    }
    if (layers.eyes) add(layers.eyes);     // blink + lid follow
    add(this.expression);
    // springs (blink/speech channels need faster response)
    const out = {};
    for (const n of this.ch.morphNames) {
      if (n.startsWith('corr_')) continue;
      const fast = /Blink|jaw|mouth|tongue/.test(n);
      const s = this.springs[n];
      s.h = /Blink/.test(n) ? 0.012 : fast ? 0.035 : 0.09;
      out[n] = Math.max(n === 'mouthClose' ? -1 : 0, Math.min(1, s.update(target[n] || 0, dt)));
    }
    this.weights = out;
    return out;
  }
}
