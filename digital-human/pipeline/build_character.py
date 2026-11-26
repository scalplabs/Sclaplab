"""
Stage 1 — build the character in Blender from data.

  venv/bin/python pipeline/build_character.py characters/minjun.json OUT.blend

Produces: body mesh (hm08 body group, 13.4k quads), 163-bone deform skeleton
(MakeHuman default incl. twist + face bones), normalized skin weights,
fitted proxies (brows, lashes, teeth, tongue, hair cards, clothes, shoes),
procedurally constructed eyeballs (sclera / iris / cornea / tear-line meshes).
All geometry metres, Blender Z-up, character facing -Y, soles on Z=0.
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mhcore as mh  # noqa: E402

MPFB = os.path.join(mh.EXT, "mpfb2/src/mpfb/data")


def to_bl(v_dm):
    v = np.asarray(v_dm, dtype=np.float64)
    return np.stack([v[:, 0], -v[:, 2], v[:, 1]], axis=1) * mh.DM_TO_M


def resolve_asset(rel):
    for root in (mh.MH_ASSETS, mh.MH_DATA):
        p = os.path.join(root, rel)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(rel)


# ------------------------------------------------------------------ shape solve
def solve_shape(cfg):
    B = mh.base_mesh()
    M = cfg["macro"]
    body_v = B.group_vertices("body")
    extra = mh.modifier_targets(cfg.get("modifiers", {})) + mh.modifier_targets(cfg.get("asymmetry", {}))

    def build(h):
        m = mh.Macro(gender=M["gender"], age=mh.Macro.age_from_years(M["age_years"]), muscle=M["muscle"],
                     weight=M["weight"], height=h, proportions=M["proportions"], african=M["african"],
                     asian=M["asian"], caucasian=M["caucasian"])
        return mh.apply_targets(B.v, mh.macro_targets(m) + extra)

    lo, hi = 0.0, 1.0
    for _ in range(30):  # bisection on the height macro to hit exact stature
        mid = (lo + hi) / 2
        v = build(mid)
        hcm = (v[body_v, 1].max() - v[body_v, 1].min()) * 10
        if hcm < M["height_cm"]:
            lo = mid
        else:
            hi = mid
    v = build((lo + hi) / 2)
    hcm = (v[body_v, 1].max() - v[body_v, 1].min()) * 10
    print(f"[shape] height macro={(lo+hi)/2:.4f} -> stature {hcm:.2f} cm")
    return v, hcm


# ------------------------------------------------------------------ mesh helpers
def make_mesh(name, verts_bl, faces, uvs=None, face_uvs=None, smooth=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(p) for p in verts_bl], [], [tuple(f) for f in faces])
    me.update()
    if uvs is not None and face_uvs is not None and len(uvs):
        uvl = me.uv_layers.new(name="UVMap")
        loop_uv = []
        for f in face_uvs:
            loop_uv.extend(f)
        arr = np.asarray(uvs)[np.array(loop_uv)]
        uvl.data.foreach_set("uv", arr.ravel())
    if smooth:
        me.shape_keys  # noqa
        for p in me.polygons:
            p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def sub_mesh(obj: mh.ObjMesh, face_ids):
    """extract faces -> (vert index map, faces remapped, face uvs)"""
    used = sorted({vi for fi in face_ids for vi in obj.faces[fi]})
    remap = {o: n for n, o in enumerate(used)}
    faces = [[remap[vi] for vi in obj.faces[fi]] for fi in face_ids]
    fuv = [obj.faces_uv[fi] for fi in face_ids]
    return np.array(used), faces, fuv


# ------------------------------------------------------------------ armature
def build_armature(v_dm, offset):
    rig = json.load(open(os.path.join(MPFB, "rigs/standard/rig.default.json")))
    B = mh.base_mesh()
    vb = to_bl(v_dm) + offset
    cube_cache = {}

    def pos(spec):
        s = spec["strategy"]
        if s == "CUBE":
            n = spec["cube_name"]
            if n not in cube_cache:
                cube_cache[n] = vb[B.group_vertices(n)].mean(axis=0)
            return cube_cache[n]
        if s == "MEAN":
            return vb[np.array(spec["vertex_indices"])].mean(axis=0)
        if s == "VERTEX":
            return vb[spec["vertex_index"]]
        raise ValueError(s)

    arm = bpy.data.armatures.new("DH_Skeleton")
    arm.display_type = "OCTAHEDRAL"
    ob = bpy.data.objects.new("DH_Rig", arm)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.edit_bones
    for name, b in rig.items():
        e = eb.new(name)
        e.head = Vector(pos(b["head"]))
        e.tail = Vector(pos(b["tail"]))
        if (e.tail - e.head).length < 1e-4:
            e.tail = e.head + Vector((0, 0, 0.01))
        e.roll = b.get("roll", 0.0)
    for name, b in rig.items():
        if b.get("parent"):
            eb[name].parent = eb[b["parent"]]
            eb[name].use_connect = bool(b.get("use_connect", False))
    bpy.ops.object.mode_set(mode="OBJECT")
    return ob


def bind(ob_mesh, rig_ob, weights_by_bone, nverts):
    """weights_by_bone: bone -> dense array(nverts)"""
    tot = np.zeros(nverts)
    for a in weights_by_bone.values():
        tot += a
    tot[tot <= 0] = 1.0
    for bone, a in weights_by_bone.items():
        a = a / tot
        nz = np.nonzero(a > 1e-4)[0]
        if not len(nz):
            continue
        vg = ob_mesh.vertex_groups.new(name=bone)
        for i in nz:
            vg.add([int(i)], float(a[i]), "REPLACE")
    mod = ob_mesh.modifiers.new("Armature", "ARMATURE")
    mod.object = rig_ob
    mod.use_deform_preserve_volume = False
    ob_mesh.parent = rig_ob


def dense_base_weights():
    W = json.load(open(os.path.join(MPFB, "rigs/standard/weights.default.json")))["weights"]
    n = len(mh.base_mesh().v)
    out = {}
    for bone, lst in W.items():
        if not lst:
            continue
        a = np.zeros(n)
        arr = np.array(lst)
        a[arr[:, 0].astype(int)] = arr[:, 1]
        out[bone] = a
    return out


def proxy_dense_weights(px, base_w):
    out = {}
    for bone, a in base_w.items():
        pw = a[px.ref[:, 0]] * px.w[:, 0] + a[px.ref[:, 1]] * px.w[:, 1] + a[px.ref[:, 2]] * px.w[:, 2]
        if pw.max() > 1e-4:
            out[bone] = pw
    return out


# ------------------------------------------------------------------ eyes
def build_eye(name, center, rig_ob, bone, R=0.0120, Rc=0.0078, iris_d=0.0117):
    """Anatomical eyeball (all metres). Gaze axis = -Y.
      sclera sphere R=12 mm, cornea sphere Rc=7.8 mm joined at the limbus,
      iris (11.7 mm) a shallow cone ~0.5 mm behind the limbus plane,
      anterior chamber between iris and cornea (refraction handled by the cornea material).
    Meshes: <name> (sclera+iris, polar UV centred on pupil), <name>_Cornea (transparent)."""
    import bmesh
    objs = []
    lim_ang = math.asin((iris_d / 2) / R)            # ~29.2 deg
    lim_depth = R * math.cos(lim_ang)                # limbus plane distance from centre
    iris_depth = lim_depth - 0.0006                  # iris plane slightly behind limbus
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=96, v_segments=64, radius=R, calc_uvs=False)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(90), 3, "X"))
    for v in bm.verts:
        d = v.co.normalized()
        ang = math.acos(max(-1, min(1, -d.y)))
        if ang < lim_ang:
            t = ang / lim_ang                        # 0 pupil .. 1 limbus
            rr = t * iris_d / 2
            # iris surface: slight anterior bulge at collarette, pupil margin set back
            y = -iris_depth + 0.00035 * math.sin(math.pi * min(1, t * 1.6)) - 0.0002 * (1 - t)
            v.co = Vector((d.x, 0, d.z)).normalized() * rr if rr > 1e-9 else Vector((0, 0, 0))
            v.co.y = y
    me = bpy.data.meshes.new(name + "_mesh")
    bm.to_mesh(me)
    bm.free()
    uvl = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        poly.use_smooth = True
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            # angle from gaze axis measured on the original sphere direction
            r_xy = math.hypot(co.x, co.z)
            if co.y < -iris_depth + 0.001 and r_xy <= iris_d / 2 + 1e-6:
                ang = math.asin(min(1.0, r_xy / R))
            else:
                ang = math.acos(max(-1, min(1, -co.y / max(co.length, 1e-9))))
            a = ang / math.pi
            phi = math.atan2(co.z, co.x)
            uvl.data[li].uv = (0.5 + 0.5 * a * math.cos(phi), 0.5 + 0.5 * a * math.sin(phi))
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = center
    ob["eye_radius"] = R
    ob["iris_uv_radius"] = 0.5 * lim_ang / math.pi
    objs.append(ob)

    # Cornea: sphere radius Rc whose cap meets the limbus circle exactly
    sag = Rc - math.sqrt(Rc * Rc - (iris_d / 2) ** 2)
    cc = -(lim_depth + sag - Rc)                     # cornea sphere centre (y)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=96, v_segments=48, radius=Rc, calc_uvs=False)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(90), 3, "X"))
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, cc, 0))
    kill = [v for v in bm.verts if v.co.y > -lim_depth + 1e-5]
    bmesh.ops.delete(bm, geom=kill, context="VERTS")
    # skirt: extend cornea a little over the sclera (tear film continuity), radius R+0.1mm
    me = bpy.data.meshes.new(name + "_cornea_mesh")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    co = bpy.data.objects.new(name + "_Cornea", me)
    bpy.context.scene.collection.objects.link(co)
    co.location = center
    objs.append(co)
    for o in objs:
        vg = o.vertex_groups.new(name=bone)
        vg.add(list(range(len(o.data.vertices))), 1.0, "REPLACE")
        m = o.modifiers.new("Armature", "ARMATURE")
        m.object = rig_ob
        o.parent = rig_ob
    return objs, lim_depth + sag


# ------------------------------------------------------------------ main
def main(cfg_path, out_blend):
    cfg = json.load(open(cfg_path))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.unit_settings.system = "METRIC"

    v_dm, stature = solve_shape(cfg)
    B = mh.base_mesh()
    vb_all = to_bl(v_dm)

    # Ground: lowest point of shoes (or body sole) on Z=0, centre X/Y on pelvis
    A = cfg["assets"]
    proxies = {}
    for key in ("eyebrows", "eyelashes", "teeth", "tongue", "hair_cards"):
        if A.get(key):
            proxies[key] = mh.load_proxy(resolve_asset(A[key]))
    for i, c in enumerate(A.get("clothes", [])):
        proxies[f"cloth{i}"] = mh.load_proxy(resolve_asset(c))
    fitted = {k: to_bl(mh.fit_proxy(p, v_dm)) for k, p in proxies.items()}

    body_ids = B.groups["body"]
    bidx, bfaces, bfuv = sub_mesh(B, body_ids)
    zmin = vb_all[bidx, 2].min()
    for k, p in proxies.items():
        if k.startswith("cloth") and "shoe" in p.name:
            zmin = min(zmin, fitted[k][:, 2].min())
    cx, cy = vb_all[bidx, 0].mean(), vb_all[bidx, 1].mean()
    offset = np.array([-cx, -cy, -zmin])
    vb_all = vb_all + offset
    for k in fitted:
        fitted[k] = fitted[k] + offset

    rig = build_armature(v_dm, offset)
    base_w = dense_base_weights()

    # Body
    body = make_mesh("DH_Body", vb_all[bidx], bfaces, B.vt, bfuv)
    body["mh_base_index"] = 0
    # store base-mesh index per vertex (needed for target-driven blendshapes later)
    attr = body.data.attributes.new("mh_index", "INT", "POINT")
    attr.data.foreach_set("value", bidx.astype(np.int32))
    bind(body, rig, {b: a[bidx] for b, a in base_w.items()}, len(bidx))

    # Hidden-under-clothes mask (MakeHuman delete_verts) as vertex group, used by Mask modifier
    hide = np.zeros(len(B.v), bool)
    for k, p in proxies.items():
        if k.startswith("cloth"):
            hide |= p.delete_verts
    hv = np.nonzero(hide[bidx])[0]
    vg = body.vertex_groups.new(name="DH_hidden_by_clothes")
    if len(hv):
        vg.add([int(i) for i in hv], 1.0, "REPLACE")

    # Proxies
    made = {}
    for k, p in proxies.items():
        ob = make_mesh(f"DH_{k.capitalize() if not k.startswith('cloth') else p.name}",
                       fitted[k], p.obj.faces, p.obj.vt, p.obj.faces_uv)
        ob["mh_proxy"] = p.name
        ob["mh_folder"] = p.folder
        ob["mh_material"] = json.dumps(p.material)
        ob["z_depth"] = p.z_depth
        bind(ob, rig, proxy_dense_weights(p, base_w), len(fitted[k]))
        made[k] = ob

    # Eyes: MakeHuman's helper sphere (~30 mm) is larger than a real eyeball (~24 mm).
    # Keep its corneal apex (lid fit) and place an anatomical eye behind it.
    bpy.context.view_layer.objects.active = rig
    eye_centres = {}
    for side in ("l", "r"):
        ev = vb_all[B.group_vertices(f"helper-{side}-eye")]
        c = ev.mean(axis=0)
        apex_y = ev[:, 1].min()          # most forward (-Y) point
        eye_centres[side] = np.array([c[0], apex_y + 0.01315, c[2]])
    bpy.ops.object.mode_set(mode="EDIT")
    for side, bone in (("l", "eye.L"), ("r", "eye.R")):
        e = rig.data.edit_bones[bone]
        d = e.tail - e.head
        e.head = Vector(eye_centres[side])
        e.tail = e.head + Vector((0, -0.03, 0))   # bone Y axis = gaze direction
        e.roll = 0.0
    bpy.ops.object.mode_set(mode="OBJECT")
    for side, bone in (("l", "eye.L"), ("r", "eye.R")):
        objs, apex = build_eye(f"DH_Eye_{side.upper()}", Vector(eye_centres[side]), rig, bone)
        print(f"[eye {side}] centre {eye_centres[side]} apex {apex*1000:.2f} mm")

    # metadata
    scn["dh_character"] = json.dumps(cfg)
    scn["dh_stature_cm"] = stature
    os.makedirs(os.path.dirname(out_blend), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=out_blend)
    print("[saved]", out_blend)
    print("[stats] body verts", len(bidx), "faces", len(bfaces), "bones", len(rig.data.bones))


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    main(a[0], a[1])
