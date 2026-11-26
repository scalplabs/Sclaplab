// Behaviour AI: state model, needs dynamics, perception/attention, memory, utility-based goal selection
// and a behaviour state machine. Decisions are executed through the public API (decoupled from animation).
import * as THREE from '../vendor/three/three.module.js';

export function defaultState(cfg = {}) {
  return {
    name: cfg.name || 'Kim Min-jun', age: cfg.age || 30, id: cfg.id || 'minjun',
    personality: cfg.personality || { openness: 0.72, conscientiousness: 0.64, extraversion: 0.48, agreeableness: 0.7, neuroticism: 0.3 },
    emotion: { name: 'neutral', intensity: 0 },
    mood: { valence: 0.2, arousal: 0.3 },          // slow-moving affect (PAD-like)
    fatigue: 0.15, hunger: 0.2, thirst: 0.25, focus: 0.6, stress: 0.2,
    attention: null,                                // id / 'user'
    currentAction: 'idle', goal: null, goalQueue: [],
    relationships: { user: { familiarity: 0.1, trust: 0.5, affinity: 0.5, name: null } },
    memory: [],                                     // {t, kind, text, tags, importance}
    conversation: [],                               // {role, text, t}
    location: { x: 0, y: 0, z: 0, area: 'room' },
    perception: { visible: [], userPresent: true, userDistance: 2.2 },
    autonomous: true,
  };
}

export class Mind {
  constructor(api, cfg) {
    this.api = api;
    this.s = defaultState(cfg);
    this.t = 0;
    this.decideEvery = 0.5;      // AI update scheduling (s); crowd agents use larger intervals
    this.acc = 0;
    this.busy = false;
    this.lastEmotionT = 0;
    this.log = [];
  }

  // ------------------------------------------------------------------ memory
  remember(text, { kind = 'episodic', tags = [], importance = 0.5 } = {}) {
    const m = { t: Date.now(), kind, text: String(text), tags, importance };
    this.s.memory.push(m);
    if (this.s.memory.length > 500) {           // forget least important old items
      this.s.memory.sort((a, b) => b.importance - a.importance || b.t - a.t);
      this.s.memory.length = 400;
    }
    return m;
  }

  recall(query, k = 5) {
    const q = String(query).toLowerCase().split(/[\s,.!?]+/).filter((w) => w.length > 1);
    const now = Date.now();
    const scored = this.s.memory.map((m) => {
      const txt = (m.text + ' ' + m.tags.join(' ')).toLowerCase();
      let rel = 0;
      for (const w of q) if (txt.includes(w)) rel += 1;
      // also match on character n-grams (Korean morphology)
      for (const w of q) for (let i = 0; i + 2 <= w.length; i++) if (txt.includes(w.slice(i, i + 2))) rel += 0.15;
      const rec = Math.exp(-(now - m.t) / (1000 * 3600 * 24));
      return { m, score: rel * 1.0 + 0.3 * rec + 0.4 * m.importance };
    }).filter((x) => x.score > 0.45);
    scored.sort((a, b) => b.score - a.score);
    return scored.slice(0, k).map((x) => x.m);
  }

  // ------------------------------------------------------------------ needs & affect dynamics
  _dynamics(dt) {
    const s = this.s, b = this.api.body;
    const moving = b.vel.length();
    s.fatigue = clamp01(s.fatigue + dt * (0.00025 + 0.0012 * moving * moving / 4) - (b.posture === 'sit' || b.posture === 'lie' ? dt * 0.0015 : 0));
    s.hunger = clamp01(s.hunger + dt * 0.00012);
    s.thirst = clamp01(s.thirst + dt * (0.00018 + 0.0006 * moving / 3));
    s.stress = clamp01(s.stress + dt * (s.emotion.name === 'anger' || s.emotion.name === 'fear' ? 0.004 : -0.0008));
    s.focus = clamp01(s.focus + dt * (s.attention ? 0.001 : -0.0006) - s.fatigue * dt * 0.0005);
    // mood drifts toward emotion valence
    const val = { joy: 0.8, surprise: 0.2, neutral: 0, focus: 0.1, sadness: -0.7, anger: -0.6, fear: -0.6, disgust: -0.5,
                  embarrassment: -0.2, tension: -0.3, boredom: -0.2, doubt: -0.1, fatigue: -0.3 }[s.emotion.name] || 0;
    s.mood.valence += (val * s.emotion.intensity - s.mood.valence) * dt * 0.02;
    s.mood.arousal += ((s.emotion.intensity * 0.7 + s.stress * 0.3) - s.mood.arousal) * dt * 0.03;
    const p = b.pos;
    s.location = { x: +p.x.toFixed(2), y: +p.y.toFixed(2), z: +p.z.toFixed(2), area: Math.hypot(p.x, p.z) < 5 ? 'room' : 'outside' };
    s.currentAction = b.action ? b.action.constructor.name.replace('Action', '').toLowerCase() : (b.vel.length() > 0.1 ? 'walking' : b.posture);
  }

  _perceive() {
    const s = this.s, w = this.api.world, b = this.api.body;
    const fwd = b.facingVec();
    s.perception.visible = Object.values(w.objects).map((o) => {
      const p = o.object3D.getWorldPosition(new THREE.Vector3());
      const d = p.clone().sub(b.pos); d.y = 0;
      const ang = Math.acos(THREE.MathUtils.clamp(d.clone().normalize().dot(fwd), -1, 1)) * 180 / Math.PI;
      return { id: o.id, type: o.type, distance: +d.length().toFixed(2), bearing: +ang.toFixed(0), inView: ang < 100 };
    }).filter((o) => o.inView || o.distance < 1.5);
    const cam = this.api.userPosition();
    if (cam) s.perception.userDistance = +cam.clone().setY(0).distanceTo(b.pos.clone().setY(0)).toFixed(2);
  }

  // ------------------------------------------------------------------ utility AI
  options() {
    const s = this.s, b = this.api.body;
    const talking = this.api.lipsync.active || this.api.listening;
    const o = [
      { name: 'idle_observe', u: 0.25 + 0.2 * (1 - s.focus), run: () => this.api.lookAround() },
      { name: 'attend_user', u: s.perception.userPresent ? 0.35 + 0.3 * s.personality.extraversion + (talking ? 0.6 : 0) : 0,
        run: () => this.api.lookAt('user', { mode: 'contact' }) },
      { name: 'rest_sit', u: s.fatigue > 0.55 && b.posture === 'stand' ? s.fatigue : 0, run: () => this.api.sit('chair') },
      { name: 'drink', u: s.thirst > 0.7 && !b.held.R ? s.thirst * 0.9 : 0, run: () => this.api.interactWith('cup', 'pick') },
      { name: 'stand_up', u: b.posture === 'sit' && s.fatigue < 0.25 ? 0.5 : 0, run: () => this.api.stand() },
      { name: 'stretch', u: s.fatigue > 0.35 && s.fatigue < 0.55 && b.posture === 'stand' ? 0.2 : 0,
        run: () => this.api.gesture('shrug') },
      { name: 'wander', u: s.personality.openness * 0.25 * (1 - s.fatigue) * (talking ? 0 : 1) * (b.posture === 'stand' ? 1 : 0),
        run: () => { const a = Math.random() * Math.PI * 2, r = 0.8 + Math.random() * 1.5; return this.api.walkTo({ x: Math.cos(a) * r, z: Math.sin(a) * r }); } },
    ];
    // goal from setGoal() takes priority
    if (s.goal) o.push({ name: 'goal:' + s.goal.type, u: 1.5 * (s.goal.priority || 1), run: () => this._pursueGoal(s.goal) });
    return o;
  }

  async _pursueGoal(g) {
    const api = this.api;
    try {
      if (g.type === 'go_to') await api.walkTo(g.target);
      else if (g.type === 'sit') await api.sit(g.target || 'chair');
      else if (g.type === 'fetch') await api.interactWith(g.target || 'cup', 'pick');
      else if (g.type === 'open_door') await api.interactWith('door', 'open');
      else if (g.type === 'greet') { await api.lookAt('user', { mode: 'contact' }); await api.gesture('wave'); }
      this.remember(`completed goal ${g.type} ${g.target || ''}`, { tags: ['goal'], importance: 0.4 });
    } finally {
      if (this.s.goal === g) this.s.goal = this.s.goalQueue.shift() || null;
    }
  }

  async update(dt) {
    this.t += dt;
    this._dynamics(dt);
    this.acc += dt;
    if (this.acc < this.decideEvery) return;
    this.acc = 0;
    this._perceive();
    // physiology -> expression (fatigue shows on the face if no stronger emotion)
    const s = this.s;
    if (s.fatigue > 0.7 && (s.emotion.name === 'neutral' || s.emotion.intensity < 0.2) && this.t - this.lastEmotionT > 10) {
      this.api.setEmotion('fatigue', (s.fatigue - 0.6) * 2);
      this.lastEmotionT = this.t;
    }
    if (!s.autonomous || this.busy) return;
    const opts = this.options().map((o) => ({ ...o, u: o.u * (0.85 + Math.random() * 0.3) }));   // stochastic tie-breaking
    opts.sort((a, b) => b.u - a.u);
    const best = opts[0];
    if (!best || best.u < 0.2) return;
    if (best.name === this._lastChoice && ['idle_observe', 'attend_user'].includes(best.name) && this.t - this._lastT < 6) return;
    this._lastChoice = best.name; this._lastT = this.t;
    this.log.push({ t: +this.t.toFixed(1), choice: best.name, u: +best.u.toFixed(2) });
    if (this.log.length > 50) this.log.shift();
    this.busy = true;
    try { await best.run(); } catch (e) { this.log.push({ error: String(e) }); } finally { this.busy = false; }
  }

  snapshot() { return JSON.parse(JSON.stringify(this.s)); }
}

const clamp01 = (x) => Math.max(0, Math.min(1, x));
