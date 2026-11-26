"""Stage 3 — facial blendshapes (ARKit 52 + extras) and body pose-space correctives.

venv/bin/python pipeline/face_rig.py IN.blend OUT.blend OUT_rig_meta.json

1. Parse MakeHuman CC0 face-poseunits.bvh (60 units, bone-driven, FACS-like).
2. For each unit pose the face bones, evaluate armature deformation of every face-related mesh,
   store the rest-space delta (unit "basis").
3. Compose ARKit shapes as weighted sums of units, with left/right/region masks and a few
   synthesised shapes (mouthClose, mouthPress, mouthFunnel ...). Shape keys are written to all
   meshes that move with the face (body, brows, lashes, teeth, tongue, tearline, occlusion,
   caruncle, hair cards). Eyeballs are bone-driven (eye.L/R) at runtime, not shape keys.
4. Body correctives: for elbow/knee/shoulder/hip/wrist flexion, the difference between
   dual-quaternion (volume preserving) and linear skinning is inverse-skinned into rest space,
   plus anatomical muscle bulge (biceps, calf), and saved as shape keys with driver metadata.
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mhcore as mh  # noqa: E402

BVH = os.path.join(mh.MH_DATA, "poseunits/face-poseunits.bvh")
UNITS = json.load(open(os.path.join(mh.MH_DATA, "poseunits/face-poseunits.json")))["framemapping"]

FACE_MESH_PREFIX = ("DH_Body", "DH_Eyebrows", "DH_Eyelashes", "DH_Teeth", "DH_Tongue", "DH_Tearline",
                    "DH_EyeOcclusion", "DH_Caruncle", "DH_HairCards")


def parse_bvh(path):
    names, chans = [], []
    lines = open(path).read().split("\n")
    i = 0
    frames = []
    while i < len(lines):
        t = lines[i].split()
        if t and t[0] in ("ROOT", "JOINT"):
            names.append(t[1])
        elif t and t[0] == "CHANNELS":
            chans.append(t[2:])
        elif t and t[0] == "MOTION":
            n = int(lines[i + 1].split()[1])
            for k in range(n):
                frames.append([float(x) for x in lines[i + 3 + k].split()])
            break
        i += 1
    out = []
    for fr in frames:
        pos = 0
        d = {}
        for nm, ch in zip(names, chans):
            vals = fr[pos:pos + len(ch)]
            pos += len(ch)
            rot = [(c[0], v) for c, v in zip(ch, vals) if c.endswith("rotation")]
            d[nm] = rot
        out.append(d)
    return out


def rot_matrix(rot):
    """BVH: rotations applied in listed channel order (intrinsic) -> R = R1 @ R2 @ R3"""
    M = Matrix.Identity(3)
    for ax, deg in rot:
        M = M @ Matrix.Rotation(math.radians(deg), 3, ax)
    return M


def eval_coords(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    co = np.zeros(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    ev.to_mesh_clear()
    return co.reshape(-1, 3)


def rest_coords(ob):
    co = np.zeros(len(ob.data.vertices) * 3, np.float32)
    ob.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def reset_pose(rig):
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)


def smooth_lr(x, width=0.006):
    """weight of the character's LEFT side (+x), 0.5 on midline"""
    return np.clip(0.5 + x / (2 * width), 0, 1)


def main(blend_in, blend_out, meta_out):
    bpy.ops.wm.open_mainfile(filepath=blend_in)
    rig = bpy.data.objects["DH_Rig"]
    face_obs = [o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith(FACE_MESH_PREFIX)]
    # disable non-armature modifiers for evaluation
    saved = {}
    for o in face_obs:
        for m in o.modifiers:
            if m.type != "ARMATURE":
                saved[(o.name, m.name)] = m.show_viewport
                m.show_viewport = False
    rests = {o.name: rest_coords(o) for o in face_obs}
    frames = parse_bvh(BVH)
    print("[bvh] frames", len(frames), "units", len(UNITS))
    bones = {b.name: b for b in rig.data.bones}
    # Rest armature-space 3x3 of each bone
    rest3 = {b.name: b.matrix_local.to_3x3() for b in rig.data.bones}

    # Determine BVH axis convention by testing JawDrop: the chin must move DOWN (-Z) and forward a bit.
    def apply_unit(fr, conv):
        reset_pose(rig)
        for bn, rot in fr.items():
            if bn not in bones or bn in ("root",) or not rot:
                continue
            if all(abs(v) < 1e-6 for _, v in rot):
                continue
            Rw = rot_matrix(rot)
            if conv == "yup":
                C = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))
                Rw = C @ Rw @ C.transposed()
            # BVH rotation is expressed in the parent-aligned global frame -> bone local
            Rl = rest3[bn].transposed() @ Rw @ rest3[bn]
            pb = rig.pose.bones[bn]
            pb.rotation_mode = "QUATERNION"
            pb.rotation_quaternion = Rl.to_quaternion()
        bpy.context.view_layer.update()

    body = bpy.data.objects["DH_Body"]
    chin_idx = int(np.argmin(rests["DH_Body"][:, 2] + 10 * np.abs(rests["DH_Body"][:, 0]) -
                             100 * (rests["DH_Body"][:, 2] > 1.5) * 0))
    # pick a chin vertex: front-most vertex near midline between mouth and neck
    rb = rests["DH_Body"]
    eye_z = bones["eye.L"].head_local.z
    cand = np.nonzero((np.abs(rb[:, 0]) < 0.004) & (rb[:, 2] < eye_z - 0.10) & (rb[:, 2] > eye_z - 0.14))[0]
    chin_idx = cand[np.argmin(rb[cand, 1])]
    ji = UNITS.index("JawDrop")
    best = None
    for conv in ("zup", "yup"):
        apply_unit(frames[ji], conv)
        d = eval_coords(body)[chin_idx] - rb[chin_idx]
        print(f"[conv {conv}] JawDrop chin delta mm", (d * 1000).round(2))
        score = -d[2]
        if best is None or score > best[0]:
            best = (score, conv)
    conv = best[1]
    print("[conv] using", conv)

    # ---- bake unit deltas
    unit_d = {}
    for ui, uname in enumerate(UNITS):
        if uname == "Rest":
            continue
        apply_unit(frames[ui], conv)
        unit_d[uname] = {o.name: eval_coords(o) - rests[o.name] for o in face_obs}
    reset_pose(rig)
    bpy.context.view_layer.update()
    mags = {u: float(np.abs(d["DH_Body"]).max() * 1000) for u, d in unit_d.items()}
    print("[units] max displacement mm:", {k: round(v, 1) for k, v in mags.items()})

    # ---- region masks (per object, on rest coords)
    def lips_w(co):
        # lips zone: around mouth in head frame
        mo = np.array(bones["oris01"].head_local)
        return np.exp(-(((co[:, 0] - mo[0]) / 0.03) ** 2 + ((co[:, 2] - (mo[2] + 0.02)) / 0.025) ** 2))

    def U(name, w=1.0):
        return (name, w)

    L, R = "L", "R"
    # ARKit definitions: list of (unit, weight, side-mask)
    defs = {
        "browDownLeft": [("LeftBrowDown", 1, None)], "browDownRight": [("RightBrowDown", 1, None)],
        "browInnerUp": [("LeftInnerBrowUp", 1, None), ("RightInnerBrowUp", 1, None)],
        "browOuterUpLeft": [("LeftOuterBrowUp", 1, None)], "browOuterUpRight": [("RightOuterBrowUp", 1, None)],
        "cheekPuff": [("CheeksPump", 1, None)],
        "cheekSquintLeft": [("LeftCheekUp", 1, None)], "cheekSquintRight": [("RightCheekUp", 1, None)],
        "eyeBlinkLeft": [("LeftUpperLidClosed", 1, None), ("LeftLowerLidUp", 0.25, None)],
        "eyeBlinkRight": [("RightUpperLidClosed", 1, None), ("RightLowerLidUp", 0.25, None)],
        "eyeLookDownLeft": [("LeftEyeDown", 1, "noeye")], "eyeLookDownRight": [("RightEyeDown", 1, "noeye")],
        "eyeLookUpLeft": [("LeftEyeUp", 1, "noeye")], "eyeLookUpRight": [("RightEyeUp", 1, "noeye")],
        "eyeLookInLeft": [("LeftEyeturnRight", 1, "noeye")], "eyeLookInRight": [("RightEyeturnLeft", 1, "noeye")],
        "eyeLookOutLeft": [("LeftEyeturnLeft", 1, "noeye")], "eyeLookOutRight": [("RightEyeturnRight", 1, "noeye")],
        "eyeSquintLeft": [("LeftLowerLidUp", 1, None), ("LeftCheekUp", 0.25, None)],
        "eyeSquintRight": [("RightLowerLidUp", 1, None), ("RightCheekUp", 0.25, None)],
        "eyeWideLeft": [("LeftUpperLidOpen", 1, None)], "eyeWideRight": [("RightUpperLidOpen", 1, None)],
        "jawOpen": [("JawDrop", 1, None)], "jawForward": [("ChinForward", 1, None)],
        "jawLeft": [("ChinLeft", 1, None)], "jawRight": [("ChinRight", 1, None)],
        "mouthClose": [("JawDrop", -1, "lips_lower")],
        "mouthFunnel": [("LipsKiss", 0.55, None), ("lowerLipForward", 0.6, None), ("UpperLipForward", 0.6, None),
                        ("JawDrop", 0.12, None)],
        "mouthPucker": [("LipsKiss", 1, None)],
        "mouthLeft": [("MouthMoveLeft", 1, None)], "mouthRight": [("MouthMoveRight", 1, None)],
        "mouthSmileLeft": [("MouthLeftPullUp", 1.45, None), ("MouthLeftPullSide", 0.35, None), ("LeftCheekUp", 0.45, None)],
        "mouthSmileRight": [("MouthRightPullUp", 1.45, None), ("MouthRightPullSide", 0.35, None), ("RightCheekUp", 0.45, None)],
        "mouthFrownLeft": [("MouthLeftPullDown", 1.8, None), ("MouthLeftPlatysma", 0.2, None)], "mouthFrownRight": [("MouthRightPullDown", 1.8, None), ("MouthRightPlatysma", 0.2, None)],
        "mouthDimpleLeft": [("MouthLeftPullSide", 0.55, None)], "mouthDimpleRight": [("MouthRightPullSide", 0.55, None)],
        "mouthStretchLeft": [("MouthLeftPlatysma", 1, None), ("MouthLeftPullSide", 0.3, None)],
        "mouthStretchRight": [("MouthRightPlatysma", 1, None), ("MouthRightPullSide", 0.3, None)],
        "mouthRollLower": [("lowerLipBackward", 1, None)], "mouthRollUpper": [("UpperLipBackward", 1, None)],
        "mouthShrugLower": [("lowerLipUp", 1, None)], "mouthShrugUpper": [("UpperLipUp", 0.45, None)],
        "mouthPressLeft": [("lowerLipUp", 0.45, "L"), ("MouthLeftPullSide", 0.25, None)],
        "mouthPressRight": [("lowerLipUp", 0.45, "R"), ("MouthRightPullSide", 0.25, None)],
        "mouthLowerDownLeft": [("lowerLipDown", 1, "L")], "mouthLowerDownRight": [("lowerLipDown", 1, "R")],
        "mouthUpperUpLeft": [("UpperLipUp", 1, "L")], "mouthUpperUpRight": [("UpperLipUp", 1, "R")],
        "noseSneerLeft": [("NoseWrinkler", 1, "L"), ("UpperLipUp", 0.25, "L")],
        "noseSneerRight": [("NoseWrinkler", 1, "R"), ("UpperLipUp", 0.25, "R")],
        "tongueOut": [("TongueOut", 1, None)],
        # extras (FACS-style, used by speech / idle)
        "tongueUp": [("TongueUp", 1, None)], "tongueDown": [("TongueDown", 1, None)],
        "tongueLeft": [("TongueLeft", 1, None)], "tongueRight": [("TongueRight", 1, None)],
        "tongueTipUp": [("TonguePointUp", 1, None)], "tongueTipDown": [("TonguePointDown", 1, None)],
        "tongueWide": [("TongueUshape", 1, None)],
        "cheekSuck": [("CheeksSuck", 1, None)], "nasolabialDeepen": [("NasolabialDeepener", 1, None)],
        "jawOpenStretched": [("JawDropStretched", 1, None)], "chinDown": [("ChinDown", 1, None)],
    }
    mo = np.array(bones["oris01"].head_local)
    shapes = {}
    for sk, comps in defs.items():
        per_ob = {}
        for o in face_obs:
            co = rests[o.name]
            acc = np.zeros_like(co)
            for unit, w, mask in comps:
                d = unit_d[unit][o.name]
                if mask == "L":
                    d = d * smooth_lr(co[:, 0])[:, None]
                elif mask == "R":
                    d = d * (1 - smooth_lr(co[:, 0]))[:, None]
                elif mask == "lips_lower":
                    # lips region only, so lips close over an open jaw
                    lw = np.exp(-(((co[:, 0] - mo[0]) / 0.028) ** 2 + ((co[:, 2] - (mo[2] + 0.025)) / 0.022) ** 2))
                    lw *= (co[:, 1] < mo[1] + 0.03)
                    d = d * lw[:, None]
                    if o.name == "DH_Teeth" or o.name == "DH_Tongue":
                        d = d * 0
                acc += w * d
            if np.abs(acc).max() > 1e-6:
                per_ob[o.name] = acc
        shapes[sk] = per_ob

    # wrinkle-map drivers (consumed by both renderers)
    wrinkle_drivers = {
        "wrinkle_forehead": {"browInnerUp": 0.6, "browOuterUpLeft": 0.25, "browOuterUpRight": 0.25},
        "wrinkle_glabella": {"browDownLeft": 0.5, "browDownRight": 0.5},
        "wrinkle_crowsfeet": {"eyeSquintLeft": 0.35, "eyeSquintRight": 0.35, "cheekSquintLeft": 0.3,
                              "cheekSquintRight": 0.3, "mouthSmileLeft": 0.25, "mouthSmileRight": 0.25},
        "wrinkle_nasolabial": {"mouthSmileLeft": 0.4, "mouthSmileRight": 0.4, "noseSneerLeft": 0.4,
                               "noseSneerRight": 0.4},
    }

    # ---- body correctives (pose-space)
    correctives, corr_meta = body_correctives(rig, body, rests["DH_Body"])

    # ---- transfer body correctives to clothing through the proxy barycentric binding (body skin under
    #      clothes is removed in the realtime model, so the garments must carry the volume correction)
    cloth_corr = transfer_correctives_to_clothes(body, correctives)
    for ob, per in cloth_corr.items():
        if not ob.data.shape_keys:
            ob.shape_key_add(name="Basis", from_mix=False)
        base = rest_coords(ob)
        for k, d in per.items():
            kb = ob.shape_key_add(name=k, from_mix=False)
            kb.data.foreach_set("co", (base + d).ravel())
            kb.value = 0.0
        print(f"[shapes] {ob.name}: {len(per)} corrective keys")

    # ---- write shape keys
    for o in face_obs:
        if not o.data.shape_keys:
            o.shape_key_add(name="Basis", from_mix=False)
        base = rests[o.name]
        for sk, per_ob in list(shapes.items()) + [(k, {"DH_Body": v}) for k, v in correctives.items()]:
            if o.name not in per_ob:
                continue
            kb = o.shape_key_add(name=sk, from_mix=False)
            kb.data.foreach_set("co", (base + per_ob[o.name]).ravel())
            kb.slider_min = -1.0 if sk.startswith("mouthClose") else 0.0
            kb.value = 0.0          # Blender 5 creates new keys at 1.0
        print(f"[shapes] {o.name}: {len(o.data.shape_keys.key_blocks) - 1} keys")
    for (on, mn), v in saved.items():
        bpy.data.objects[on].modifiers[mn].show_viewport = v

    # ---- rig metadata for runtimes
    meta = {"arkit": [k for k in defs if k in shapes and shapes[k]],
            "wrinkle_drivers": wrinkle_drivers, "correctives": corr_meta,
            "bvh_convention": conv, "joint_limits": JOINT_LIMITS,
            "unit_max_disp_mm": mags}
    json.dump(meta, open(meta_out, "w"), indent=1)
    bpy.ops.wm.save_as_mainfile(filepath=blend_out)
    print("[saved]", blend_out)


def transfer_correctives_to_clothes(body, correctives):
    attr = body.data.attributes.get("mh_index")
    idx = np.zeros(len(body.data.vertices), np.int32)
    attr.data.foreach_get("value", idx)
    B = mh.base_mesh()
    nb = len(B.v)
    # base-mesh vertex -> body-mesh vertex: identity for skin, nearest skin vertex for helper shells
    # (MakeHuman garments are bound to the 'helper-tights' shell that sits just outside the skin)
    from scipy.spatial import cKDTree
    body_set = np.zeros(nb, bool); body_set[idx] = True
    tree = cKDTree(B.v[idx])
    _, nn = tree.query(B.v, k=1)
    base_to_body = nn.astype(np.int64)            # index into body-mesh vertex order
    inv = np.full(nb, -1, np.int64); inv[idx] = np.arange(len(idx))
    base_to_body[body_set] = inv[body_set]
    out = {}
    for ob in bpy.data.objects:
        folder, name = ob.get("mh_folder"), ob.get("mh_proxy")
        if not folder or "clothes" not in str(folder):
            continue
        px = mh.load_proxy(os.path.join(folder, name + ".mhclo"))
        if len(px.ref) != len(ob.data.vertices):
            print("[corrective transfer] vertex count mismatch", ob.name)
            continue
        per = {}
        for k, d in correctives.items():
            full = d[base_to_body]
            dc = (full[px.ref[:, 0]] * px.w[:, 0, None] + full[px.ref[:, 1]] * px.w[:, 1, None] + full[px.ref[:, 2]] * px.w[:, 2, None])
            if np.abs(dc).max() > 1e-5:
                per[k] = dc
        out[ob] = per
    return out


# Human active range of motion (degrees) per anatomical motion. Used by API validation + IK clamps.
JOINT_LIMITS = {
    "neck_flexion": [-50, 60], "neck_rotation": [-75, 75], "neck_lateral": [-40, 40],
    "spine_flexion": [-25, 75], "spine_rotation": [-35, 35], "spine_lateral": [-30, 30],
    "shoulder_flexion": [-50, 170], "shoulder_abduction": [-30, 170], "shoulder_rotation": [-70, 90],
    "elbow_flexion": [0, 145], "forearm_pronation": [-80, 85],
    "wrist_flexion": [-70, 80], "wrist_deviation": [-20, 35],
    "finger_mcp_flexion": [-20, 90], "finger_pip_flexion": [0, 105], "finger_dip_flexion": [0, 80],
    "thumb_cmc_flexion": [-15, 50],
    "hip_flexion": [-20, 120], "hip_abduction": [-30, 45], "hip_rotation": [-40, 45],
    "knee_flexion": [0, 140], "ankle_dorsiflexion": [-50, 20], "ankle_inversion": [-20, 35], "toe_flexion": [-40, 70],
    "jaw_open": [0, 30], "eye_yaw": [-45, 45], "eye_pitch": [-35, 30],
}


def _flex_axis(rig, bone, child_tip_bone, want_dir):
    """find local axis/sign whose positive rotation moves child tip along want_dir"""
    pb = rig.pose.bones[bone]
    best = None
    for ax in ("X", "Z"):
        for sgn in (1, -1):
            reset_pose(rig)
            pb.rotation_mode = "XYZ"
            setattr(pb.rotation_euler, ax.lower(), math.radians(40 * sgn))
            bpy.context.view_layer.update()
            tip = rig.pose.bones[child_tip_bone].tail
            rest_tip = rig.data.bones[child_tip_bone].tail_local
            mv = (tip - rest_tip).dot(Vector(want_dir))
            if best is None or mv > best[0]:
                best = (mv, ax, sgn)
    reset_pose(rig)
    return best[1], best[2]


def body_correctives(rig, body, rest):
    vg_names = {vg.index: vg.name for vg in body.vertex_groups}
    nv = len(body.data.vertices)
    W = {}
    for v in body.data.vertices:
        for g in v.groups:
            nm = vg_names[g.group]
            if nm in rig.data.bones:
                W.setdefault(nm, np.zeros(nv, np.float32))[v.index] = g.weight
    arm_mod = [m for m in body.modifiers if m.type == "ARMATURE"][0]
    specs = []
    for side in ("L", "R"):
        specs += [
            (f"corr_elbowFlex_{side}", f"lowerarm01.{side}", f"lowerarm02.{side}", (0, -1, 0.3), 135, "biceps", f"upperarm02.{side}"),
            (f"corr_kneeFlex_{side}", f"lowerleg01.{side}", f"lowerleg02.{side}", (0, 1, 0.2), 130, "calf", f"lowerleg01.{side}"),
            (f"corr_shoulderUp_{side}", f"upperarm01.{side}", f"upperarm02.{side}", (0, 0, 1), 85, None, None),
            (f"corr_shoulderFwd_{side}", f"upperarm01.{side}", f"upperarm02.{side}", (0, -1, 0.2), 90, None, None),
            (f"corr_hipFlex_{side}", f"upperleg01.{side}", f"upperleg02.{side}", (0, -1, 0.3), 100, None, None),
            (f"corr_wristFlex_{side}", f"wrist.{side}", f"finger3-1.{side}", (0, -1, 0), 70, None, None),
        ]
    out, meta = {}, {}
    for name, bone, tip, want, deg, bulge, bulge_bone in specs:
        ax, sgn = _flex_axis(rig, bone, tip, want)
        pb = rig.pose.bones[bone]
        reset_pose(rig)
        pb.rotation_mode = "XYZ"
        setattr(pb.rotation_euler, ax.lower(), math.radians(deg * sgn))
        bpy.context.view_layer.update()
        arm_mod.use_deform_preserve_volume = False
        lbs = eval_coords(body)
        arm_mod.use_deform_preserve_volume = True
        dqs = eval_coords(body)
        arm_mod.use_deform_preserve_volume = False
        dpos = dqs - lbs
        # inverse-skin into rest space with each vertex's dominant bone (robust where LBS collapses),
        # restricted to the joint region and clamped.
        names = list(W.keys())
        Wm = np.stack([W[n] for n in names], 1)
        dom = np.argmax(Wm, 1)
        rots = np.stack([np.array((rig.pose.bones[n].matrix @ rig.data.bones[n].matrix_local.inverted()).to_3x3(),
                                  np.float32) for n in names])
        drest = np.einsum("nji,nj->ni", rots[dom], dpos)          # R^T * d
        jt = np.array(rig.data.bones[bone].head_local)
        region = np.exp(-(np.linalg.norm(rest - jt, axis=1) / 0.12) ** 2)
        drest *= region[:, None]
        mag = np.linalg.norm(drest, axis=1, keepdims=True)
        drest = np.where(mag > 0.03, drest / np.maximum(mag, 1e-9) * 0.03, drest)
        # muscle bulge
        if bulge:
            b = rig.data.bones[bulge_bone]
            h, t = np.array(b.head_local), np.array(b.tail_local)
            axv = (t - h) / np.linalg.norm(t - h)
            rel = rest - h
            along = rel @ axv / np.linalg.norm(t - h)
            radial = rel - (rel @ axv)[:, None] * axv
            rn = np.linalg.norm(radial, axis=1) + 1e-9
            if bulge == "biceps":
                front = (-radial[:, 1] / rn)                    # anterior (-Y) surface
                amp = 0.006 * np.exp(-((along - 0.55) / 0.22) ** 2) * np.clip(front, 0, 1) ** 1.5
            else:
                back = (radial[:, 1] / rn)
                amp = 0.004 * np.exp(-((along - 0.3) / 0.2) ** 2) * np.clip(back, 0, 1) ** 1.5
            amp *= (rn < 0.09)
            drest += (radial / rn[:, None]) * amp[:, None]
        mx = float(np.linalg.norm(drest, axis=1).max())
        out[name] = drest
        meta[name] = {"bone": bone, "axis": ax, "sign": sgn, "full_deg": deg, "max_mm": round(mx * 1000, 2)}
        print(f"[corrective] {name}: axis {ax}{'+' if sgn > 0 else '-'} {deg}deg  max {mx*1000:.1f} mm")
    reset_pose(rig)
    bpy.context.view_layer.update()
    return out, meta


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    main(a[0], a[1], a[2])
