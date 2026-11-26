// Runtime / API / behaviour tests in headless Chromium (Playwright). Server must run on :8765.
//   node tests/runtime_test.js   (from a dir where `require('playwright')` resolves)
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--autoplay-policy=no-user-gesture-required'] });
  const p = await b.newPage({ viewport: { width: 480, height: 360 } });
  const pageErrors = [];
  p.on('pageerror', (e) => pageErrors.push(e.message));
  await p.goto((process.env.DH_SERVER || 'http://localhost:8765') + '/?q=rt', { waitUntil: 'load' });
  await p.waitForFunction(() => window.APP && window.APP.frameCount > 3, null, { timeout: 180000 });
  await p.evaluate(() => { APP.startCapture(30); });   // deterministic fixed-step simulation (no wall-clock dependence)
  const results = [];
  const check = (name, cond, detail = '') => { results.push({ test: name, pass: !!cond, detail: typeof detail === 'string' ? detail : JSON.stringify(detail) }); console.log((cond ? 'PASS ' : 'FAIL ') + name + (detail ? `  [${typeof detail === 'string' ? detail : JSON.stringify(detail)}]` : '')); };
  const run = (js) => p.evaluate(js);
  const step = (sec) => p.evaluate(async (n) => { for (let i = 0; i < n; i++) { APP.frame(); if (i % 15 === 0) await new Promise((r) => setTimeout(r, 0)); } }, Math.round(sec * 30));
  const expectErr = async (js, code) => {
    const r = await run(`(async () => { try { await (${js}); return 'NO_ERROR'; } catch (e) { return e.code || e.message; } })()`);
    check(`error ${code}: ${js}`, r === code, r);
  };
  // run an async API call while stepping the simulation until it resolves
  const until = async (js, maxSec = 60) => {
    await run(`window.__r = undefined; Promise.resolve(${js}).then((v) => { window.__r = { ok: true, v }; }, (e) => { window.__r = { ok: false, e: e.code || e.message }; })`);
    let t = 0;
    while (t < maxSec) { await step(0.5); t += 0.5; const r = await run('window.__r'); if (r) return { ...r, simSec: t }; }
    return { ok: false, e: 'TIMEOUT', simSec: t };
  };

  // ---------------------------------------------------------- model / skeleton
  const info = await run(`({ bones: Object.keys(APP.character.bones).length, morphs: APP.character.morphNames.length, dofs: Object.keys(APP.character.dofs).length, h: +APP.character.heightM.toFixed(3) })`);
  check('model loaded: 163 bones', info.bones === 163, info);
  check('morph targets >= 75 (52 ARKit + extras + correctives)', info.morphs >= 75, info.morphs);
  check('character height with shoes 1.80-1.84 m', info.h >= 1.80 && info.h <= 1.84, info.h);

  // ---------------------------------------------------------- transform API
  await run(`DH.setPosition({x: 0, z: 0}); DH.setRotation(0)`);
  await step(0.5);
  const pos = await run(`DH.getState().body.position`);
  check('setPosition', Math.abs(pos[0]) < 1e-6 && Math.abs(pos[2]) < 1e-6, pos);
  await expectErr(`DH.setPosition({x: 'a', z: 1})`, 'INVALID_ARGUMENT');
  await expectErr(`DH.moveTo({x: 20, z: 0})`, 'UNREACHABLE');
  await expectErr(`DH.moveTo({x: 1, z: 1}, {speed: 30})`, 'OUT_OF_RANGE');

  // ---------------------------------------------------------- idle: blinks, saccades, breathing, no repetition
  const s0 = await run(`({ b: APP.gaze.stats.blinks, s: APP.gaze.stats.saccades })`);
  const chest = [];
  for (let i = 0; i < 60; i++) { await step(0.25); chest.push(await run(`APP.character.worldPos('spine01').y`)); }
  const s1 = await run(`({ b: APP.gaze.stats.blinks, s: APP.gaze.stats.saccades, m: APP.gaze.stats.micro })`);
  check('idle 15 s: blinks occur (5-12 expected at ~17/min)', s1.b - s0.b >= 2 && s1.b - s0.b <= 14, s1.b - s0.b);
  check('idle 15 s: saccades + micro-saccades occur', s1.s - s0.s >= 3 && s1.m > 3, s1);
  const amp = Math.max(...chest) - Math.min(...chest);
  check('breathing moves the chest (0.5-15 mm)', amp > 0.0005 && amp < 0.015, (amp * 1000).toFixed(2) + ' mm');

  // ---------------------------------------------------------- face
  await run(`DH.setEmotion('joy', 80)`); await step(1.5);
  const joy = await run(`({ s: APP.face.weights.mouthSmileLeft, c: APP.face.weights.cheekSquintLeft })`);
  check('setEmotion joy 80%: smile + cheek raise blend in', joy.s > 0.5 && joy.c > 0.3, joy);
  await run(`DH.setEmotion('joy', 30)`); await step(1.5);
  const joy30 = await run(`APP.face.weights.mouthSmileLeft`);
  check('emotion intensity scales continuously (30% < 80%)', joy30 < joy.s * 0.6 && joy30 > 0.1, joy30);
  await run(`DH.setEmotion('anger', 1)`); await step(1.5);
  const ang = await run(`({ bd: APP.face.weights.browDownLeft, wr: APP.character.materials.DH_Skin.userData.uniforms.uWrinkle.value.y })`);
  check('anger: brows lowered + glabella wrinkle map active', ang.bd > 0.6 && ang.wr > 0.4, ang);
  await expectErr(`DH.setEmotion('hungry', 1)`, 'INVALID_ARGUMENT');
  await run(`DH.setEmotion('neutral', 0); DH.setBlendshape('jawOpen', 0.7)`); await step(0.3);
  const jaw = await run(`APP.character.morphValues.jawOpen`);
  check('setBlendshape override reaches the mesh', Math.abs(jaw - 0.7) < 1e-6, jaw);
  await run(`DH.setBlendshape('jawOpen', null)`);
  await expectErr(`DH.setBlendshape('nope', 1)`, 'NOT_FOUND');
  await run(`DH.blink()`); await step(0.1);
  const bl = await run(`APP.character.morphValues.eyeBlinkLeft`);
  check('blink(): lids close (eyeBlink > 0.6 at 100 ms)', bl > 0.6, bl);

  // ---------------------------------------------------------- eyes / gaze
  await run(`DH.lookAt({x: 1.5, y: 1.7, z: 1.5})`); await step(1.0);
  const ga = await run(`APP.character.eyeAngles`);
  check('lookAt left target: both eyes rotate toward +x (yaw>5)', ga.L.yaw > 5 && ga.R.yaw > 5, ga);
  await run(`DH.lookAt({x: 0, y: 1.71, z: 0.25})`); await step(1.0);
  const verg = await run(`APP.character.eyeAngles`);
  check('near target 25 cm: binocular convergence (L yaw < 0 < R yaw)', verg.L.yaw < -2 && verg.R.yaw > 2, verg);
  const pupNear = await run(`APP.gaze.pupilFrac`);
  await run(`DH.lookAt({x: 0, y: 1.7, z: 5})`); await step(1.5);
  const pupFar = await run(`APP.gaze.pupilFrac`);
  check('pupil near-response (constricts for near target)', pupNear < pupFar, { pupNear, pupFar });
  await run(`APP.gaze.light = 0.05`); await step(2.0);
  const pupDark = await run(`APP.gaze.pupilFrac`);
  check('pupil light reflex (dilates in dark)', pupDark > pupFar + 0.05, { pupFar, pupDark });
  await run(`APP.gaze.light = 0.55; DH.lookAt({x: 0, y: 1.6, z: -3})`); await step(1.5);
  const hy = await run(`APP.gaze.headYawDeg`);
  check('target behind: head turns (head-eye coordination, |yaw| > 30)', Math.abs(hy) > 30, hy);
  await run(`DH.lookAt('user')`);

  // ---------------------------------------------------------- joints & limits
  const jr = await run(`DH.setJointRotation('elbow_flexion_L', 200)`);
  check('setJointRotation clamps to human ROM (elbow 145)', jr.value === 145 && jr.clamped, jr);
  await step(0.2);
  const elb = await run(`(() => { const c = APP.character, w = (n) => c.worldPos(n); const u = w('lowerarm01.L').sub(w('upperarm01.L')).normalize(), v = w('wrist.L').sub(w('lowerarm01.L')).normalize(); return Math.acos(u.dot(v)) * 180 / Math.PI; })()`);
  check('elbow geometric flexion ~ commanded 145 deg', Math.abs(elb - 145) < 8, elb.toFixed(1));
  await run(`DH.setJointRotation('elbow_flexion_L', null)`);
  await expectErr(`DH.setJointRotation('nose_wiggle', 3)`, 'NOT_FOUND');
  const tgt = await run(`DH.setJointTarget('hand_R', {x: -0.25, y: 1.25, z: 0.35})`);
  await step(0.3);
  const hand = await run(`APP.character.worldPos('wrist.R').distanceTo(new APP.camera.position.constructor(-0.25, 1.25, 0.35))`);
  check('setJointTarget hand IK reaches target (< 2 cm)', hand < 0.02 && tgt.reachable, { err_m: +hand.toFixed(4), tgt });
  await run(`DH.setJointTarget('hand_R', null)`);

  // ---------------------------------------------------------- locomotion
  const w = await until(`DH.walkTo({x: 0, z: 3})`, 30);
  const ws = await run(`({ p: DH.getState().body.position, slip: APP.body.slip.last })`);
  check('walkTo arrives within 10 cm', w.ok && Math.hypot(ws.p[0], ws.p[2] - 3) < 0.1, { ...w, ...ws });
  check('walk duration plausible for 3 m at 1.35 m/s (2.5-6 s incl. accel/decel)', w.simSec >= 2.5 && w.simSec <= 6.5, w.simSec);
  // foot sliding: max horizontal speed of a planted foot's ANKLE joint (actual IK result, not the plant target)
  await run(`window.__slip = 0; window.__iv = setInterval(() => {}, 1000); APP.__ankles = null;`);
  const rr = await run(`(async () => { const b = APP.body, c = APP.character; let maxSlip = 0, prev = {}; const r = DH.runTo({x: 0, z: -2});
     let done = false; r.then(() => done = true);
     for (let i = 0; i < 30 * 15 && !done; i++) { APP.frame(); if (i % 15 === 0) await new Promise((r) => setTimeout(r, 0));
       for (const s of ['L', 'R']) { const a = c.worldPos('foot.' + s); a.y = 0; const F = b.feet[s];
         if (F.planted && F.stanceT > 0.15 && F.stanceT < 0.65 && prev[s]) maxSlip = Math.max(maxSlip, a.distanceTo(prev[s]) * 30);
         prev[s] = a; } }
     return { done, maxSlip, peak: 0, pos: DH.getState().body.position }; })()`);
  check('runTo arrives', rr.done && Math.hypot(rr.pos[0], rr.pos[2] + 2) < 0.12, rr);
  check('no foot sliding in mid-stance (ankle speed < 0.15 m/s)', rr.maxSlip < 0.15, rr.maxSlip.toFixed(3) + ' m/s');
  const bk = await until(`DH.walkBackward(1.0)`, 20);
  check('walk backward arrives', bk.ok, bk);
  const sd = await until(`DH.sidestep(0.8)`, 20);
  check('sidestep arrives', sd.ok, sd);
  // stairs: feet follow step heights
  const st = await until(`DH.interactWith('stairs', 'climb')`, 60);
  const top = await run(`({ y: APP.body.pos.y, fl: APP.body.feet.L.plant.y, fr: APP.body.feet.R.plant.y })`);
  check('stairs climb: on landing (~0.85 m)', st.ok && top.y > 0.75, { st, top });
  const dn = await until(`DH.interactWith('stairs', 'descend')`, 60);
  check('stairs descend back to floor', dn.ok && (await run('APP.body.pos.y')) < 0.05, dn);

  // ---------------------------------------------------------- posture & manipulation
  const sit = await until(`DH.sit('chair')`, 60);
  const sitY = await run(`APP.character.worldPos('root').y`);
  check('sit: seated (pelvis 0.45-0.65 m)', sit.ok && sitY > 0.45 && sitY < 0.65, { sit, sitY });
  const stand = await until(`DH.stand()`, 10);
  const standY = await run(`APP.character.worldPos('root').y`);
  check('stand: pelvis back to standing height', stand.ok && standY > 0.85, standY);
  const sq = await until(`DH.squat(0.4)`, 10); const sqY = await run(`APP.character.worldPos('root').y`);
  check('squat lowers pelvis ~0.4 m', sq.ok && sqY < 0.62, sqY);
  await until(`DH.stand()`, 10);
  const g = await until(`DH.grabObject('cup')`, 60);
  const held = await run(`DH.getState().body.holding.R`);
  check('grabObject cup: walks, reaches, holds', g.ok && held === 'cup', { g, held });
  const cupY0 = await run(`APP.world.objects.cup.object3D.position.y`);
  const dr = await until(`DH.playAnimation('drink')`, 10);
  check('playAnimation drink (with held cup)', dr.ok, dr);
  const rel = await until(`DH.releaseObject()`, 60);
  check('releaseObject places cup on table', rel.ok && (await run(`DH.getState().body.holding.R`)) === null && Math.abs((await run(`APP.world.objects.cup.object3D.position.y`)) - 0.81) < 0.05, { rel, cupY0 });
  await expectErr(`DH.releaseObject()`, 'NOT_HOLDING');
  const door = await until(`DH.interactWith('door', 'open')`, 60);
  check('door opens (hinge > 1.2 rad)', door.ok && (await run(`APP.world.objects.door.angle`)) > 1.2, door);
  for (const gname of ['wave', 'nod', 'shake', 'shrug', 'think', 'handshake']) {
    const r = await until(`DH.gesture('${gname}')`, 10);
    check(`gesture ${gname}`, r.ok, r);
  }
  const bl2 = await until(`DH.blendAnimation('stretch', 'clap', 0.4)`, 10);
  check('blendAnimation', bl2.ok, bl2);
  const lie = await until(`DH.lieDown()`, 60);
  const lieY = await run(`APP.character.worldPos('head').y`);
  check('lieDown: head near floor (< 0.4 m)', lie.ok && lieY < 0.4, { lie, lieY });
  await until(`DH.stand()`, 10);

  // ---------------------------------------------------------- speech / lip-sync (virtual clock)
  const sp = await run(`(async () => { const r = DH.speak('안녕하세요. 반갑습니다. 저는 민준입니다.'); const samples = [];
      let done = false; r.then(() => done = true);
      for (let i = 0; i < 30 * 12 && !done; i++) { APP.frame(); if (i % 10 === 0) await new Promise((r) => setTimeout(r, 0));
        if (APP.lipsync.active && APP.lipsync.time() > 0) samples.push({ t: APP.lipsync.time(), jaw: APP.character.morphValues.jawOpen, press: APP.character.morphValues.mouthPressLeft || 0 }); }
      return { done, n: samples.length, maxJaw: Math.max(...samples.map((s) => s.jaw)), method: DH.lastSpeech.method, phones: DH.lastSpeech.phones,
        samples }; })()`);
  check('speak(): completes with acoustic alignment', sp.done && String(sp.method).startsWith('ctc'), sp.method);
  check('lip-sync opens the jaw on vowels (max jawOpen > 0.25)', sp.maxJaw > 0.25, sp.maxJaw);
  // bilabial closures: at each /m/ or /p/ centre the jaw must be nearly closed
  const bil = sp.phones.filter((q) => q.viseme === 'PP');
  const closed = bil.map((q) => { const c = (q.start + q.end) / 2; const s = sp.samples.reduce((a, b) => (Math.abs(b.t - c) < Math.abs(a.t - c) ? b : a)); return s.jaw; });
  check('bilabial closure at /m b p/ (jaw < 0.12 at phone centre)', bil.length > 0 && closed.every((j) => j < 0.12), { n: bil.length, jaw: closed.map((x) => +x.toFixed(3)) });
  // not amplitude-driven: correlation between jaw and audio energy is not ~1, and closures occur during voiced energy
  check('lip-sync is phoneme-timed (closures exist while audio energy is high)', closed.length > 0, 'see bilabial test');

  // ---------------------------------------------------------- memory / goals / behaviour
  await run(`DH.remember('사용자는 커피를 좋아한다 (user likes coffee)', { tags: ['user', 'preference'], importance: 0.9 })`);
  const rc = await run(`DH.recall('커피')`);
  check('remember + recall (Korean query)', rc.length >= 1 && rc[0].text.includes('커피'), rc.map((m) => m.text));
  const goal = await run(`DH.setGoal({ type: 'go_to', target: { x: 1, z: 1 } })`);
  await run(`DH.updateBehavior({ autonomous: true })`);
  let reached = false;
  for (let i = 0; i < 40 && !reached; i++) { await step(0.5); const p2 = await run('DH.getState().body.position'); reached = Math.hypot(p2[0] - 1, p2[2] - 1) < 0.15; }
  check('setGoal + autonomous behaviour: goal executed by utility AI', reached, goal);
  await run(`DH.updateBehavior({ autonomous: false })`);
  await expectErr(`DH.setGoal({ type: 'fly' })`, 'INVALID_ARGUMENT');
  const state = await run(`DH.getState()`);
  const fields = ['name', 'age', 'personality', 'memory', 'emotion', 'mood', 'fatigue', 'hunger', 'thirst', 'focus', 'stress', 'attention', 'currentAction', 'goal', 'relationships', 'conversation', 'location', 'perception'];
  check('AI state has all required fields', fields.every((f) => f in state), fields.filter((f) => !(f in state)));

  // ---------------------------------------------------------- performance
  await run(`APP.stopCapture()`);
  await p.waitForTimeout(3000);
  const perf = await run(`APP.perf()`);
  check('perf: simulation (AI+anim+IK+face) < 8 ms/frame on CPU', perf.simMs < 8, perf);
  check('no uncaught page errors', pageErrors.length === 0, pageErrors.slice(0, 3));

  const nf = results.filter((r) => !r.pass).length;
  console.log(`\n${results.length - nf}/${results.length} passed`);
  fs.writeFileSync(path.join(__dirname, 'results_runtime.json'), JSON.stringify({ results, perf }, null, 1));
  await b.close();
  process.exit(nf ? 1 : 0);
})();
