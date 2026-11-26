// Phoneme-timed lip-sync with coarticulation (Cohen-Massaro dominance model), speech-rate adaptation,
// stress emphasis, pre-utterance inhalation and audio-clock synchronisation.
// Input: server /api/tts result {audio_url, phones:[{p,start,end,viseme,stress,word}], words, energy}.

export const VISEMES = {
  sil: {},
  PP: { jawOpen: 0.06, mouthClose: 0.06, mouthPressLeft: 0.35, mouthPressRight: 0.35, mouthRollLower: 0.12, mouthRollUpper: 0.08 },
  FF: { jawOpen: 0.08, mouthRollLower: 0.6, mouthUpperUpLeft: 0.18, mouthUpperUpRight: 0.18, mouthShrugUpper: 0.1 },
  TH: { jawOpen: 0.16, tongueOut: 0.3, mouthStretchLeft: 0.1, mouthStretchRight: 0.1 },
  DD: { jawOpen: 0.2, tongueTipUp: 0.65, mouthStretchLeft: 0.12, mouthStretchRight: 0.12 },
  kk: { jawOpen: 0.22, tongueUp: 0.55, mouthStretchLeft: 0.08, mouthStretchRight: 0.08 },
  CH: { jawOpen: 0.12, mouthFunnel: 0.55, mouthPucker: 0.2, mouthShrugUpper: 0.2, tongueTipUp: 0.3 },
  SS: { jawOpen: 0.06, mouthStretchLeft: 0.32, mouthStretchRight: 0.32, mouthSmileLeft: 0.1, mouthSmileRight: 0.1, tongueTipUp: 0.3 },
  nn: { jawOpen: 0.14, tongueTipUp: 0.75 },
  RR: { jawOpen: 0.13, mouthFunnel: 0.35, mouthPucker: 0.25 },
  aa: { jawOpen: 0.62, mouthLowerDownLeft: 0.25, mouthLowerDownRight: 0.25, mouthStretchLeft: 0.08, mouthStretchRight: 0.08 },
  E: { jawOpen: 0.36, mouthStretchLeft: 0.32, mouthStretchRight: 0.32, mouthSmileLeft: 0.12, mouthSmileRight: 0.12, mouthLowerDownLeft: 0.15, mouthLowerDownRight: 0.15 },
  I: { jawOpen: 0.16, mouthStretchLeft: 0.45, mouthStretchRight: 0.45, mouthSmileLeft: 0.22, mouthSmileRight: 0.22 },
  O: { jawOpen: 0.4, mouthFunnel: 0.6, mouthPucker: 0.25 },
  U: { jawOpen: 0.12, mouthPucker: 0.85, mouthFunnel: 0.3 },
};
// dominance (how strongly a segment imposes its target on neighbours) per articulator group
const DOM = {
  //       lips  jaw  tongue
  sil: [0.6, 0.6, 0.5], PP: [1.0, 0.5, 0.2], FF: [0.95, 0.45, 0.2], TH: [0.3, 0.5, 0.9], DD: [0.25, 0.5, 0.95],
  kk: [0.2, 0.45, 0.9], CH: [0.85, 0.45, 0.7], SS: [0.6, 0.6, 0.7], nn: [0.2, 0.4, 0.9], RR: [0.7, 0.4, 0.6],
  aa: [0.45, 1.0, 0.3], E: [0.6, 0.85, 0.3], I: [0.65, 0.7, 0.3], O: [0.9, 0.8, 0.3], U: [0.95, 0.6, 0.3],
};
const groupOf = (k) => (k.startsWith('tongue') ? 2 : k === 'jawOpen' ? 1 : 0);

export class LipSync {
  constructor() {
    this.ctx = null;
    this.active = false;
    this.track = null;
    this.weights = {};
    this.activity = 0;
    this.listeners = [];
  }

  async _ensureCtx() {
    if (!this.ctx) this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (this.ctx.state === 'suspended') await this.ctx.resume();
  }

  // Prepare segments: phone list -> segments with centres, durations, targets, dominance
  prepare(speech) {
    const ph = speech.phones || [];
    const avgDur = ph.length ? ph.reduce((s, p) => s + (p.end - p.start), 0) / ph.length : 0.08;
    const rateScale = Math.min(1.15, Math.max(0.7, avgDur / 0.085));   // fast speech -> hypo-articulation
    const segs = [];
    let prevEnd = 0;
    for (const p of ph) {
      if (p.start - prevEnd > 0.12) segs.push({ v: 'sil', c: (prevEnd + p.start) / 2, d: p.start - prevEnd, stress: 0 });
      segs.push({ v: p.viseme in VISEMES ? p.viseme : 'DD', c: (p.start + p.end) / 2, d: Math.max(0.03, p.end - p.start),
                  stress: p.stress || 0, p: p.p });
      prevEnd = p.end;
    }
    segs.push({ v: 'sil', c: prevEnd + 0.15, d: 0.3, stress: 0 });
    segs.unshift({ v: 'sil', c: (ph[0]?.start || 0) - 0.15, d: 0.3, stress: 0 });
    // stressed words: English primary stress (2); Korean: phrase-initial syllables of each word get mild stress
    return { segs, rateScale, words: speech.words || [], energy: speech.energy || [], duration: speech.duration || prevEnd };
  }

  evaluate(track, t) {
    const out = {};
    const num = {}, den = [1e-4, 1e-4, 1e-4];
    const keysSeen = new Set();
    const contributions = [];
    for (const s of track.segs) {
      const dt = Math.abs(t - s.c);
      if (dt > 0.5) continue;
      const th = 1 / Math.max(0.035, s.d * 0.75);
      const dom = DOM[s.v] || [0.5, 0.5, 0.5];
      const D = [0, 1, 2].map((g) => dom[g] * Math.exp(-th * dt * (g === 0 && (s.v === 'PP' || s.v === 'FF') ? 0.8 : 1)));
      contributions.push([s, D]);
      for (let g = 0; g < 3; g++) den[g] += D[g];
      for (const k of Object.keys(VISEMES[s.v])) keysSeen.add(k);
    }
    for (const k of keysSeen) {
      const g = groupOf(k);
      let n = 0;
      for (const [s, D] of contributions) {
        let v = VISEMES[s.v][k] || 0;
        if (k === 'jawOpen') v *= track.rateScale * (s.stress === 2 ? 1.2 : 1);
        n += D[g] * v;
      }
      num[k] = n;
      out[k] = n / den[g];
    }
    // bilabial closure guarantee: when a PP/FF centre is within its own duration, enforce closure
    for (const [s] of contributions) {
      // lips start closing before the acoustic segment (anticipatory coarticulation, ~60-90 ms)
      if (s.v === 'PP' && t > s.c - s.d * 0.5 - 0.07 && t < s.c + s.d * 0.4) {
        out.jawOpen = Math.min(out.jawOpen || 0, 0.07);
        out.mouthPressLeft = Math.max(out.mouthPressLeft || 0, 0.3);
        out.mouthPressRight = Math.max(out.mouthPressRight || 0, 0.3);
      }
    }
    return out;
  }

  /** Speak a prepared speech result. Returns a promise resolved when audio finishes. */
  async play(speech, { onWord, onStart, preBreath = 0.35, baseUrl = '' } = {}) {
    if (this.clock) {   // virtual clock (deterministic capture): no audio output, time from the simulation
      this.track = this.prepare(speech);
      this.startAt = this.clock() + preBreath; this.breathIn = preBreath; this.active = true;
      this._wordIdx = 0; this.onWord = onWord; onStart && onStart();
      this.virtualStart = this.startAt;
      return new Promise((resolve) => { this._virtualResolve = resolve; });
    }
    await this._ensureCtx();
    const res = await fetch(baseUrl + speech.audio_url);
    const buf = await this.ctx.decodeAudioData(await res.arrayBuffer());
    this.track = this.prepare(speech);
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    const gain = this.ctx.createGain();
    src.connect(gain).connect(this.ctx.destination);
    this.analyser = this.ctx.createAnalyser();
    gain.connect(this.analyser);
    const startAt = this.ctx.currentTime + preBreath;
    src.start(startAt);
    this.startAt = startAt;
    this.breathIn = preBreath;
    this.active = true;
    this.src = src;
    onStart && onStart();
    this._wordIdx = 0;
    this.onWord = onWord;
    return new Promise((resolve) => { src.onended = () => { this.active = false; this.activity = 0; resolve(); }; });
  }

  stop() { if (this.src) try { this.src.stop(); } catch (e) { /* ended */ } this.active = false; }

  // speechSynthesis fallback (no server): timing ESTIMATED from text length -> marked approximate
  async speakFallback(text, lang = 'ko') {
    const est = estimatePhones(text, lang);
    this.track = this.prepare(est);
    const u = new SpeechSynthesisUtterance(text);
    u.lang = lang === 'ko' ? 'ko-KR' : 'en-US';
    this.active = true;
    this.startAt = (this.ctx ? this.ctx.currentTime : performance.now() / 1000);
    this._clock = () => performance.now() / 1000;
    this._t0 = this._clock();
    speechSynthesis.speak(u);
    return new Promise((r) => { u.onend = () => { this.active = false; r(); }; });
  }

  time() {
    if (this.clock && this.virtualStart !== undefined) return this.clock() - this.virtualStart;
    if (this._clock) return this._clock() - this._t0;
    return this.ctx ? this.ctx.currentTime - this.startAt : 0;
  }

  update() {
    if (!this.active || !this.track) { this.weights = {}; this.activity = Math.max(0, this.activity - 0.05); return; }
    const t = this.time();
    if (t < 0) {      // inhalation before speaking: lips part slightly
      const x = 1 + t / this.breathIn;
      this.weights = { jawOpen: 0.07 * Math.sin(Math.PI * Math.min(1, x)), mouthClose: 0 };
      this.activity = 0.3;
      this.breathing = true;
      return;
    }
    this.breathing = false;
    if (this._virtualResolve && t > this.track.duration + 0.05) {
      this.active = false; const r = this._virtualResolve; this._virtualResolve = null; this.virtualStart = undefined; r(); this.weights = {}; return;
    }
    this.weights = this.evaluate(this.track, t);
    this.activity = 1;
    const w = this.track.words;
    while (this._wordIdx < w.length && w[this._wordIdx].start <= t) {
      this.onWord && this.onWord(w[this._wordIdx]);
      this._wordIdx++;
    }
    const e = this.track.energy;
    this.energy = e.length ? e[Math.min(e.length - 1, Math.floor(t * 50))] || 0 : 0;
  }
}

// rough phone estimate for the browser TTS fallback (approximate; documented limitation)
export function estimatePhones(text, lang) {
  const chars = [...text];
  const per = lang === 'ko' ? 0.18 : 0.075;
  const phones = [];
  let t = 0.1, wi = 0;
  for (const c of chars) {
    if (/\s/.test(c)) { wi++; t += 0.05; continue; }
    if (/[.,!?]/.test(c)) { t += 0.25; continue; }
    const vowel = /[aeiouAEIOU아어오우으이애에]/.test(c);
    const vis = lang === 'ko' ? ['aa', 'E', 'O', 'U', 'I', 'nn', 'PP', 'DD'][c.charCodeAt(0) % 8] : vowel ? 'aa' : 'DD';
    phones.push({ p: c, start: t, end: t + per, viseme: vis, stress: 0, word: wi });
    t += per;
  }
  return { phones, words: [], energy: [], duration: t };
}
