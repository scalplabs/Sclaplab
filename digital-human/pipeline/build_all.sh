#!/usr/bin/env bash
# Full character build. Usage: bash build_all.sh [characters/minjun.json]
set -euo pipefail
cd "$(dirname "$0")"
CFG=${1:-characters/minjun.json}; ID=$(basename "$CFG" .json)
V=${DH_BPY_PY:-/home/user/work/venv/bin/python}; B=${DH_BUILD:-/home/user/work/build}; T=${DH_TEX:-/home/user/work/tex_$ID}; M=${DH_MAPS:-/home/user/work/maps_$ID}
RES=${DH_TEX_RES:-4096}
mkdir -p "$B" "$T"
$V build_character.py "$CFG" "$B/${ID}_s1.blend"
$V dump_landmarks.py "$B/${ID}_s1.blend" "$B/${ID}_landmarks.json"
$V bake_geometry_maps.py "$B/${ID}_s1.blend" "$M" "$RES"
python3 - "$M" <<'PY'
import sys, numpy as np, os
m = sys.argv[1]
for n in ("position", "normal_obj"):   # tex_skin reads *32.npy
    src = os.path.join(m, n + ".npy"); dst = os.path.join(m, n + "32.npy")
    if os.path.exists(src) and not os.path.exists(dst): np.save(dst, np.load(src).astype(np.float32))
PY
python3 tex_micro.py "$T"; python3 tex_eye.py "$T"
python3 tex_skin.py "$M" "$B/${ID}_landmarks.json" "$CFG" "$T"
$V lookdev.py "$B/${ID}_s1.blend" "$T" "$CFG" "$B/${ID}_ld.blend"
$V face_rig.py "$B/${ID}_ld.blend" "$B/${ID}_rig.blend" "$B/${ID}_rig_meta.json"
$V export_glb.py "$B/${ID}_rig.blend" "$T" ../assets "$B/${ID}_rig_meta.json"
echo "built $ID"
