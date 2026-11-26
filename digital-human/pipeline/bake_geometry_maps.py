"""Bake per-texel geometry maps of the body in UV space (rest pose):
   position (object space, metres), object-space normal, ambient occlusion.
These feed tex_skin.py which synthesises anatomically placed detail.

venv/bin/python pipeline/bake_geometry_maps.py IN.blend OUT_DIR RES
"""
import os
import sys

import bpy
import numpy as np

POS_SCALE, POS_OFF = 0.4, 0.5   # stored = pos*0.4+0.5


def main(blend, out, res):
    bpy.ops.wm.open_mainfile(filepath=blend)
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.cycles.samples = 1
    body = bpy.data.objects["DH_Body"]
    # bake on smooth (subdivided) surface for continuous positions
    sub = body.modifiers.new("BakeSub", "SUBSURF")
    sub.levels = 2
    sub.render_levels = 2
    sub.uv_smooth = "PRESERVE_BOUNDARIES"
    for m in body.modifiers:
        if m.type == "ARMATURE":
            m.show_render = False
        if m.type == "MASK":
            m.show_render = False
    for o in scn.objects:
        o.hide_render = o is not body and o.type == "MESH"
    os.makedirs(out, exist_ok=True)

    mat = bpy.data.materials.new("BakeMat")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    mul = nt.nodes.new("ShaderNodeVectorMath")
    mul.operation = "MULTIPLY_ADD"
    mul.inputs[1].default_value = (POS_SCALE,) * 3
    mul.inputs[2].default_value = (POS_OFF,) * 3
    em = nt.nodes.new("ShaderNodeEmission")
    outn = nt.nodes.new("ShaderNodeOutputMaterial")
    img_node = nt.nodes.new("ShaderNodeTexImage")
    body.data.materials.clear()
    body.data.materials.append(mat)
    nt.nodes.active = img_node

    def bake(name, kind, link_fn=None, fmt="OPEN_EXR"):
        img = bpy.data.images.new(name, res, res, alpha=False, float_buffer=True)
        img_node.image = img
        nt.nodes.active = img_node
        for l in list(nt.links):
            nt.links.remove(l)
        if link_fn:
            link_fn()
        scn.render.bake.margin = 24
        if kind == "EMIT":
            bpy.ops.object.bake(type="EMIT")
        elif kind == "NORMAL_OBJ":
            scn.render.bake.normal_space = "OBJECT"
            bpy.ops.object.bake(type="NORMAL")
        elif kind == "AO":
            scn.cycles.samples = 128
            bpy.ops.object.bake(type="AO")
            scn.cycles.samples = 1
        img.filepath_raw = os.path.join(out, name + ".exr")
        img.file_format = fmt
        img.save()
        px = np.array(img.pixels[:], dtype=np.float32).reshape(res, res, 4)
        np.save(os.path.join(out, name + ".npy"), px[..., :3].astype(np.float32))
        print("[baked]", name)

    bpy.context.view_layer.objects.active = body
    for o in scn.objects:
        o.select_set(o is body)

    def lp():
        nt.links.new(geo.outputs["Position"], mul.inputs[0])
        nt.links.new(mul.outputs[0], em.inputs["Color"])
        nt.links.new(em.outputs[0], outn.inputs["Surface"])

    bake("position", "EMIT", lp)

    # coverage mask: emission white
    def lc():
        em.inputs["Color"].default_value = (1, 1, 1, 1)
        nt.links.new(em.outputs[0], outn.inputs["Surface"])
    scn.render.bake.margin = 0
    img = bpy.data.images.new("coverage", res, res, alpha=False, float_buffer=False)
    img_node.image = img
    for l in list(nt.links):
        nt.links.remove(l)
    lc()
    scn.render.bake.margin = 0
    bpy.ops.object.bake(type="EMIT", margin=0)
    px = np.array(img.pixels[:], dtype=np.float32).reshape(res, res, 4)
    np.save(os.path.join(out, "coverage.npy"), (px[..., 0] > 0.5))
    print("[baked] coverage")

    bsdf = nt.nodes.new("ShaderNodeBsdfDiffuse")

    def ln():
        nt.links.new(bsdf.outputs[0], outn.inputs["Surface"])
    bake("normal_obj", "NORMAL_OBJ", ln)
    bake("ao", "AO", ln)


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    main(a[0], a[1], int(a[2]))
