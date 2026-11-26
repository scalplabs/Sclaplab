# Digital Human Control API

Three ways to call it — all execute the **same** functions:

1. **In the page** (dev UI console or embedding app): `await DH.walkTo({x: 1, z: 2})`
2. **External programs over HTTP** (any language): `POST http://localhost:8765/api/control`
   `{"cmd": "walkTo", "args": [{"x": 1, "z": 2}], "timeout": 60}` → `{"ok": true, "result": ...}` or
   `{"ok": false, "error": "OUT_OF_RANGE", "message": "..."}` (HTTP 400). Requires a browser runtime connected (`/api/health` → `runtimes_connected`).
3. **Python client**: `tools/dh_client.py` (`DH().walkTo({"x":1,"z":2})`).

Conventions: metres, degrees, world Y-up, character faces +Z at heading 0. Timed actions return a Promise that resolves when the action completes. Errors: `DHError {code, message}` with codes
`INVALID_ARGUMENT, OUT_OF_RANGE, NOT_FOUND, UNREACHABLE, BUSY, NOT_HOLDING, UNSUPPORTED, TTS_FAILED, UNKNOWN_COMMAND, NO_RUNTIME, TIMEOUT`.

| Function | Input (range) | Output | Errors | Example |
|---|---|---|---|---|
| `setPosition(p)` | `{x,z}` m | `[x,y,z]` | INVALID_ARGUMENT | `DH.setPosition({x:0,z:1})` |
| `setRotation(deg)` | number, deg (0 = +Z) | deg | INVALID_ARGUMENT | `DH.setRotation(90)` |
| `moveTo(p, {speed, face, backward, strafe, keepGaze})` | speed 0.1–7.5 m/s; face deg | `{arrived, pos}` on arrival | OUT_OF_RANGE, UNREACHABLE (outside r=13 m or inside obstacle) | `DH.moveTo({x:2,z:0},{speed:2})` |
| `walkTo(p, opts)` | as moveTo, 1.35 m/s | same | same | `DH.walkTo({x:0,z:3})` |
| `runTo(p, opts)` | 3.6 m/s | same | same | `DH.runTo({x:0,z:-5})` |
| `sprintTo(p)` / `walkBackward(d)` / `sidestep(d)` | 6.5 m/s / metres | same | same | `DH.walkBackward(1.5)` |
| `stop()` | – | `true` | – | `DH.stop()` |
| `sit(chairId='chair')` | world chair id | `{ok, posture:'sit'}` | NOT_FOUND | `DH.sit()` (walks there, turns, sits) |
| `stand()` | – | `{ok, posture:'stand'}` | – | `DH.stand()` |
| `squat(depth)` / `lieDown(id='mat')` | 0.1–0.55 m | `{ok, posture}` | OUT_OF_RANGE, NOT_FOUND | `DH.lieDown()` |
| `lookAt(target, {mode})` | `'user'` \| object id \| `{x,y,z}` \| `null`; mode fixate/contact/pursue/idle/avert | `{target, mode}` | NOT_FOUND, INVALID_ARGUMENT | `DH.lookAt('cup')` |
| `blink({double})` | bool | `true` | – | `DH.blink({double:true})` |
| `breathe({rate, depth, deep})` | 6–40 /min, 0.3–2.5 | `{rate, depth}` | OUT_OF_RANGE | `DH.breathe({deep:true})` |
| `speak(text, {lang, emotion, intensity, provider})` | ≤600 chars; ko/en; provider typecast/elevenlabs | `{ok, duration, method, phones}` | INVALID_ARGUMENT, OUT_OF_RANGE; TTS failure falls back to browser speech (marked *approximate*) | `DH.speak('안녕하세요', {emotion:'joy'})` |
| `listen(on, {mic})` | bool; mic = microphone VAD back-channel | `{listening}` | (getUserMedia errors) | `DH.listen(true,{mic:true})` |
| `converse(text)` | user utterance | intent `{reply, emotion, gesture, action, ...}` | INVALID_ARGUMENT | `DH.converse('의자에 앉아 줄래요?')` |
| `setEmotion(name, intensity)` | neutral, joy, sadness, anger, fear, surprise, disgust, embarrassment, tension, boredom, focus, doubt, fatigue; 0–1 or 0–100 | `{name, intensity}` | INVALID_ARGUMENT, OUT_OF_RANGE | `DH.setEmotion('joy', 70)` |
| `setExpression(weights)` | `{arkitName: 0–1}` additive; `null` clears | weights | NOT_FOUND, OUT_OF_RANGE | `DH.setExpression({browInnerUp:.6})` |
| `setBlendshape(name, w)` | any of 63 face + 12 corrective morphs; 0–1 (`mouthClose` −1–1); `null` releases | w | NOT_FOUND, OUT_OF_RANGE | `DH.setBlendshape('jawOpen', .4)` |
| `setJointRotation(joint, v)` | anatomical DOF (deg, clamped to human ROM) e.g. `elbow_flexion_L`, or raw bone `{x,y,z}` local Euler deg; `null` releases | `{joint, value, clamped, limit}` | NOT_FOUND, INVALID_ARGUMENT | `DH.setJointRotation('knee_flexion_R', 60)` |
| `joints()` | – | `{anatomical: {dof:[min,max]}, bones:[163]}` | – | |
| `setJointTarget(effector, p, {weight})` | hand_L/R, foot_L/R, head; `{x,y,z}`; `null` clears | `{effector, reachable, distance}` | INVALID_ARGUMENT, OUT_OF_RANGE | `DH.setJointTarget('hand_R',{x:.3,y:1.2,z:.4})` |
| `playAnimation(name, {loop, speed, weight})` | clips in `assets/animations` (bow, drink, stretch, clap, check_watch, scratch_head, cross_arms, look_around) | `{ok, clip}` when done | NOT_FOUND, OUT_OF_RANGE | `DH.playAnimation('bow')` |
| `blendAnimation(a, b, w)` | two clips, w 0–1 | when both done | NOT_FOUND | `DH.blendAnimation('stretch','clap',.3)` |
| `gesture(name, {side, target})` | wave, nod, shake, shrug, open_palms, think, beat, point, handshake | `{ok, gesture}` | INVALID_ARGUMENT | `DH.gesture('point',{target:'door'})` |
| `reachFor(target, {side})` | object id or `{x,y,z}` | `{ok}` | NOT_FOUND | `DH.reachFor('table')` |
| `grabObject(id, {side})` | graspable item | `{ok, holding}` | NOT_FOUND, BUSY | `DH.grabObject('cup')` |
| `releaseObject({side, at})` | `{x,y,z}` or table default | `{ok}` | NOT_HOLDING | `DH.releaseObject()` |
| `interactWith(id, verb)` | chair:sit, mat:lie, cup:pick/drink/place, door:open, stairs:climb/descend, user:greet/handshake | action result | NOT_FOUND, UNSUPPORTED | `DH.interactWith('door','open')` |
| `remember(text, {tags, importance})` | text, importance 0–1 | memory record | INVALID_ARGUMENT | `DH.remember('user likes coffee')` |
| `recall(query, k)` | text | `[memory]` ranked by relevance+recency+importance | INVALID_ARGUMENT | `DH.recall('coffee')` |
| `setGoal({type, target, priority})` | go_to, sit, fetch, open_door, greet | `{active, queued}` | INVALID_ARGUMENT | `DH.setGoal({type:'fetch',target:'cup'})` |
| `updateBehavior({autonomous, needs, personality, decideEvery, relationship})` | needs 0–1 | full state | OUT_OF_RANGE | `DH.updateBehavior({autonomous:true})` |
| `getState()` | – | identity, personality, emotion, mood, needs, memory, goals, conversation, location, perception, body, face, speech | – | |

App-level commands over `/api/control`: `setLighting(studio|window|overcast|park|loft|night)`, `setCamera(face|face34|eyes|bust|full|side|back|wide)`, `setQuality(hq|rt)`, `perf()`, `screenshot()`.

## Server endpoints

| Endpoint | Body | Returns |
|---|---|---|
| `POST /api/tts` | `{text, lang?, emotion?, intensity?, provider?, voice_id?, speed?}` | `{audio_url, duration, lang, phones:[{p,start,end,viseme,stress,word,char}], words, energy(50 Hz), char_times, method, provider, timing_ms}` |
| `POST /api/chat` | `{text, context}` | intent JSON (schema in `server/brain.py`) |
| `POST /api/say` | `{text, context}` | `{intent, speech}` |
| `POST /api/control` | `{cmd, args, timeout}` | runtime result |
| `GET /api/health` | – | providers, alignment model, LLM mode, connected runtimes |
