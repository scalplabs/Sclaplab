# Technology stack — decision record

## 1. What was attached / available

| Item | Finding |
|---|---|
| Attached repos | `Sclaplab` (a single-file trading-terminal web page) and `HeadsDown` (an iOS transit app). **Neither contains a 3D model, rig or digital-human code.** Everything here was built from scratch. |
| Hardware | 4 vCPU, 15 GB RAM, **no GPU** (software GL only: SwiftShader / lavapipe). |
| Engines | No Unreal Engine 5 (not installable here: no GPU, no Epic account, Linux headless). Blender is available as the `bpy` 5.3 Python module (headless, Cycles CPU). |
| Network | GitHub (clone + LFS media), PyPI, npm, jsDelivr, Hugging Face reachable. Poly Haven, blender.org, threejs.org blocked (Poly Haven HDRIs obtained from a CC0 mirror on Hugging Face). |
| Services | Typecast TTS (credentials injected by the environment proxy, **verified working**, includes per-character timestamps). ElevenLabs connector present for the user, but no API key available to server code → adapter implemented, not verified. No Anthropic API key in this environment → Claude adapter implemented, rule-based fallback used in tests. |

## 2. Options considered

| Option | Photorealism ceiling | Programmatic control | Runs here? | License / cost | Verdict |
|---|---|---|---|---|---|
| **Unreal Engine 5 + MetaHuman** | Highest (real-time) | Good (Blueprint/C++/Python, Live Link) | **No** (needs GPU + Windows/Linux desktop + Epic account; MetaHuman assets only licensed for rendering in Unreal) | Free under EULA, UE-only | Best target for final presentation; documented as an export path (FBX), not buildable here |
| **Blender (bpy) + Cycles** | Film-quality offline (path tracing, random-walk SSS, Principled Hair) | Full Python | **Yes** (CPU) | GPL tool; outputs are ours | **Chosen for asset authoring + offline "high-quality mode" renders** |
| **three.js / WebGL2** | Good real-time with custom shaders (no ray tracing) | Full JS, trivially externally controllable | **Yes** (software GL for tests; real GPUs in browsers) | MIT | **Chosen for the real-time runtime, control API and dev UI** |
| WebGPU | Higher ceiling (compute, better post) | Same | Not in headless SwiftShader reliably | MIT | Future: three.js WebGPURenderer path |
| OpenUSD | Interchange | — | Possible | Apache | Not needed for one character; FBX + GLB provided |
| SMPL/SMPL-X | Excellent body shape space | — | Yes | **Non-commercial license** | Rejected (license) |
| MakeHuman (hm08) data | Anatomical base mesh, 163-bone rig incl. face/twist bones, FACS-like face units, morph targets | — | Yes | **CC0** | **Chosen as the anatomical foundation** |
| Real head scans (e.g. Lee Perry-Smith) | Real skin detail | — | Yes | CC-BY, **a real person's likeness** | Rejected (identity/likeness) |

## 3. Chosen architecture

```
pipeline/ (Python + Blender bpy 5.3)           server/ (Python, aiohttp)                 web/ (three.js r170, ES modules)
 build_character   hm08 + macros + asymmetry      /api/tts   Typecast TTS (+ElevenLabs)     character  GLB, materials, DOFs, morphs
 bake/tex_*        4K skin/eye/micro textures      g2p        Korean rules / CMUdict          materials  skin SSS, eye refraction, hair
 hair_strands      strand groom + hair cards       align      wav2vec2 CTC forced alignment   motion     gait, IK, posture, actions
 lookdev           Cycles materials                /api/chat  Claude intent (structured)      face/eyes  FACS emotions, saccades, blinks
 face_rig          ARKit52 + correctives           /ws +      external control bridge         lipsync    coarticulated visemes
 export_glb        GLB LOD0-2, FBX, textures       /api/control                               ai         utility AI, memory, needs
 render            Cycles stills (offline mode)                                               api        28+ public functions
```

* **Offline high-quality mode** = Blender Cycles path tracing (`pipeline/render.py`): 81k-strand groom, random-walk skin SSS, refractive cornea, HDRI GI.
* **Real-time mode** = browser runtime with two quality levels (`?q=rt` / `?q=hq`: GTAO, DOF, SMAA, 4K skin, 4K shadow maps).
* **LLM** only for dialogue / intent (structured JSON); all joint control, IK and timing run locally at frame rate.

## 4. Honest limits of this environment

* No GPU → realtime frame rates measured here (~8 fps actual on SwiftShader) are **not** representative; the per-frame simulation cost is reported separately (≈1.7 ms). A consumer GPU is required for interactive use.
* Skin detail is synthesised procedurally from anatomy (no scan data). It is physically plausible but not equivalent to a scanned MetaHuman.
* Hair in real time uses generated cards; strand hair is offline (Cycles) only.
* Motion is procedural (no motion-capture library could be licensed/fetched for commercial use within this session); see `docs/TEST_REPORT.md` for measured gait metrics.
