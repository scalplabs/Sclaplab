"""Asset integrity tests (pure Python + numpy; parses GLB directly).

python3 tests/test_assets.py [assets/characters/minjun]
"""
import json
import os
import struct
import sys

import numpy as np

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "assets", "characters", "minjun")
ARKIT = ["browDownLeft", "browDownRight", "browInnerUp", "browOuterUpLeft", "browOuterUpRight", "cheekPuff", "cheekSquintLeft",
         "cheekSquintRight", "eyeBlinkLeft", "eyeBlinkRight", "eyeLookDownLeft", "eyeLookDownRight", "eyeLookInLeft", "eyeLookInRight",
         "eyeLookOutLeft", "eyeLookOutRight", "eyeLookUpLeft", "eyeLookUpRight", "eyeSquintLeft", "eyeSquintRight", "eyeWideLeft",
         "eyeWideRight", "jawForward", "jawLeft", "jawOpen", "jawRight", "mouthClose", "mouthDimpleLeft", "mouthDimpleRight",
         "mouthFrownLeft", "mouthFrownRight", "mouthFunnel", "mouthLeft", "mouthLowerDownLeft", "mouthLowerDownRight", "mouthPressLeft",
         "mouthPressRight", "mouthPucker", "mouthRight", "mouthRollLower", "mouthRollUpper", "mouthShrugLower", "mouthShrugUpper",
         "mouthSmileLeft", "mouthSmileRight", "mouthStretchLeft", "mouthStretchRight", "noseSneerLeft", "noseSneerRight", "tongueOut"]
CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def load_glb(path):
    b = open(path, "rb").read()
    magic, ver, length = struct.unpack("<III", b[:12])
    assert magic == 0x46546C67
    jl = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + jl])
    bl = struct.unpack("<I", b[20 + jl:24 + jl])[0]
    binc = b[28 + jl:28 + jl + bl]
    return j, binc


def accessor(j, binc, i):
    a = j["accessors"][i]
    n, comps = a["count"], NC[a["type"]]
    dt = CT[a["componentType"]]
    if "bufferView" in a:
        bv = j["bufferViews"][a["bufferView"]]
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride")
        isz = np.dtype(dt).itemsize * comps
        if stride and stride != isz:
            raw = np.frombuffer(binc, np.uint8, n * stride, off).reshape(n, stride)[:, :isz].copy()
            arr = raw.view(dt).reshape(n, comps)
        else:
            arr = np.frombuffer(binc, dt, n * comps, off).reshape(n, comps).copy()
    else:
        arr = np.zeros((n, comps), dt)
    if "sparse" in a:
        sp = a["sparse"]
        ib, vb = j["bufferViews"][sp["indices"]["bufferView"]], j["bufferViews"][sp["values"]["bufferView"]]
        idx = np.frombuffer(binc, CT[sp["indices"]["componentType"]], sp["count"], ib.get("byteOffset", 0) + sp["indices"].get("byteOffset", 0))
        val = np.frombuffer(binc, dt, sp["count"] * comps, vb.get("byteOffset", 0) + sp["values"].get("byteOffset", 0)).reshape(-1, comps)
        arr = arr.astype(np.float32) if dt == np.float32 else arr
        arr[idx.astype(int)] = val
    if a.get("normalized") and dt in (np.uint8, np.uint16):
        arr = arr.astype(np.float32) / np.iinfo(dt).max
    return arr


def main():
    meta = json.load(open(os.path.join(ROOT, "rig_meta.json")))
    for lod in (0, 1, 2):
        path = os.path.join(ROOT, f"minjun_lod{lod}.glb")
        check(f"lod{lod}: file exists & loads", os.path.exists(path))
        j, binc = load_glb(path)
        skin = j["skins"][0]
        joints = skin["joints"]
        check(f"lod{lod}: skeleton has 163 joints", len(joints) == 163, str(len(joints)))
        # hierarchy: every joint reachable from exactly one root, no cycles
        parent = {}
        for ni, node in enumerate(j["nodes"]):
            for c in node.get("children", []):
                parent[c] = ni
        roots = [jt for jt in joints if parent.get(jt) not in joints]
        check(f"lod{lod}: single skeleton root", len(roots) == 1, j["nodes"][roots[0]]["name"] if roots else "")
        if lod == 0:
            names = {j["nodes"][jt]["name"] for jt in joints}
            req = ["root", "spine05", "spine01", "neck01", "head", "jaw", "eye.L", "eye.R", "clavicle.L", "shoulder01.L", "upperarm01.L",
                   "upperarm02.L", "lowerarm01.L", "lowerarm02.L", "wrist.L", "finger1-3.L", "finger5-3.R", "upperleg01.L", "upperleg02.L",
                   "lowerleg01.R", "foot.R", "toe1-1.L", "toe5-3.R", "tongue00", "oris01", "levator02.L"]
            missing = [r for r in req if r not in names]
            check("lod0: required joints (root..toes, jaw, eyes, twist bones, facial)", not missing, ",".join(missing))
        tot_tris = 0
        allnames = set()
        corr_dead_on_body = []
        for m in j["meshes"]:
            for pr in m["primitives"]:
                pos = accessor(j, binc, pr["attributes"]["POSITION"])
                ind = accessor(j, binc, pr["indices"]).ravel() if "indices" in pr else np.arange(len(pos))
                tot_tris += len(ind) // 3
                ok_nan = np.isfinite(pos).all()
                ok_idx = ind.max() < len(pos)
                tri = ind.reshape(-1, 3)
                a, b2, c = pos[tri[:, 0]], pos[tri[:, 1]], pos[tri[:, 2]]
                area = np.linalg.norm(np.cross(b2 - a, c - a), axis=1) / 2
                degen = (area < 1e-12).mean()
                if "TEXCOORD_0" in pr["attributes"]:
                    uv = accessor(j, binc, pr["attributes"]["TEXCOORD_0"])
                    uv_ok = np.isfinite(uv).all() and uv.min() > -0.01 and uv.max() < 1.01
                else:
                    uv_ok = True
                w = accessor(j, binc, pr["attributes"]["WEIGHTS_0"]) if "WEIGHTS_0" in pr["attributes"] else None
                wsum_ok = True
                if w is not None:
                    s = w.astype(np.float64).sum(1)
                    wsum_ok = np.abs(s - 1).max() < 0.02
                jidx_ok = True
                if "JOINTS_0" in pr["attributes"]:
                    ji = accessor(j, binc, pr["attributes"]["JOINTS_0"])
                    jidx_ok = ji.max() < len(joints)
                if lod == 0:
                    check(f"lod0 mesh {m['name']}: finite verts, valid indices, UV in [0,1], weights sum=1, joint idx valid, degenerate<0.5%",
                          ok_nan and ok_idx and uv_ok and wsum_ok and jidx_ok and degen < 0.005,
                          f"v={len(pos)} t={len(tri)} degen={degen*100:.2f}% wsum={'ok' if wsum_ok else 'BAD'} uv={'ok' if uv_ok else 'BAD'}")
                if lod == 0:
                    allnames.update(m.get("extras", {}).get("targetNames", []))
                if m["name"] == "DH_Body" and lod == 0:
                    tn = m.get("extras", {}).get("targetNames", [])
                    # every ARKit target actually moves geometry
                    dead = []
                    for ti, t in enumerate(pr.get("targets", [])):
                        d = accessor(j, binc, t["POSITION"])
                        if np.abs(d).max() < 1e-5:
                            dead.append(tn[ti])
                    check("lod0 body: no zero (dead) face morph targets", not [d for d in dead if not d.startswith("corr_")], ",".join(dead))
                    corr_dead_on_body = [d for d in dead if d.startswith("corr_")]
                if lod == 0 and m["name"].startswith("DH_male"):
                    tn = m.get("extras", {}).get("targetNames", [])
                    covered = [c for c in corr_dead_on_body if c in tn]
                    check("lod0 clothes carry correctives for skin regions hidden under clothing", set(covered) == set(corr_dead_on_body),
                          f"{len(covered)}/{len(corr_dead_on_body)}")
        if lod == 0:
            miss = [a for a in ARKIT if a not in allnames]
            check("lod0: all 52 ARKit blendshapes present (union over face meshes)", not miss, f"missing {miss}")
        check(f"lod{lod}: triangle budget", tot_tris < {0: 400000, 1: 260000, 2: 120000}[lod], f"{tot_tris} tris")
    check("rig_meta: correctives with drivers", len(meta.get("correctives", {})) == 12)
    check("rig_meta: joint limits table", len(meta.get("joint_limits", {})) >= 20)
    check("rig_meta: stature 180 cm", abs(meta["stature_cm"] - 180.0) < 0.05, f"{meta['stature_cm']:.2f}")
    tex = os.path.join(ROOT, "textures")
    from PIL import Image
    a4 = Image.open(os.path.join(tex, "skin_albedo_4k.jpg"))
    check("textures: 4K face/body albedo", a4.size == (4096, 4096), str(a4.size))
    for f in ["skin_normal_4k.png", "skin_rough_spec_2k.png", "skin_masks_2k.png", "skin_wrinkle_normal_2k.jpg", "skin_wrinkle_mask_1k.png",
              "skin_micro_normal.jpg", "eye_albedo_2k.jpg", "eye_normal_1k.jpg", "hair_card_atlas.png", "teeth.png", "tongue.png"]:
        check(f"textures: {f}", os.path.exists(os.path.join(tex, f)))
    n_fail = sum(1 for r in results if not r[1])
    print(f"\n{len(results) - n_fail}/{len(results)} passed")
    json.dump([{"test": n, "pass": p, "detail": d} for n, p, d in results], open(os.path.join(os.path.dirname(__file__), "results_assets.json"), "w"), indent=1)
    return n_fail


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
