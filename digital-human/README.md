# Digital Human — Kim Min-jun (김민준)

A controllable, photoreal-oriented digital human: adult male, 180.0 cm, built from anatomical CC0 data with a
Blender (bpy) asset pipeline, a Cycles offline renderer, a three.js real-time runtime with a full programmatic
control API, a Korean/English speech stack with acoustic forced alignment, and an AI behaviour layer.

| | |
|---|---|
| Run it | `python -m server.app --preload` → <http://localhost:8765/> (see `docs/INSTALL.md`) |
| Control it | `DH.walkTo({x:1,z:2})` in the page, or `POST /api/control` from any program (`docs/API.md`, `tools/dh_client.py`) |
| Edit it | `source/minjun_rig.blend` (master: subdivided body, 163-bone rig, 75 shape keys, Cycles materials, strand hair) |
| Real-time model | `assets/characters/minjun/minjun_lod{0,1,2}.glb`, `minjun_lod0.fbx`, `textures/`, `rig_meta.json` |
| Renders / video | `renders/`, `videos/` |
| Test results | `docs/TEST_REPORT.md` (`tests/`) |
| Why this stack | `docs/TECH_STACK.md` · 100-agent design: `docs/SCALING_100.md` · licenses: `docs/LICENSES.md` |
| Resume work | `PROGRESS.md` |

## What is inside

**Body & face** — hm08 topology (13.4k quads, face/joint edge loops, separate lips/lids), MakeHuman macro shape solved by
bisection to exactly 180.00 cm, East-Asian 30-year-old proportions, deliberate asymmetry (eyes, brow, mouth corner, ear, nose, jaw).
Anatomical eyes rebuilt from measurements (12 mm sclera, 7.8 mm cornea, 11.7 mm iris, refractive cornea, tear meniscus, caruncle).
Teeth, gums, tongue (8 bones), oral cavity.

**Rig** — 163 bones: root/pelvis, 5 spine, 3 neck, head, jaw, eyes, clavicles, shoulders, upper/lower-arm *twist* bones, wrists, all
finger and toe joints, 50+ facial bones, tongue. Normalised 4-influence skin weights. Anatomical DOF layer with human range-of-motion
limits; analytic two-bone IK with pole vectors; foot locking and ground contact; centre-of-mass; root motion.

**Face rig** — 52 ARKit blendshapes + 11 FACS/tongue extras composed from MakeHuman's 60 bone-driven face units, propagated to brows,
lashes, teeth and tongue; animated wrinkle maps (forehead, glabella, crow's feet, nasolabial) driven by the shapes;
12 pose-space correctives (elbow, knee, shoulder ×2, hip, wrist; DQS-vs-LBS volume restoration + biceps/calf bulge), carried by the clothing too.

**Look** — procedural 4K skin from per-texel 3D anatomy: melanin/haemoglobin variation, vascular regions, beard follicles, moles,
capillaries, wrinkles/folds/knuckle and palm creases, lip lines, tiled micro-normal (pores + dermal grooves), roughness/specular/cavity/
translucency maps. Cycles: random-walk SSS (skin mfp ratios), principled hair strands (81k scalp + brows, lashes, stubble, vellus, arm hair).
Real time: per-channel bent-normal SSS + thin-tissue transmission, dual-lobe (clearcoat) sebum specular, refraction-parallax eyes with
physiological pupil, double-layer hair cards, GTAO, DOF, SMAA, AgX tone mapping, HDRI lighting presets.

**Behaviour** — saccades on the main sequence, micro-saccades, smooth pursuit, vergence, head–eye coordination, lid follow, state-driven
blinking, pupil light/arousal/near response; breathing (emotion- and exertion-dependent), weight shifts, postural sway, finger micro-motion,
swallowing, micro-expressions; 13 emotions with 0–100 % intensity and posture/physiology coupling; procedural walk/run/sprint/backward/
sidestep with world-locked foot plants, stairs; sit, stand, squat, lie down, reach, grasp, place, door, wave, handshake, point, gestures,
keyframe clips; utility-AI with needs, mood, memory, goals, perception; LLM (Claude) only for dialogue and intent.

**Speech** — Typecast TTS (ElevenLabs adapter), Korean rule-based G2P (liaison, nasalisation, aspiration, lateralisation) and CMUdict
English, wav2vec2 CTC forced alignment to phone level cross-checked against provider timestamps, 15 visemes with Cohen–Massaro
coarticulation, bilabial closure guarantee, stress-driven emphasis, pre-utterance inhalation, back-channel listening.

## Honest limitations
See `docs/TEST_REPORT.md` § Limitations. In short: no GPU in the build environment (real-time FPS measured here is software rasterisation),
skin detail is synthesised not scanned, real-time hair is cards (strands are offline only), locomotion is procedural (no licensed mocap),
the Claude dialogue path is implemented but was exercised here only through its rule-based fallback (no API key in this environment).
