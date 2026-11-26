# Install & run

## A. Run the real-time digital human (most users)

Requirements: Python ≥ 3.11, a desktop browser with WebGL2 and a real GPU (Chrome/Edge/Firefox/Safari 17+).

```bash
cd digital-human
python3 -m venv .venv && . .venv/bin/activate
pip install -r server/requirements.txt          # aiohttp, numpy, scipy, soundfile, anthropic
# optional: acoustic forced alignment (≈ 1.3 GB model + torch)
pip install -r server/requirements-align.txt
python tools/fetch_models.py                     # downloads facebook/wav2vec2-xlsr-53-espeak-cv-ft + CMUdict
export TYPECAST_API_KEY=...                      # or ELEVENLABS_API_KEY / ELEVENLABS_VOICE
export ANTHROPIC_API_KEY=...                     # optional: Claude dialogue; otherwise rule-based fallback
python -m server.app --port 8765 --preload
```

Open <http://localhost:8765/> (`?q=rt` for the lighter real-time mode, default `hq`).

Without the alignment model the server still runs: phone timing falls back to the TTS provider's per-character timestamps (marked *approximate* in every response). Without any TTS key, `speak()` falls back to the browser's speech synthesis with estimated timing (also marked *approximate*).

Environment variables: `TYPECAST_API_KEY`, `TYPECAST_VOICE` (default young-adult male "Jinheon"), `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE`, `ANTHROPIC_API_KEY`, `DH_W2V_DIR`, `DH_CMUDICT`, `DH_TTS_CACHE`.

## B. External control

```bash
python tools/dh_client.py                         # prints body state
curl -X POST localhost:8765/api/control -d '{"cmd":"walkTo","args":[{"x":1,"z":2}]}'
```
See `docs/API.md`.

## C. Rebuild the character / render offline (artists, pipeline)

```bash
python3 -m venv ~/dhvenv && ~/dhvenv/bin/pip install bpy==5.3.0 numpy scipy pillow   # Blender as a module (Python 3.13)
bash pipeline/fetch_assets.sh                     # CC0 MakeHuman / MPFB2 data + HDRIs into $DH_EXT
cd pipeline && bash build_all.sh                  # ≈ 25 min on 4 CPU cores (4K texture synthesis dominates)
~/dhvenv/bin/python render.py ../source/minjun_rig.blend ../renders --shots face_34,full_front --light studio --spp 256
```

`source/minjun_rig.blend` (+ `source/textures/`, relative paths) is the editable master: full-resolution body with subdivision, 163-bone armature, 75 shape keys, Cycles materials, 5 strand-hair systems (scalp, brows, stubble, vellus, forearm) + lid-following lash cards.
For Unreal Engine import use `assets/characters/minjun/minjun_lod0.fbx` (skeleton + morphs; rebuild materials in UE from the texture set).
