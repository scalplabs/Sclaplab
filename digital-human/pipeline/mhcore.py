"""
mhcore — pure-numpy loader for MakeHuman (hm08) CC0 data.

Reproduces the parts of MakeHuman 1.x we need, without its Qt/OpenGL app:
  * base mesh (OBJ, quads, face groups, UVs)
  * .target morph files (sparse vertex deltas)
  * macro modifier weighting (gender/age/muscle/weight/height/proportions/ethnicity)
  * generic modifiers (decr|incr pairs) and asymmetry targets
  * skeleton joints (mhskel: joint = mean of vertex group) + bone roll planes
  * skin weights (mhw)
  * proxy / clothes fitting (mhclo: barycentric + scaled offset)

Units: MakeHuman uses decimetres, Y-up. All public outputs are METRES, Y-up
(glTF convention). Blender conversion is done in the Blender scripts.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

import numpy as np

EXT = os.environ.get("DH_EXT", "/home/user/work/ext")
MH_DATA = os.path.join(EXT, "makehuman/makehuman/data")
MH_ASSETS = os.path.join(EXT, "makehuman-py3-assets/base")
CACHE = os.environ.get("DH_CACHE", "/home/user/work/cache")
os.makedirs(CACHE, exist_ok=True)

DM_TO_M = 0.1


# --------------------------------------------------------------------------- OBJ
@dataclass
class ObjMesh:
    v: np.ndarray                 # (N,3) float64, file units
    vt: np.ndarray                # (T,2)
    faces: list                   # list of lists of vertex indices
    faces_uv: list                # list of lists of uv indices (may be empty lists)
    face_group: list              # group name per face
    groups: dict = field(default_factory=dict)  # group -> list(face idx)

    def group_vertices(self, name: str) -> np.ndarray:
        vs = set()
        for fi in self.groups.get(name, []):
            vs.update(self.faces[fi])
        return np.array(sorted(vs), dtype=np.int64)


def load_obj(path: str) -> ObjMesh:
    v, vt, faces, fuv, fg = [], [], [], [], []
    g = "default"
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            if line.startswith("v "):
                p = line.split()
                v.append((float(p[1]), float(p[2]), float(p[3])))
            elif line.startswith("vt "):
                p = line.split()
                vt.append((float(p[1]), float(p[2])))
            elif line.startswith("f "):
                p = line.split()[1:]
                fv, ft = [], []
                for tok in p:
                    s = tok.split("/")
                    fv.append(int(s[0]) - 1)
                    if len(s) > 1 and s[1]:
                        ft.append(int(s[1]) - 1)
                faces.append(fv)
                fuv.append(ft)
                fg.append(g)
            elif line.startswith("g "):
                g = line.split(None, 1)[1].strip()
    groups: dict = {}
    for i, name in enumerate(fg):
        groups.setdefault(name, []).append(i)
    return ObjMesh(np.array(v, dtype=np.float64), np.array(vt, dtype=np.float64),
                   faces, fuv, fg, groups)


_BASE = None


def base_mesh() -> ObjMesh:
    global _BASE
    if _BASE is None:
        _BASE = load_obj(os.path.join(MH_DATA, "3dobjs/base.obj"))
    return _BASE


# ----------------------------------------------------------------------- targets
_TCACHE: dict = {}


def load_target(rel: str):
    """rel: path relative to data/targets, e.g. 'macrodetails/asian-male-young.target'"""
    if rel in _TCACHE:
        return _TCACHE[rel]
    path = os.path.join(MH_DATA, "targets", rel)
    idx, d = [], []
    with open(path) as fh:
        for line in fh:
            if not line.strip() or line.startswith("#"):
                continue
            p = line.split()
            idx.append(int(p[0]))
            d.append((float(p[1]), float(p[2]), float(p[3])))
    t = (np.array(idx, dtype=np.int64), np.array(d, dtype=np.float64).reshape(-1, 3))
    _TCACHE[rel] = t
    return t


def target_exists(rel: str) -> bool:
    return os.path.exists(os.path.join(MH_DATA, "targets", rel))


# ----------------------------------------------------------------- macro weights
@dataclass
class Macro:
    gender: float = 1.0          # 1 = male
    age: float = 0.5             # 0..1 (0.5 = 25y, 1 = 90y)
    muscle: float = 0.5
    weight: float = 0.5
    height: float = 0.5
    proportions: float = 0.5
    african: float = 0.0
    asian: float = 0.0
    caucasian: float = 1.0

    @staticmethod
    def age_from_years(y: float) -> float:
        if y < 25:
            return (y - 1.0) / (25.0 - 1.0) * 0.5
        return 0.5 + (y - 25.0) / (90.0 - 25.0) * 0.5

    def vals(self) -> dict:
        d = {}
        d["male"], d["female"] = self.gender, 1 - self.gender
        a = self.age
        if a < 0.5:
            d["old"] = 0.0
            d["baby"] = max(0.0, 1 - a * 5.333)
            d["young"] = max(0.0, (a - 0.1875) * 3.2)
            d["child"] = max(0.0, min(1.0, 5.333 * a) - d["young"])
        else:
            d["child"] = d["baby"] = 0.0
            d["old"] = max(0.0, a * 2 - 1)
            d["young"] = 1 - d["old"]

        def tri(x, lo, mid, hi):
            d[hi] = max(0.0, x * 2 - 1)
            d[lo] = max(0.0, 1 - x * 2)
            d[mid] = 1 - (d[hi] + d[lo])

        tri(self.weight, "minweight", "averageweight", "maxweight")
        tri(self.muscle, "minmuscle", "averagemuscle", "maxmuscle")
        tri(self.height, "minheight", "averageheight", "maxheight")
        d["idealproportions"] = max(0.0, self.proportions * 2 - 1)
        d["uncommonproportions"] = max(0.0, 1 - self.proportions * 2)
        d["regularproportions"] = 1 - max(d["idealproportions"], d["uncommonproportions"])
        s = self.african + self.asian + self.caucasian
        d["african"], d["asian"], d["caucasian"] = self.african / s, self.asian / s, self.caucasian / s
        return d


def macro_targets(m: Macro):
    """Yield (relpath, weight) for every macro target with non-zero weight."""
    v = m.vals()
    G, A = ("male", "female"), ("baby", "child", "young", "old")
    MU, W = ("minmuscle", "averagemuscle", "maxmuscle"), ("minweight", "averageweight", "maxweight")
    out = []
    for e in ("african", "asian", "caucasian"):
        for g in G:
            for a in A:
                out.append((f"macrodetails/{e}-{g}-{a}.target", v[e] * v[g] * v[a]))
    for g in G:
        for a in A:
            for mu in MU:
                for w in W:
                    base = v[g] * v[a] * v[mu] * v[w]
                    out.append((f"macrodetails/universal-{g}-{a}-{mu}-{w}.target", base))
                    for h in ("minheight", "maxheight"):
                        out.append((f"macrodetails/height/{g}-{a}-{mu}-{w}-{h}.target", base * v[h]))
                    for p in ("idealproportions", "uncommonproportions"):
                        out.append((f"macrodetails/proportions/{g}-{a}-{mu}-{w}-{p}.target", base * v[p]))
    return [(r, w) for r, w in out if w > 1e-6 and target_exists(r)]


# ---------------------------------------------------------------- generic mods
def _modifier_index():
    """map 'group/name' -> (decr_target, incr_target) or (None, single)"""
    idx = {}
    path = os.path.join(MH_DATA, "modifiers/modeling_modifiers.json")
    for grp in json.load(open(path)):
        g = grp["group"]
        for m in grp["modifiers"]:
            if "target" not in m:
                continue
            t = m["target"]
            if "min" in m and "max" in m:
                name = f"{g}/{t}-{m['min']}|{m['max']}"
                idx[name] = (f"{t}-{m['min']}", f"{t}-{m['max']}")
            else:
                idx[f"{g}/{t}"] = (None, t)
    return idx


_TFILES = None


def find_target_file(stem: str):
    """Find targets/**/<stem>.target"""
    global _TFILES
    if _TFILES is None:
        _TFILES = {}
        root = os.path.join(MH_DATA, "targets")
        for dp, _, fs in os.walk(root):
            for f in fs:
                if f.endswith(".target"):
                    _TFILES[f[:-7]] = os.path.relpath(os.path.join(dp, f), root)
    return _TFILES.get(stem)


def modifier_targets(mods: dict):
    """mods: {'nose/nose-scale-horiz-decr|incr': -0.2, 'head/head-oval': 0.3, 'r-eye-...':...}
    Also accepts direct target stems: {'stem': weight}."""
    index = _modifier_index()
    out = []
    for key, val in mods.items():
        if abs(val) < 1e-6:
            continue
        if key in index:
            dec, inc = index[key]
            if dec is None:
                stem, w = inc, val
            else:
                stem, w = (inc, val) if val > 0 else (dec, -val)
        else:
            stem, w = key, val
        rel = find_target_file(stem)
        if rel is None:
            raise KeyError(f"target not found for modifier {key} ({stem})")
        out.append((rel, w))
    return out


def apply_targets(base_v: np.ndarray, tlist) -> np.ndarray:
    v = base_v.copy()
    for rel, w in tlist:
        idx, d = load_target(rel)
        np.add.at(v, idx, d * w)
    return v


# ---------------------------------------------------------------------- skeleton
@dataclass
class Bone:
    name: str
    parent: str | None
    head: np.ndarray
    tail: np.ndarray
    plane: list | None


def load_skeleton(v_dm: np.ndarray, rig="default"):
    path = os.path.join(MH_DATA, f"rigs/{rig}.mhskel")
    if not os.path.exists(path):
        path = os.path.join(MH_ASSETS, f"rigs/{rig}.mhskel")
    d = json.load(open(path))
    jpos = {j: v_dm[np.array(vs)].mean(axis=0) for j, vs in d["joints"].items()}
    bones = {}
    for name, b in d["bones"].items():
        plane = d["planes"].get(b.get("rotation_plane")) if b.get("rotation_plane") else None
        bones[name] = Bone(name, b.get("parent"), jpos[b["head"]], jpos[b["tail"]], plane)
    wpath = os.path.join(os.path.dirname(path), d["weights_file"])
    weights = json.load(open(wpath))["weights"]
    return bones, jpos, weights


def bone_roll_normal(b: Bone, jpos: dict):
    """Normal of the bone's rotation plane (MakeHuman convention) used for roll."""
    if not b.plane:
        return None
    p = [jpos[j] for j in b.plane]
    n = np.cross(p[1] - p[0], p[2] - p[0])
    ln = np.linalg.norm(n)
    return n / ln if ln > 1e-12 else None


def bones_topo_order(bones: dict):
    order, seen = [], set()

    def visit(n):
        if n in seen:
            return
        p = bones[n].parent
        if p:
            visit(p)
        seen.add(n)
        order.append(n)

    for n in bones:
        visit(n)
    return order


# ------------------------------------------------------------------------ proxies
@dataclass
class Proxy:
    name: str
    obj: ObjMesh
    ref: np.ndarray        # (N,3) int  (single-vertex refs padded)
    w: np.ndarray          # (N,3)
    off: np.ndarray        # (N,3)
    scale: list | None     # [(v1,v2,den)]*3
    delete_verts: np.ndarray
    material: dict
    folder: str
    z_depth: int = 50


def _parse_mhmat(path):
    m = {}
    if not os.path.exists(path):
        return m
    for line in open(path, encoding="utf-8", errors="ignore"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        k, _, val = line.partition(" ")
        m.setdefault(k, val.strip())
    return m


def load_proxy(path: str) -> Proxy:
    folder = os.path.dirname(path)
    name, objf, matf = None, None, None
    scale = [None, None, None]
    refs, ws, offs = [], [], []
    dverts = []
    z_depth = 50
    mode = None
    for line in open(path, encoding="utf-8", errors="ignore"):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        p = s.split()
        if p[0] == "verts":
            mode = "verts"
            continue
        if p[0] == "delete_verts":
            mode = "delete"
            continue
        if p[0] in ("weights", "texVerts", "texFaces"):
            mode = None
            continue
        if mode == "verts" and re.match(r"^-?\d", p[0]):
            if len(p) == 1:
                refs.append((int(p[0]),) * 3)
                ws.append((1.0, 0.0, 0.0))
                offs.append((0.0, 0.0, 0.0))
            else:
                refs.append((int(p[0]), int(p[1]), int(p[2])))
                ws.append((float(p[3]), float(p[4]), float(p[5])))
                offs.append((float(p[6]), float(p[7]), float(p[8])) if len(p) >= 9 else (0, 0, 0))
            continue
        if mode == "delete" and re.match(r"^\d", p[0]):
            # tokens like "1355 - 1388 1393" or "1355-1388"
            toks = " ".join(p).replace(" - ", "-").split()
            for tok in toks:
                if "-" in tok:
                    a, b = tok.split("-")
                    dverts.extend(range(int(a), int(b) + 1))
                else:
                    dverts.append(int(tok))
            continue
        if p[0] == "name":
            name = p[1]
        elif p[0] == "obj_file":
            objf = p[1]
        elif p[0] == "material":
            matf = p[1]
        elif p[0] == "z_depth":
            z_depth = int(p[1])
        elif p[0] in ("x_scale", "y_scale", "z_scale"):
            i = "xyz".index(p[0][0])
            scale[i] = (int(p[1]), int(p[2]), float(p[3]))
    obj = load_obj(os.path.join(folder, objf))
    mat = _parse_mhmat(os.path.join(folder, matf)) if matf else {}
    dv = np.zeros(len(base_mesh().v), dtype=bool)
    if dverts:
        dv[np.array(dverts)] = True
    return Proxy(name, obj, np.array(refs), np.array(ws), np.array(offs),
                 scale if all(scale) else None, dv, mat, folder, z_depth)


def fit_proxy(px: Proxy, v_dm: np.ndarray) -> np.ndarray:
    M = np.eye(3)
    if px.scale:
        for n in range(3):
            v1, v2, den = px.scale[n]
            M[n, n] = abs(v_dm[v1][n] - v_dm[v2][n]) / den
    r, w = px.ref, px.w
    co = (v_dm[r[:, 0]] * w[:, 0, None] + v_dm[r[:, 1]] * w[:, 1, None] +
          v_dm[r[:, 2]] * w[:, 2, None] + (M @ px.off.T).T)
    return co


def proxy_weights(px: Proxy, base_weights: dict):
    """Map base-mesh bone weights onto proxy vertices through barycentric refs."""
    nb = len(base_mesh().v)
    out = {}
    for bone, lst in base_weights.items():
        a = np.zeros(nb)
        if not lst:
            continue
        arr = np.array(lst)
        a[arr[:, 0].astype(int)] = arr[:, 1]
        pw = (a[px.ref[:, 0]] * px.w[:, 0] + a[px.ref[:, 1]] * px.w[:, 1] + a[px.ref[:, 2]] * px.w[:, 2])
        if pw.max() > 1e-4:
            out[bone] = pw
    # normalize
    tot = np.zeros(len(px.ref))
    for a in out.values():
        tot += a
    tot[tot == 0] = 1
    for k in out:
        out[k] = out[k] / tot
    return out


def asset(*p):
    return os.path.join(MH_ASSETS, *p)
