# Test report

Environment: 4 vCPU, 15 GB RAM, **no GPU** (Chromium + SwiftShader software WebGL2; Blender 5.3 `bpy` Cycles on CPU).
All numbers below were produced by the scripts in `tests/` and the capture/render tools in this session; raw results are in
`tests/results_*.json`. Nothing is marked as verified unless it was executed.

## 1. Summary

| Suite | Command | Result |
|---|---|---|
| Asset integrity (GLB LOD0–2, rig, textures) | `python3 tests/test_assets.py` | **49 / 49 pass** |
| Speech + server (G2P, TTS, forced alignment, endpoints) | `python tests/test_speech.py` (server running) | **30 / 30 pass** |
| Runtime / API / behaviour (headless Chromium, fixed-step simulation) | `node tests/runtime_test.js` | **60 / 61 pass** (1 genuine failure, see §6) |
| External control (Python client → HTTP → WebSocket → runtime) | `tools/dh_client.py` session (§5) | works, incl. typed error propagation |
| Crowd (100 agents) | `web/crowd.html?n=100` | runs; simulation 1.4 ms/frame |

## 2. Model, mesh, UV, skeleton, weights (`test_assets.py`)

* All three LODs load; every mesh primitive has finite positions, valid indices, UVs within [0, 1], skin weights summing to 1 (±0.02),
  joint indices in range, < 0.5 % degenerate triangles (measured 0.00 % on all LOD0 meshes).
* Skeleton: 163 joints, single root (`root`), hierarchy acyclic; required joints present (pelvis/spine/neck/head/jaw/eyes, clavicles,
  twist bones `upperarm02/lowerarm02/upperleg02/lowerleg02`, every finger and toe joint, facial and tongue bones).
* Morphs: all 52 ARKit names present (union over body/teeth/tongue/brows/lashes); no dead face targets.
* **Found and fixed during testing:** the 6 elbow/knee/hip correctives were *dead* in the realtime model because the skin under
  the clothes is removed; correctives are now transferred to the garment through its barycentric proxy binding (garment carries 12 keys).
* Triangle budgets: LOD0 173,940 · LOD1 145,832 · LOD2 49,165. Stature 180.00 cm (macro solved by bisection); 1.823 m in shoes.
* Textures present: 4K albedo/normal, 2K roughness-spec-cavity-translucency, masks, wrinkle normal + mask, tiled micro normal, eye set.

## 3. Speech & lip-sync (`test_speech.py`)

* Korean G2P phonological rules: 국물→[kuŋmul] (nasalisation), 좋다→[tɕotʰa] (aspiration), 신라→[silla] (lateralisation),
  음악→[ɯmak] (liaison), 입니다→[imnita], 안녕→[annjʌŋ]: all pass. English CMUdict + letter-to-sound fallback pass.
* Live Typecast TTS + wav2vec2 CTC forced alignment for Korean and English: phone times monotonic and inside the audio;
  method = acoustic forced alignment (not approximate); **Korean phones agree with Typecast's syllable timestamps 38/38 (±80 ms)**.
  Typical latency (CPU): TTS 0.6–2.4 s + alignment 1.7–3.0 s for 3–4 s of speech (cached afterwards).
* Bilabials detected and mapped to the closure viseme; 14/15 viseme classes exercised by two pangrams; 50 Hz energy envelope.
* Validation: empty text and > 600 characters rejected with HTTP 400. `/api/chat` returns the full intent schema.
* Mixed-script language detection bug found ("안녕 hello" → en) and fixed (syllable weighting).

## 4. Runtime behaviour (`runtime_test.js`, deterministic 30 Hz simulation)

| Area | Measured |
|---|---|
| Idle life (15 s) | 4–7 blinks (stochastic, ~17/min baseline), 10–11 saccades, 12–13 micro-saccades, chest breathing excursion 0.9–4 mm |
| Emotion | joy 80 % → smile 0.67 / cheek 0.51; joy 30 % → smile 0.26 (continuous scaling); anger → brows 0.94, glabella wrinkle map 1.0 |
| Blink | lids reach 0.97 closure within 300 ms |
| Gaze | lateral target: both eyes yaw ≈ 15–17°; target at 25 cm: convergence L −5.6° / R +8.6°; target behind: head turns 70° |
| Pupil | near response 0.399 → 0.345; darkness 0.399 → 0.599 (light reflex) |
| Joints | elbow command 200° clamped to 145° (human ROM); geometric elbow angle 144.4°; hand IK error 0.0 mm |
| Locomotion | walk 3 m arrives (error < 5 cm) in 3.0 s sim incl. acceleration; run, walk backward, sidestep arrive; stairs climb to 0.85 m landing and descend |
| Foot contact | **walking: mid-stance ankle speed ≤ 0.144 m/s (single frame), zero-motion otherwise**; running: one frame of 0.264 m/s (≈ 9 mm) just after touchdown → FAIL vs 0.15 threshold |
| Posture | sit pelvis 0.558 m on a 0.47 m seat; stand back to 0.978 m; squat pelvis 0.581 m; lie down head 0.315 m |
| Manipulation | cup: walk → reach → grasp → drink clip → place back on table (y = 0.81); door hinge > 1.2 rad; 6 gestures; clip blending |
| Speech in runtime | Korean utterance completes with acoustic alignment; max jawOpen 0.26 on vowels; **jaw ≤ 0.074 at all 5 bilabial centres** (closure) |
| AI | remember/recall (Korean query), autonomous utility AI executes `setGoal(go_to)`, state contains all 18 required fields |
| Cost | simulation (AI + body + IK + gaze + face + lip-sync) **0.58 ms/frame**; no uncaught page errors |

**Bugs found by these tests and fixed in this session:** arms raised instead of hanging (probe picked mixed axis → exact
cross-product axes); MakeHuman bind pose has 46° elbow bend (absolute anatomical angles via rest offsets); feet initialised at
ankle height (constant settle-stepping); obstacle avoidance made the chair approach point unreachable; settle-step resumed with stale
end points after walking (1 m foot drag); gaze locked on the user while running away; ±180° head-yaw flip-flop; lie-down recline
clamped by the pelvis-tilt joint limit; bilabial closure lag (now anticipatory, physiologically ~70 ms early); Blender 5 creates
shape keys at value 1.0 (all 70 expressions were stacked).

## 5. External control

`tools/dh_client.py` against a live runtime: `setEmotion`, `walkTo` (arrived at (0.48, 0.96) for target (0.5, 1.0)), `setJointRotation`,
`joints` (82 anatomical DOFs), `remember`/`recall`, `perf`, and an invalid emotion raising `DHError INVALID_ARGUMENT` — all succeeded.

## 6. Known failures and limitations (not hidden)

| Item | Status |
|---|---|
| Running foot contact | one-frame ≈ 9 mm settle at touchdown (0.264 m/s peak); walking is within tolerance |
| Photorealism | Not at MetaHuman/film-double level. Skin detail is synthesised (no scan data); the face still reads as CG in close-ups (see `renders/`). Realtime hair = generated cards; strand hair only in Cycles. |
| Real-time frame rate | Not measurable on a real GPU here. Software rasteriser: ~110–200 ms per frame (HQ face close-up up to ~2 s because of double-sided alpha-tested hair cards). Simulation itself: 0.6–1.5 ms. |
| Motion data | Procedural locomotion and actions (no licensed motion-capture library was available); no physics-based balance controller (COM is computed and used for posture, not closed-loop balance). |
| Cloth | Garments are skinned with transferred correctives; **no cloth simulation** at runtime (Blender cloth sim not applied). |
| Clothing/body penetration | prevented structurally by removing skin under garments; not measured numerically for extreme poses. |
| Strand lashes/brows (Cycles) | parented to the head bone: they do not follow eyelid shapes in expression renders (cards do in realtime). |
| LLM | Claude adapter implemented (structured output, fallbacks) but **not executed** here (no API key); rule-based fallback was tested. |
| ElevenLabs | adapter implemented to the public API, **not executed** (no key available to the server). |
| Facial motion capture / mocap retargeting | not implemented (no device/data). Animation clips are DOF-space keyframes. |
| Unreal Engine / MetaHuman | not available in this environment; FBX export provided for import. |
| Video | captured from the real-time runtime at a fixed 15 fps simulation step (software rendering); audio muxed at recorded offsets. In the stairs shot the camera crops the head at the top of the climb. |
