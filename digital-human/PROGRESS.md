# Digital Human — Progress Log (resume point for future sessions)

Project root: `Sclaplab/digital-human/` (branch `claude/hyper-realistic-digital-human-tobvcm`).
External sources (NOT committed, re-fetch with `pipeline/fetch_assets.sh`): `/home/user/work/ext/`
- makehuman (CC0 assets: base mesh hm08, targets, default skeleton 163 bones, weights, face pose units)
- mpfb2 (region mask textures, skin node-tree reference)
- makehuman-py3-assets (CC0 MakeHuman 1.1 system assets mirror: skins, eyes, brows, lashes, teeth, tongue, clothes)
Blender: `pip install bpy==5.3.0` into `/home/user/work/venv` (Python 3.13).

## Findings (Phase 0)
- Attached repos contain NO 3D model: Sclaplab = trading-terminal web page, HeadsDown = iOS transit app.
- No GPU (software GL: lavapipe/swiftshader). No Unreal Engine. => see docs/TECH_STACK.md.
- Network: GitHub raw/clone, media.githubusercontent (LFS), PyPI, npm, jsdelivr, HuggingFace OK; polyhaven/blender.org blocked.
- TTS: Typecast (proxy-injected creds, has timestamps API), ElevenLabs MCP connected.

## Phases
- [x] P0 environment + asset analysis
- [x] P1 character build: pipeline/build_character.py (hm08 13.4k quads, 163 bones, 180.00cm, anatomical eyes)
- [~] P2 lookdev: bake_geometry_maps.py, tex_skin.py, tex_micro.py, tex_eye.py, hair_strands.py, lookdev.py, render.py (iterating)
- [x] P3 face_rig.py: 52 ARKit + 11 extra from MH FACS units (BVH zup); 12 body correctives. NOTE Blender5 shape_key_add value=1 -> set 0
- [x] P4 export_glb.py -> assets/characters/minjun (lod0/1/2 glb, fbx, textures, rig_meta.json)
- [ ] P5 web runtime (three.js): rendering, rig control, IK, gaze, idle, locomotion
- [x] P6 server/: Typecast TTS w/ timestamps + G2P(ko/en) + wav2vec2 CTC forced alignment (speechvenv). Claude brain w/ rule fallback
- [ ] P7 AI behavior + API + dev UI
- [ ] P8 verification: renders, video, tests, report
- [ ] P9 docs, commit, push

## Build order (reproduce)
venv=/home/user/work/venv/bin/python ; cd pipeline
$venv build_character.py characters/minjun.json B/minjun_s1.blend
$venv dump_landmarks.py B/minjun_s1.blend B/landmarks.json
$venv bake_geometry_maps.py B/minjun_s1.blend MAPS 4096
python3 tex_micro.py TEX; python3 tex_eye.py TEX; python3 tex_skin.py MAPS B/landmarks.json characters/minjun.json TEX
$venv lookdev.py B/minjun_s1.blend TEX characters/minjun.json B/minjun_ld.blend
$venv face_rig.py B/minjun_ld.blend B/minjun_rig.blend B/rig_meta.json
$venv export_glb.py B/minjun_rig.blend TEX ../assets B/rig_meta.json
$venv render.py B/minjun_rig.blend OUT --shots face_34,... --light studio
Server: /home/user/work/speechvenv/bin/python -m server.app --preload  (port 8765)
