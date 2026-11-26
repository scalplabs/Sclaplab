# Scaling to 100 independent AI humans

Goal: 100 distinct people (appearance, body, voice, personality, memory, goals, relationships) sharing one space,
without rendering 100 hero characters at full cost.

## 1. Data separation (implemented)

| Shared (once) | Per character (data) |
|---|---|
| hm08 topology, UV layout, 163-bone skeleton, skin weights | `pipeline/characters/<id>.json`: macro body (sex, age, height, muscle, weight, proportions, ethnicity), 70+ face modifiers, asymmetry |
| ARKit/FACS shape *definitions* (unit → shape recipes) | baked shape keys (same names; geometry differs) |
| Anatomical DOF table + joint limits | skin tone (melanin/hemoglobin), freckles, beard shadow, hair colour, eye palette, seed |
| Shaders (skin/eye/hair), animation clips (DOF space → retarget-free) | voice (provider + voice_id + emotion mapping), personality (Big Five), memory, goals, relationships |
| Gait / gaze / blink / lipsync models | behaviour parameters (`decideEvery`, needs rates) |

Because animation is authored in **anatomical DOF space** and IK is procedural, every clip and every locomotion
style works on every generated body without retargeting; height/leg length are measured at load
(`Character.measure()`), so stride and foot plants adapt automatically.

Generation: `build_character.py characters/<id>.json` → the same pipeline produces a unique mesh, textures (procedural, seeded), groom and GLB. A batch generator (`tools/make_population.py`) samples plausible parameter sets (age 18–75, height from population distributions, all ethnic mixes) and seeds.

## 2. Runtime budget strategy (demonstrated in `web/crowd.html`)

| Tier (by screen size / importance) | Mesh | Face | Hair | Shading | Animation | AI tick |
|---|---|---|---|---|---|---|
| L0 hero (≤ 3 m, ≤ 2 agents) | LOD0 + all morphs | full ARKit + wrinkles + eyes | double-layer cards | skin SSS shader, 4K | full IK + gaze + lipsync | 0.5 s |
| L1 (3–8 m, ≤ 10) | LOD1 (45 %) | speech/blink subset (23 morphs) | cards | 2K, no micro normal | IK feet only | 1 s |
| L2 crowd (> 8 m) | LOD2 (≈ 15 %, merged) | none | baked in mesh | standard PBR, 1K | shared clip sampling, no IK | 2–4 s, round-robin |
| culled | – | – | – | – | position only | 5 s |

* **Frustum culling** per agent bounding sphere; **occlusion**: cheap CPU test against world occluders (walls) + three.js frustum.
* **Shared animation resources**: one skeleton evaluation per *pose cluster* at L2 (agents walking at similar speed share sampled DOF poses with phase offsets).
* **GPU skinning**: three.js skins on the GPU (bone texture); L2 can move to `InstancedMesh` + vertex-animation textures when > 300 agents.
* **Texture streaming**: L2/L1 textures load first; 4K hero sets stream on promotion (`Character.setLOD`).
* **AI update scheduling**: priority queue by distance/importance; fixed per-frame budget (e.g. 2 ms); LLM calls are asynchronous, rate-limited and only for agents in conversation; others use the utility AI.
* **Asynchronous voice**: TTS + alignment run server-side in a worker pool; results are cached by `(voice, text, emotion)`.
* **Spatial hashing** (2 m cells) for neighbour queries, collision avoidance (RVO-style steering) and perception.

## 3. What exists today vs. next steps

Implemented: data-driven character config, LOD0/1/2 export, hero LOD switching, AI scheduling parameter, crowd demo with LOD2 instances + spatial hash + round-robin AI, measured in `docs/TEST_REPORT.md`.
Next: population generator batch run (≈ 25 min CPU per character for 4K textures; 2K takes ≈ 6 min), voice bank assignment per character, social relationship graph between agents, server-side agent simulation for > 100 agents.
