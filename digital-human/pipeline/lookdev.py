"""Stage 2 — materials, grooming, eye/mouth detail meshes.

venv/bin/python pipeline/lookdev.py IN_stage1.blend TEX_DIR characters/X.json OUT.blend [--fast]

Creates (in the .blend):
  * DH_Skin material (Cycles random-walk SSS, macro normal + expression wrinkle normal blend + tiled
    micro bump, roughness/spec/cavity maps). Expression wrinkle weights are object custom properties
    on DH_Body (wrinkle_forehead / wrinkle_glabella / wrinkle_crowsfeet / wrinkle_nasolabial)
    driving the shader through attribute nodes.
  * Eyes: sclera/iris (procedural texture, pupil dilation via custom prop 'pupil'),
    cornea (IOR 1.376, shadow-transparent), tear meniscus strip, caruncle.
  * Teeth, tongue, oral cavity materials.
  * Strand hair (offline): scalp, brows, lashes, stubble, vellus, forearm hair  -> DH_Strands_* objects
  * Realtime hair cards (DH_HairCards) generated from the scalp guides + atlas texture.
  * Clothes/shoes PBR (diffuse/normal/AO from CC0 assets + fabric sheen).
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hair_strands as hs  # noqa: E402
import mhcore as mh  # noqa: E402

SUB_RADIUS = (1.0, 0.373, 0.185)   # skin mean free path ratios R:G:B (Christensen-Burley skin fit 3.67/1.37/0.68 mm)
SUB_SCALE = 0.0026                 # metres (red mfp ~2.6 mm; 3.6 mm read as waxy at portrait scale)


def img(path, colorspace="sRGB"):
    im = bpy.data.images.load(path, check_existing=True)
    im.colorspace_settings.name = colorspace
    return im


class NT:
    """tiny node-tree helper"""

    def __init__(self, mat):
        mat.use_nodes = True
        self.nt = mat.node_tree
        self.nt.nodes.clear()
        self.x = 0

    def n(self, kind, **props):
        nd = self.nt.nodes.new(kind)
        for k, v in props.items():
            if k.startswith("in_"):
                key = k[3:].replace("__", " ")
                nd.inputs[key].default_value = v
            else:
                setattr(nd, k, v)
        return nd

    def l(self, a, b):
        self.nt.links.new(a, b)


def tex_node(t, image, uv=None, interp="Linear"):
    nd = t.n("ShaderNodeTexImage")
    nd.image = image
    nd.interpolation = interp
    if uv is not None:
        t.l(uv, nd.inputs["Vector"])
    return nd


# ----------------------------------------------------------------------------- skin
def skin_material(tex):
    m = bpy.data.materials.new("DH_Skin")
    t = NT(m)
    out = t.n("ShaderNodeOutputMaterial")
    bsdf = t.n("ShaderNodeBsdfPrincipled")
    bsdf.subsurface_method = "RANDOM_WALK_SKIN" if "RANDOM_WALK_SKIN" in [
        e.identifier for e in bsdf.bl_rna.properties["subsurface_method"].enum_items] else "RANDOM_WALK"
    t.l(bsdf.outputs[0], out.inputs["Surface"])
    uvn = t.n("ShaderNodeUVMap", uv_map="UVMap")
    uv = uvn.outputs["UV"]
    alb = tex_node(t, img(os.path.join(tex, "skin_albedo.png")), uv)
    rs = tex_node(t, img(os.path.join(tex, "skin_rough_spec.png"), "Non-Color"), uv)
    rs.image.alpha_mode = "CHANNEL_PACKED"
    mk = tex_node(t, img(os.path.join(tex, "skin_masks.png"), "Non-Color"), uv)
    mk.image.alpha_mode = "CHANNEL_PACKED"
    nrm = tex_node(t, img(os.path.join(tex, "skin_normal.png"), "Non-Color"), uv)
    wnr = tex_node(t, img(os.path.join(tex, "skin_wrinkle_normal.png"), "Non-Color"), uv)
    wmk = tex_node(t, img(os.path.join(tex, "skin_wrinkle_mask.png"), "Non-Color"), uv)
    wmk.image.alpha_mode = "CHANNEL_PACKED"
    # micro detail (tiling 32 mm tile ~ x15 over the face UV density)
    mp = t.n("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (15.0, 15.0, 1.0)
    t.l(uv, mp.inputs["Vector"])
    mic_h = tex_node(t, img(os.path.join(tex, "skin_micro_height.png"), "Non-Color"), mp.outputs[0])
    mic_c = tex_node(t, img(os.path.join(tex, "skin_micro_cavity.png"), "Non-Color"), mp.outputs[0])

    # expression wrinkle weight = dot(mask, object props)
    sep = t.n("ShaderNodeSeparateColor")
    t.l(wmk.outputs["Color"], sep.inputs[0])
    acc = None
    for i, (sock, prop) in enumerate(((sep.outputs[0], "wrinkle_forehead"), (sep.outputs[1], "wrinkle_glabella"),
                                      (sep.outputs[2], "wrinkle_crowsfeet"), (wmk.outputs["Alpha"], "wrinkle_nasolabial"))):
        at = t.n("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name=prop)
        mul = t.n("ShaderNodeMath", operation="MULTIPLY")
        t.l(sock, mul.inputs[0])
        t.l(at.outputs["Fac"], mul.inputs[1])
        if acc is None:
            acc = mul
        else:
            add = t.n("ShaderNodeMath", operation="ADD", use_clamp=True)
            t.l(acc.outputs[0], add.inputs[0])
            t.l(mul.outputs[0], add.inputs[1])
            acc = add
    mixn = t.n("ShaderNodeMix", data_type="RGBA", blend_type="MIX")
    t.l(acc.outputs[0], mixn.inputs["Factor"])
    t.l(nrm.outputs["Color"], mixn.inputs[6])
    t.l(wnr.outputs["Color"], mixn.inputs[7])
    nmap = t.n("ShaderNodeNormalMap", uv_map="UVMap")
    nmap.inputs["Strength"].default_value = 1.0
    t.l(mixn.outputs[2], nmap.inputs["Color"])
    # micro bump scaled by pore mask
    msep = t.n("ShaderNodeSeparateColor")
    t.l(mk.outputs["Color"], msep.inputs[0])
    bmul = t.n("ShaderNodeMath", operation="MULTIPLY", in_Value=1.0)
    t.l(msep.outputs[0], bmul.inputs[0])
    bmul.inputs[1].default_value = 1.0
    bump = t.n("ShaderNodeBump")
    bump.inputs["Distance"].default_value = 0.00006
    t.l(bmul.outputs[0], bump.inputs["Strength"])
    t.l(mic_h.outputs["Color"], bump.inputs["Height"])
    t.l(nmap.outputs[0], bump.inputs["Normal"])
    t.l(bump.outputs[0], bsdf.inputs["Normal"])

    rsep = t.n("ShaderNodeSeparateColor")
    t.l(rs.outputs["Color"], rsep.inputs[0])
    # roughness: macro * (micro cavity raises roughness inside pores)
    rmix = t.n("ShaderNodeMapRange")
    t.l(mic_c.outputs["Color"], rmix.inputs["Value"])
    rmix.inputs["From Min"].default_value = 0.0
    rmix.inputs["From Max"].default_value = 1.0
    rmix.inputs["To Min"].default_value = 1.25
    rmix.inputs["To Max"].default_value = 0.97
    rough = t.n("ShaderNodeMath", operation="MULTIPLY", use_clamp=True)
    t.l(rsep.outputs[0], rough.inputs[0])
    t.l(rmix.outputs[0], rough.inputs[1])
    t.l(rough.outputs[0], bsdf.inputs["Roughness"])
    spec = t.n("ShaderNodeMath", operation="MULTIPLY")
    t.l(rsep.outputs[1], spec.inputs[0])
    t.l(mic_c.outputs["Color"], spec.inputs[1])
    t.l(spec.outputs[0], bsdf.inputs["Specular IOR Level"])
    t.l(alb.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Subsurface Weight"].default_value = 1.0
    bsdf.inputs["Subsurface Radius"].default_value = SUB_RADIUS
    # thickness/translucency map widens scattering in ears/nose/lids
    ssc = t.n("ShaderNodeMapRange")
    t.l(rs.outputs["Alpha"], ssc.inputs["Value"])
    ssc.inputs["To Min"].default_value = SUB_SCALE * 0.8
    ssc.inputs["To Max"].default_value = SUB_SCALE * 1.6
    t.l(ssc.outputs[0], bsdf.inputs["Subsurface Scale"])
    bsdf.inputs["IOR"].default_value = 1.4
    if "Subsurface IOR" in bsdf.inputs:
        bsdf.inputs["Subsurface IOR"].default_value = 1.4
    bsdf.inputs["Subsurface Anisotropy"].default_value = 0.8
    # a thin second specular lobe (sebum film) via Coat on oily areas
    coat_w = t.n("ShaderNodeMath", operation="MULTIPLY")
    t.l(mk.outputs["Alpha"], coat_w.inputs[0])
    coat_w.inputs[1].default_value = 0.35
    t.l(coat_w.outputs[0], bsdf.inputs["Coat Weight"])
    bsdf.inputs["Coat Roughness"].default_value = 0.32
    bsdf.inputs["Coat IOR"].default_value = 1.45
    m["dh_kind"] = "skin"
    return m


def simple_pbr(name, base=None, base_img=None, normal_img=None, ao_img=None, rough=0.5, sheen=0.0, sss=0.0,
               sss_radius=(1, 0.4, 0.2), sss_scale=0.002, coat=0.0, alpha_img=False, spec=0.5, metallic=0.0):
    m = bpy.data.materials.new(name)
    t = NT(m)
    out = t.n("ShaderNodeOutputMaterial")
    b = t.n("ShaderNodeBsdfPrincipled")
    t.l(b.outputs[0], out.inputs["Surface"])
    uv = t.n("ShaderNodeUVMap", uv_map="UVMap").outputs["UV"]
    if base_img:
        tb = tex_node(t, img(base_img), uv)
        if ao_img:
            ta = tex_node(t, img(ao_img, "Non-Color"), uv)
            mx = t.n("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
            mx.inputs["Factor"].default_value = 0.8
            t.l(tb.outputs["Color"], mx.inputs[6])
            t.l(ta.outputs["Color"], mx.inputs[7])
            t.l(mx.outputs[2], b.inputs["Base Color"])
        else:
            t.l(tb.outputs["Color"], b.inputs["Base Color"])
        if alpha_img:
            t.l(tb.outputs["Alpha"], b.inputs["Alpha"])
            m.blend_method = "HASHED" if hasattr(m, "blend_method") else None
    elif base is not None:
        b.inputs["Base Color"].default_value = (*base, 1)
    if normal_img:
        tn = tex_node(t, img(normal_img, "Non-Color"), uv)
        nm = t.n("ShaderNodeNormalMap", uv_map="UVMap")
        t.l(tn.outputs["Color"], nm.inputs["Color"])
        t.l(nm.outputs[0], b.inputs["Normal"])
    b.inputs["Roughness"].default_value = rough
    b.inputs["Sheen Weight"].default_value = sheen
    b.inputs["Specular IOR Level"].default_value = spec
    b.inputs["Metallic"].default_value = metallic
    if sss:
        b.inputs["Subsurface Weight"].default_value = sss
        b.inputs["Subsurface Radius"].default_value = sss_radius
        b.inputs["Subsurface Scale"].default_value = sss_scale
    if coat:
        b.inputs["Coat Weight"].default_value = coat
        b.inputs["Coat Roughness"].default_value = 0.05
    return m


def eye_material(tex):
    m = bpy.data.materials.new("DH_EyeSclera")
    t = NT(m)
    out = t.n("ShaderNodeOutputMaterial")
    b = t.n("ShaderNodeBsdfPrincipled")
    t.l(b.outputs[0], out.inputs["Surface"])
    meta = json.load(open(os.path.join(tex, "eye_meta.json")))
    # pupil dilation: warp radial uv inside the iris. pupil prop = actual pupil fraction of iris (0.2..0.8)
    uv = t.n("ShaderNodeUVMap", uv_map="UVMap")
    # uv -> centred vector
    sub = t.n("ShaderNodeVectorMath", operation="SUBTRACT")
    sub.inputs[1].default_value = (0.5, 0.5, 0)
    t.l(uv.outputs["UV"], sub.inputs[0])
    ln = t.n("ShaderNodeVectorMath", operation="LENGTH")
    t.l(sub.outputs[0], ln.inputs[0])
    rho = t.n("ShaderNodeMath", operation="DIVIDE")
    t.l(ln.outputs["Value"], rho.inputs[0])
    rho.inputs[1].default_value = meta["iris_uv_radius"]
    pup = t.n("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="pupil")
    # rho_tex = p0 + (rho - p)/(1 - p) * (1 - p0)   for rho in [p,1]; scaled back for rho < p
    p0 = meta["pupil_fraction_nominal"]
    a1 = t.n("ShaderNodeMath", operation="SUBTRACT")
    t.l(rho.outputs[0], a1.inputs[0])
    t.l(pup.outputs["Fac"], a1.inputs[1])
    a2 = t.n("ShaderNodeMath", operation="SUBTRACT")
    a2.inputs[0].default_value = 1.0
    t.l(pup.outputs["Fac"], a2.inputs[1])
    a3 = t.n("ShaderNodeMath", operation="DIVIDE")
    t.l(a1.outputs[0], a3.inputs[0])
    t.l(a2.outputs[0], a3.inputs[1])
    a4 = t.n("ShaderNodeMath", operation="MULTIPLY_ADD")
    t.l(a3.outputs[0], a4.inputs[0])
    a4.inputs[1].default_value = 1 - p0
    a4.inputs[2].default_value = p0
    # inside pupil: rho/p * p0
    b1 = t.n("ShaderNodeMath", operation="DIVIDE")
    t.l(rho.outputs[0], b1.inputs[0])
    t.l(pup.outputs["Fac"], b1.inputs[1])
    b2 = t.n("ShaderNodeMath", operation="MULTIPLY")
    t.l(b1.outputs[0], b2.inputs[0])
    b2.inputs[1].default_value = p0
    inpupil = t.n("ShaderNodeMath", operation="LESS_THAN")
    t.l(rho.outputs[0], inpupil.inputs[0])
    t.l(pup.outputs["Fac"], inpupil.inputs[1])
    sel = t.n("ShaderNodeMix", data_type="FLOAT")
    t.l(inpupil.outputs[0], sel.inputs["Factor"])
    t.l(a4.outputs[0], sel.inputs[2])
    t.l(b2.outputs[0], sel.inputs[3])
    # outside iris: identity
    iniris = t.n("ShaderNodeMath", operation="LESS_THAN")
    t.l(rho.outputs[0], iniris.inputs[0])
    iniris.inputs[1].default_value = 1.0
    sel2 = t.n("ShaderNodeMix", data_type="FLOAT")
    t.l(iniris.outputs[0], sel2.inputs["Factor"])
    t.l(rho.outputs[0], sel2.inputs[2])
    t.l(sel.outputs[0], sel2.inputs[3])
    # new uv = 0.5 + dir * rho' * iris_r
    nrm = t.n("ShaderNodeVectorMath", operation="NORMALIZE")
    t.l(sub.outputs[0], nrm.inputs[0])
    sc = t.n("ShaderNodeMath", operation="MULTIPLY")
    t.l(sel2.outputs[0], sc.inputs[0])
    sc.inputs[1].default_value = meta["iris_uv_radius"]
    sv = t.n("ShaderNodeVectorMath", operation="SCALE")
    t.l(nrm.outputs[0], sv.inputs[0])
    t.l(sc.outputs[0], sv.inputs["Scale"])
    add = t.n("ShaderNodeVectorMath", operation="ADD")
    t.l(sv.outputs[0], add.inputs[0])
    add.inputs[1].default_value = (0.5, 0.5, 0)
    ta = tex_node(t, img(os.path.join(tex, "eye_albedo.png")), add.outputs[0])
    tn = tex_node(t, img(os.path.join(tex, "eye_normal.png"), "Non-Color"), add.outputs[0])
    nm = t.n("ShaderNodeNormalMap", uv_map="UVMap")
    t.l(tn.outputs["Color"], nm.inputs["Color"])
    t.l(nm.outputs[0], b.inputs["Normal"])
    t.l(ta.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.35
    b.inputs["Subsurface Weight"].default_value = 0.4
    b.inputs["Subsurface Radius"].default_value = (1.0, 0.5, 0.4)
    b.inputs["Subsurface Scale"].default_value = 0.0015
    b.inputs["Specular IOR Level"].default_value = 0.3
    return m


def glass_shadow_transparent(name, ior, rough=0.0, tint=(1, 1, 1)):
    m = bpy.data.materials.new(name)
    t = NT(m)
    out = t.n("ShaderNodeOutputMaterial")
    g = t.n("ShaderNodeBsdfPrincipled")
    g.inputs["Base Color"].default_value = (*tint, 1)
    g.inputs["Transmission Weight"].default_value = 1.0
    g.inputs["IOR"].default_value = ior
    g.inputs["Roughness"].default_value = rough
    tr = t.n("ShaderNodeBsdfTransparent")
    lp = t.n("ShaderNodeLightPath")
    mx = t.n("ShaderNodeMixShader")
    t.l(lp.outputs["Is Shadow Ray"], mx.inputs[0])
    t.l(g.outputs[0], mx.inputs[1])
    t.l(tr.outputs[0], mx.inputs[2])
    t.l(mx.outputs[0], out.inputs["Surface"])
    return m


def hair_material(name, melanin=0.9, redness=0.25, rough=0.28, radial=0.3, coat=0.1, random_color=0.12,
                  random_rough=0.1, ior=1.55, dye=None):
    m = bpy.data.materials.new(name)
    t = NT(m)
    out = t.n("ShaderNodeOutputMaterial")
    try:
        h = t.n("ShaderNodeBsdfHairPrincipled")
        h.parametrization = "MELANIN"
        h.inputs["Melanin"].default_value = melanin
        h.inputs["Melanin Redness"].default_value = redness
        h.inputs["Roughness"].default_value = rough
        h.inputs["Radial Roughness"].default_value = radial
        h.inputs["Coat"].default_value = coat
        h.inputs["Random Color"].default_value = random_color
        h.inputs["Random Roughness"].default_value = random_rough
        h.inputs["IOR"].default_value = ior
        rnd = t.n("ShaderNodeHairInfo")
        t.l(rnd.outputs["Random"], h.inputs["Random"])
    except Exception as e:  # pragma: no cover
        print("hair bsdf fallback", e)
        h = t.n("ShaderNodeBsdfHair")
    t.l(h.outputs[0], out.inputs["Surface"])
    return m


# ----------------------------------------------------------------------------- tearline/caruncle
def make_tearline_and_caruncle(body, eye_objs, rig, mat_water, mat_car, mat_occl):
    import bmesh
    cent = {s: np.array(eye_objs[s].matrix_world.translation) for s in ("L", "R")}
    R = eye_objs["L"]["eye_radius"]
    loops = hs.eyelid_loops(body, cent)
    made = []
    for side, pts in loops.items():
        c = cent[side]
        # tear meniscus: strip from lid margin (slightly inside) onto the eyeball surface
        verts, faces = [], []
        n = len(pts)
        for i, p in enumerate(pts):
            d = p - c
            on_eye = c + d / np.linalg.norm(d) * (R + 0.00015)
            a = p + (on_eye - p) * 0.25
            b = on_eye + (on_eye - p) / (np.linalg.norm(on_eye - p) + 1e-9) * 0.0007
            verts += [tuple(a), tuple(b)]
        for i in range(n):
            j = (i + 1) % n
            faces.append((2 * i, 2 * j, 2 * j + 1, 2 * i + 1))
        me = bpy.data.meshes.new(f"tearline_{side}")
        me.from_pydata(verts, [], faces)
        for p in me.polygons:
            p.use_smooth = True
        ob = bpy.data.objects.new(f"DH_Tearline_{side}", me)
        bpy.context.scene.collection.objects.link(ob)
        ob.data.materials.append(mat_water)
        made.append(ob)
        # eye occlusion shell (realtime only): lid margin -> 3.5 mm onto eyeball, alpha gradient
        verts, faces, uvs = [], [], []
        for i, p in enumerate(pts):
            d = p - c
            on_eye = c + d / np.linalg.norm(d) * (R + 0.0003)
            inward = c + (d - np.array([0, -1, 0]) * 0) / np.linalg.norm(d) * (R + 0.0003)
            tgt = c + (on_eye - c) * 1.0
            dirv = (np.array([c[0], c[1] - R, c[2]]) - on_eye)
            dirv /= np.linalg.norm(dirv) + 1e-9
            q = on_eye + dirv * 0.0035
            q = c + (q - c) / np.linalg.norm(q - c) * (R + 0.0003)
            verts += [tuple(p + (on_eye - p) * 0.1), tuple(q)]
        for i in range(n):
            j = (i + 1) % n
            faces.append((2 * i, 2 * j, 2 * j + 1, 2 * i + 1))
        me = bpy.data.meshes.new(f"eyeocc_{side}")
        me.from_pydata(verts, [], faces)
        uvl = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            poly.use_smooth = True
            for li in poly.loop_indices:
                vi = me.loops[li].vertex_index
                uvl.data[li].uv = (0.5, 0.0 if vi % 2 == 0 else 1.0)
        oc = bpy.data.objects.new(f"DH_EyeOcclusion_{side}", me)
        bpy.context.scene.collection.objects.link(oc)
        oc.data.materials.append(mat_occl)
        oc.hide_render = True          # realtime only (Cycles computes real occlusion)
        oc["realtime_only"] = 1
        made.append(oc)
        # caruncle: small wet ellipsoid at the medial canthus
        medial = pts[np.argmin(np.abs(pts[:, 0]))]
        bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=1.0,
                                             location=tuple(medial + (c - medial) * 0.18 + np.array([0, 0.0006, 0])))
        car = bpy.context.active_object
        car.name = f"DH_Caruncle_{side}"
        car.scale = (0.0017, 0.0013, 0.0021)
        bpy.ops.object.transform_apply(scale=True)
        for p in car.data.polygons:
            p.use_smooth = True
        car.data.materials.append(mat_car)
        made.append(car)
    for ob in made:
        vg = ob.vertex_groups.new(name="head")
        vg.add(list(range(len(ob.data.vertices))), 1.0, "REPLACE")
        md = ob.modifiers.new("Armature", "ARMATURE")
        md.object = rig
        ob.parent = rig
    return made


def occlusion_material():
    m = bpy.data.materials.new("DH_EyeOcclusion")
    m["realtime_only"] = 1
    t = NT(m)
    out = t.n("ShaderNodeOutputMaterial")
    b = t.n("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (0.02, 0.015, 0.015, 1)
    b.inputs["Alpha"].default_value = 0.6
    t.l(b.outputs[0], out.inputs["Surface"])
    return m


# ----------------------------------------------------------------------------- main
def bind_to_head(ob, rig, bone="head"):
    vg = ob.vertex_groups.new(name=bone)
    vg.add(list(range(len(ob.data.vertices))), 1.0, "REPLACE")
    md = ob.modifiers.new("Armature", "ARMATURE")
    md.object = rig
    ob.parent = rig


def main(blend_in, tex, cfg_path, blend_out, fast=False):
    cfg = json.load(open(cfg_path))
    bpy.ops.wm.open_mainfile(filepath=blend_in)
    scn = bpy.context.scene
    rng = np.random.default_rng(cfg["look"].get("seed", 1))
    body = bpy.data.objects["DH_Body"]
    rig = bpy.data.objects["DH_Rig"]
    L = {b.name: b for b in rig.data.bones}
    eL, eR = np.array(L["eye.L"].head_local), np.array(L["eye.R"].head_local)
    O = (eL + eR) / 2
    s = np.linalg.norm(eL - eR) / 0.062

    # subdivision for render smoothness (viewport 1, render 2)
    sub = body.modifiers.new("Subdivision", "SUBSURF")
    sub.levels, sub.render_levels = 1, 2
    sub.uv_smooth = "PRESERVE_BOUNDARIES"
    mask = body.modifiers.new("ClothesMask", "MASK")
    mask.vertex_group = "DH_hidden_by_clothes"
    mask.invert_vertex_group = True
    # order: armature -> mask -> subsurf
    bpy.context.view_layer.objects.active = body
    while body.modifiers[0].name != "Armature":
        bpy.ops.object.modifier_move_up(modifier="Armature")
    bpy.ops.object.modifier_move_to_index(modifier="ClothesMask", index=1)
    for k in ("wrinkle_forehead", "wrinkle_glabella", "wrinkle_crowsfeet", "wrinkle_nasolabial"):
        body[k] = 0.0

    skin = skin_material(tex)
    body.data.materials.clear()
    body.data.materials.append(skin)

    # eyes
    em = eye_material(tex)
    cor = glass_shadow_transparent("DH_Cornea", 1.376, 0.0)
    eyes = {}
    for sd in ("L", "R"):
        e = bpy.data.objects[f"DH_Eye_{sd}"]
        e.data.materials.clear()
        e.data.materials.append(em)
        e["pupil"] = 0.36
        c = bpy.data.objects[f"DH_Eye_{sd}_Cornea"]
        c.data.materials.clear()
        c.data.materials.append(cor)
        eyes[sd] = e
        for o in (e, c):
            sub2 = o.modifiers.new("Subdivision", "SUBSURF")
            sub2.levels, sub2.render_levels = 0, 1
    water = glass_shadow_transparent("DH_TearFilm", 1.336, 0.02)
    car = simple_pbr("DH_Caruncle", base=(0.62, 0.30, 0.30), rough=0.15, sss=1.0, sss_radius=(1, 0.3, 0.2),
                     sss_scale=0.001, coat=1.0)
    make_tearline_and_caruncle(body, eyes, rig, water, car, occlusion_material())

    A = mh.MH_ASSETS
    # teeth / tongue
    teeth = bpy.data.objects.get("DH_Teeth")
    if teeth:
        teeth.data.materials.clear()
        teeth.data.materials.append(simple_pbr("DH_Teeth", base_img=os.path.join(A, "teeth/materials/teeth.png"),
                                               rough=0.18, sss=0.6, sss_radius=(1, 0.8, 0.6), sss_scale=0.0008,
                                               coat=0.6))
    tongue = bpy.data.objects.get("DH_Tongue")
    if tongue:
        tongue.data.materials.clear()
        tongue.data.materials.append(simple_pbr("DH_Tongue", base_img=os.path.join(A, "tongue/tongue01/tongue01_diffuse.png"),
                                                rough=0.32, sss=1.0, sss_radius=(1, 0.3, 0.2), sss_scale=0.002, coat=0.8))
    # brows / lashes cards (realtime; hidden in offline strand renders)
    for key, sub_ in (("DH_Eyebrows", "eyebrows/eyebrow010/eyebrow010.png"), ("DH_Eyelashes", "eyelashes/eyelashes02/eyelashes02.png")):
        ob = bpy.data.objects.get(key)
        if ob:
            ob.data.materials.clear()
            mat = simple_pbr(key + "_Card", base_img=os.path.join(A, sub_), rough=0.5, alpha_img=True)
            ob.data.materials.append(mat)
            ob["realtime_only"] = 1
            ob.hide_render = True
    hc = bpy.data.objects.get("DH_Hair_cards")
    if hc:
        bpy.data.objects.remove(hc, do_unlink=True)   # replaced by generated cards
    # clothes
    for ob in [o for o in scn.objects if o.get("mh_proxy") and o.get("mh_folder") and "cloth" not in o.name.lower()]:
        pm = json.loads(ob.get("mh_material", "{}"))
        f = ob["mh_folder"]
        if "clothes" not in f:
            continue
        name = ob["mh_proxy"]
        dif = os.path.join(f, pm.get("diffuseTexture", "")) if pm.get("diffuseTexture") else None
        nor = os.path.join(f, pm.get("normalmapTexture", "")) if pm.get("normalmapTexture") else None
        ao = os.path.join(f, pm.get("aomapTexture", "")) if pm.get("aomapTexture") else None
        shoe = "shoe" in name
        mat = simple_pbr("DH_" + name, base_img=dif, normal_img=nor, ao_img=ao, rough=0.55 if shoe else 0.82,
                         sheen=0.0 if shoe else 0.6)
        ob.data.materials.clear()
        ob.data.materials.append(mat)
        sb = ob.modifiers.new("Subdivision", "SUBSURF")
        sb.levels, sb.render_levels = 0, 1

    # -------------------------------------------------------------- grooming
    from PIL import Image
    masks = np.asarray(Image.open(os.path.join(tex, "skin_masks.png")).convert("RGBA"))
    hf = {"O": O.tolist(), "s": float(s)}
    hair_col = cfg["look"].get("hair_melanin", 0.92)
    mat_hair = hair_material("DH_HairStrands", melanin=hair_col, redness=0.22, rough=0.26, radial=0.32, coat=0.05)
    mat_brow = hair_material("DH_BrowStrands", melanin=0.9, redness=0.2, rough=0.35)
    mat_lash = hair_material("DH_LashStrands", melanin=0.97, redness=0.1, rough=0.3)
    mat_stub = hair_material("DH_StubbleStrands", melanin=0.85, redness=0.2, rough=0.35)
    mat_vel = hair_material("DH_VellusStrands", melanin=0.25, redness=0.3, rough=0.4, random_color=0.3)
    nG, nC = (500, 9000) if fast else (2600, 85000)
    C, rad, G, gp, gn = hs.groom_scalp(body, masks, hf, rng, n_guides=nG, n_children=nC)
    hair = hs.make_curves("DH_Strands_Scalp", C, rad, mat_hair, rig)
    print("[groom] scalp strands", len(C))
    brows = bpy.data.objects.get("DH_Eyebrows")
    if brows:
        S, r = hs.groom_brows(body, brows, rng, n=500 if fast else 1500, s=s)
        hs.make_curves("DH_Strands_Brows", S, r, mat_brow, rig)
        print("[groom] brow strands", len(S))
    # Lashes: the lid-following card mesh is used offline too (strand lashes rooted from the geometric lid ring
    # landed off the lid margin in eye macro renders; cards deform with blink/expression shapes).
    lc = bpy.data.objects.get("DH_Eyelashes")
    if lc:
        lc.hide_render = False
        if "realtime_only" in lc:
            del lc["realtime_only"]
        lm = lc.active_material
        b = [n for n in lm.node_tree.nodes if n.type == "BSDF_PRINCIPLED"][0]
        for l in list(lm.node_tree.links):
            if l.to_socket == b.inputs["Base Color"]:
                lm.node_tree.links.remove(l)
        b.inputs["Base Color"].default_value = (0.03, 0.02, 0.015, 1)
        b.inputs["Roughness"].default_value = 0.4
    beard_dir = lambda p, n: np.array([0, -0.2, -1.0])
    S, r = hs.groom_short(body, masks, 1, rng, 4000 if fast else 22000, (0.0004, 0.0012), s=s, flow=beard_dir,
                          radius=0.00004, lie=0.35)
    hs.make_curves("DH_Strands_Stubble", S, r, mat_stub, rig)
    print("[groom] stubble", len(S))
    face_reg = lambda cen: ((cen[:, 2] > O[2] - 0.14) & (cen[:, 1] < O[1] + 0.02)).astype(float)
    S, r = hs.groom_short(body, None, 0, rng, 3000 if fast else 20000, (0.001, 0.0025), s=s, radius=0.000012,
                          region=face_reg, lie=1.1, flow=lambda p, n: np.array([np.sign(p[0] - O[0]) * 0.5, 0, -1.0]))
    hs.make_curves("DH_Strands_Vellus", S, r, mat_vel, rig)
    arm_reg = lambda cen: (((np.abs(cen[:, 0]) > 0.25) & (cen[:, 2] > 0.85) & (cen[:, 2] < 1.25))).astype(float)
    S, r = hs.groom_short(body, None, 0, rng, 2000 if fast else 12000, (0.004, 0.010), s=s, radius=0.00002,
                          region=arm_reg, lie=1.2, flow=lambda p, n: np.array([np.sign(p[0]) * 1.0, 0, -0.4]))
    hs.make_curves("DH_Strands_Arms", S, r, mat_stub, rig)
    # realtime cards from guides
    atlas = hs.hair_card_atlas(os.path.join(tex, "hair_card_atlas.png"))
    # two card layers: a wide, short under-layer that hides the scalp + the full-length top layer
    cards = hs.cards_from_guides(G, gn, width=0.017 * s)
    under = hs.cards_from_guides(G[:, : max(3, G.shape[1] * 3 // 5)], gn, width=0.026 * s, name="DH_HairCardsUnder")
    for o in bpy.context.scene.objects:
        o.select_set(False)
    under.select_set(True)
    cards.select_set(True)
    bpy.context.view_layer.objects.active = cards
    bpy.ops.object.join()
    bind_to_head(cards, rig)
    cmat = simple_pbr("DH_HairCards", base_img=atlas, rough=0.35, alpha_img=True)
    cards.data.materials.append(cmat)
    cards.hide_render = True
    cards["realtime_only"] = 1
    for o in scn.objects:
        if o.name.startswith("DH_Strands_"):
            o["offline_only"] = 1
            o.parent = rig
            o.parent_type = "BONE"
            o.parent_bone = "head"
            o.matrix_parent_inverse = (rig.matrix_world @ rig.pose.bones["head"].matrix @
                                       __import__("mathutils").Matrix.Translation((0, rig.data.bones["head"].length, 0))).inverted()

    scn["dh_lookdev"] = 1
    bpy.ops.wm.save_as_mainfile(filepath=blend_out)
    print("[saved]", blend_out)


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    main(a[0], a[1], a[2], a[3], fast="--fast" in a)
