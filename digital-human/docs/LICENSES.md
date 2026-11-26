# Third-party data, models and licenses

| Asset / dependency | Use | License | Source |
|---|---|---|---|
| MakeHuman 1.x data: hm08 base mesh, morph targets, default skeleton + weights, face pose units (BVH) | anatomical base, body/face shape, rig, FACS-like face units | **CC0 1.0** (explicitly released 2020; `LICENSE.ASSETS.md`) | github.com/makehumancommunity/makehuman |
| MPFB2 data: `rig.default.json` (bone rolls), `weights.default.json`, region masks (lips, eyelids, ears, nails) | rig construction, texture region masks | **CC0** (`LICENSE.ASSETS.md`) | github.com/makehumancommunity/mpfb2 |
| MakeHuman 1.1 system assets: skin albedo (low-frequency painted detail), teeth, tongue, eyebrow010, eyelashes02, male_casualsuit01, shoes06 | proxies / clothing / texture base | **CC0** (MakeHuman system assets; mirrored at github.com/dmaugis/makehuman-py3-assets — that mirror's repo-level AGPL notice covers its code; the assets themselves are the CC0 MakeHuman system assets) | MakeHuman 1.1 |
| Poly Haven HDRIs (brown_photostudio_02, hotel_room, cloudy_vondelpark, photo_studio_loft_hall, kloofendal_48d_partly_cloudy_puresky) 1k EXR | image-based lighting | **CC0** | polyhaven.com via huggingface.co/datasets/leodriesch/open-hdri-1k |
| facebook/wav2vec2-xlsr-53-espeak-cv-ft | phoneme forced alignment | **Apache-2.0** | huggingface.co (downloaded at install, not redistributed) |
| CMUdict | English pronunciation | BSD-2-Clause | github.com/cmusphinx/cmudict (downloaded at install) |
| three.js r170 (vendored under `web/vendor/three`) | real-time renderer | MIT | npm `three@0.170.0` |
| lil-gui (bundled with three.js examples) | dev UI | MIT | |
| Blender `bpy` 5.3 | pipeline / offline render (tool only) | GPL-3.0 (tool; outputs are not covered) | PyPI `bpy` |
| Typecast TTS / ElevenLabs | speech synthesis (runtime services) | commercial API terms of each provider | |
| Claude API (`claude-opus-5-5`) | dialogue / behaviour intent | Anthropic commercial terms | |

Everything else in `digital-human/` (pipeline code, shaders, runtime, generated textures, grooms, shapes, animation clips) was written for this project.

**Likeness:** the face is generated from parametric CC0 shape data (no scan of a real person). The name "Kim Min-jun" is a common placeholder name, not a real individual.
