"""Stage 4 — exports.

venv/bin/python pipeline/export_glb.py RIG.blend TEX_DIR OUT_ASSETS_DIR rig_meta.json

Writes:
  OUT/characters/minjun/minjun_lod0.glb   hero realtime model: body (hidden-under-clothes verts removed),
                                          eyes+cornea, tearlines, eye occlusion, caruncles, teeth, tongue,
                                          brow/lash cards, hair cards, clothes, shoes; 163-bone skeleton;
                                          skin weights (4 influences); all ARKit/FACS/corrective morphs
  OUT/characters/minjun/minjun_lod1.glb   ~45% triangles, no face morphs except speech/blink subset
  OUT/characters/minjun/minjun_lod2.glb   crowd LOD (~15%), body+clothes merged, no morphs
  OUT/characters/minjun/minjun.fbx        FBX of LOD0 for DCC / Unreal import
  OUT/characters/minjun/textures/*.jpg|png  web texture set (4K skin, 2K others)
  OUT/characters/minjun/rig_meta.json     morph list, wrinkle drivers, corrective drivers, joint limits,
                                          eye/iris metadata, material table
"""
import json
import os
import shutil
import sys

import bpy
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

REALTIME_EXCLUDE_PREFIX = ("DH_Strands_", "DH_PreviewGround")
SPEECH_SUBSET = {"jawOpen", "mouthClose", "mouthFunnel", "mouthPucker", "mouthSmileLeft", "mouthSmileRight",
                 "mouthStretchLeft", "mouthStretchRight", "mouthRollLower", "mouthRollUpper", "mouthPressLeft",
                 "mouthPressRight", "mouthLowerDownLeft", "mouthLowerDownRight", "mouthUpperUpLeft",
                 "mouthUpperUpRight", "eyeBlinkLeft", "eyeBlinkRight", "browInnerUp", "browDownLeft",
                 "browDownRight", "tongueOut", "tongueUp"}


def select_only(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    if objs:
        bpy.context.view_layer.objects.active = objs[0]


def delete_hidden_verts(body):
    vg = body.vertex_groups.get("DH_hidden_by_clothes")
    if not vg:
        return 0
    select_only([body])
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    body.vertex_groups.active_index = vg.index
    bpy.ops.object.vertex_group_select()
    n = body.data.total_vert_sel
    bpy.ops.mesh.delete(type="VERT")
    bpy.ops.object.mode_set(mode="OBJECT")
    return n


def limit_weights(objs, limit=4):
    for o in objs:
        select_only([o])
        bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
        try:
            bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=limit)
            bpy.ops.object.vertex_group_normalize_all(group_select_mode="BONE_DEFORM", lock_active=False)
        except Exception as e:
            print("weight limit failed", o.name, e)
        bpy.ops.object.mode_set(mode="OBJECT")


def export_glb(path, objs, rig, morphs=True):
    select_only(objs + [rig])
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=False,
                              export_skins=True, export_morph=morphs, export_morph_normal=False,
                              export_try_sparse_sk=True, export_animations=False, export_yup=True,
                              export_image_format="NONE", export_materials="EXPORT", export_extras=True,
                              export_all_influences=False)
    print("[glb]", path, round(os.path.getsize(path) / 1e6, 2), "MB")


def strip_materials_to_placeholders(objs):
    """keep material NAMES (runtime binds shaders by name) but drop node graphs the exporter can't map"""
    for o in objs:
        for slot in o.material_slots:
            m = slot.material
            if m and not m.name.endswith("_rt"):
                rt = bpy.data.materials.get(m.name + "_rt") or bpy.data.materials.new(m.name + "_rt")
                rt.diffuse_color = (0.8, 0.8, 0.8, 1)
                rt["source"] = m.name
                slot.material = rt


def textures(tex, out):
    os.makedirs(out, exist_ok=True)
    plan = [  # (src, dst, size, format)
        ("skin_albedo.png", "skin_albedo_4k.jpg", 4096, "JPEG"), ("skin_albedo.png", "skin_albedo_2k.jpg", 2048, "JPEG"),
        ("skin_normal.png", "skin_normal_4k.png", 4096, "PNG"), ("skin_normal.png", "skin_normal_2k.jpg", 2048, "JPEG"),
        ("skin_wrinkle_normal.png", "skin_wrinkle_normal_2k.jpg", 2048, "JPEG"),
        ("skin_wrinkle_mask.png", "skin_wrinkle_mask_1k.png", 1024, "PNG"),
        ("skin_rough_spec.png", "skin_rough_spec_2k.png", 2048, "PNG"),
        ("skin_masks.png", "skin_masks_2k.png", 2048, "PNG"),
        ("skin_micro_normal.png", "skin_micro_normal.jpg", 1024, "JPEG"),
        ("eye_albedo.png", "eye_albedo_2k.jpg", 2048, "JPEG"), ("eye_normal.png", "eye_normal_1k.jpg", 1024, "JPEG"),
        ("hair_card_atlas.png", "hair_card_atlas.png", 1024, "PNG"),
    ]
    for src, dst, size, fmt in plan:
        p = os.path.join(tex, src)
        if not os.path.exists(p):
            print("missing", p)
            continue
        im = Image.open(p)
        if im.size[0] != size:
            im = im.resize((size, size), Image.LANCZOS)
        if fmt == "JPEG":
            im.convert("RGB").save(os.path.join(out, dst), quality=92, subsampling=0)
        else:
            im.save(os.path.join(out, dst), optimize=True)
    A = "/home/user/work/ext/makehuman-py3-assets/base"
    extra = {"teeth.png": f"{A}/teeth/materials/teeth.png", "tongue.png": f"{A}/tongue/tongue01/tongue01_diffuse.png",
             "eyebrow.png": f"{A}/eyebrows/eyebrow010/eyebrow010.png", "eyelashes.png": f"{A}/eyelashes/eyelashes02/eyelashes02.png",
             "shirt_jeans_diffuse.jpg": f"{A}/clothes/male_casualsuit01/male_casualsuit01_diffuse.png",
             "shirt_jeans_normal.jpg": f"{A}/clothes/male_casualsuit01/male_casualsuit01_normal.png",
             "shirt_jeans_ao.jpg": f"{A}/clothes/male_casualsuit01/male_casualsuit01_ao.png",
             "shoes_diffuse.jpg": f"{A}/clothes/shoes06/shoes06_diffuse.png"}
    for dst, src in extra.items():
        im = Image.open(src)
        if max(im.size) > 2048:
            im = im.resize((2048, 2048), Image.LANCZOS)
        if dst.endswith(".jpg"):
            im.convert("RGB").save(os.path.join(out, dst), quality=90)
        else:
            im.save(os.path.join(out, dst), optimize=True)
    print("[textures] ->", out)


def main(blend, tex, out_assets, meta_path):
    out = os.path.join(out_assets, "characters", "minjun")
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=blend)
    scn = bpy.context.scene
    rig = bpy.data.objects["DH_Rig"]
    objs = [o for o in scn.objects if o.type == "MESH" and o.name.startswith("DH_")
            and not o.name.startswith(REALTIME_EXCLUDE_PREFIX)]
    for o in objs:
        for m in list(o.modifiers):
            if m.type != "ARMATURE":
                o.modifiers.remove(m)
    body = bpy.data.objects["DH_Body"]
    print("[body] removed hidden verts:", delete_hidden_verts(body))
    limit_weights(objs)
    strip_materials_to_placeholders(objs)
    for o in objs:
        o.hide_render = False
    stats = {o.name: {"verts": len(o.data.vertices), "tris": sum(len(p.vertices) - 2 for p in o.data.polygons),
                      "morphs": (len(o.data.shape_keys.key_blocks) - 1) if o.data.shape_keys else 0} for o in objs}
    export_glb(os.path.join(out, "minjun_lod0.glb"), objs, rig)
    # FBX (DCC / Unreal)
    select_only(objs + [rig])
    bpy.ops.export_scene.fbx(filepath=os.path.join(out, "minjun_lod0.fbx"), use_selection=True,
                             add_leaf_bones=False, bake_anim=False, mesh_smooth_type="FACE", use_mesh_modifiers=False)
    print("[fbx] written")

    # LOD1: decimate, keep speech subset morphs only (decimate cannot keep shape keys -> rebuild subset by
    # transferring: simpler approach = remove non-subset keys and use planar-less unsubdivide on clothes only)
    for o in objs:
        if o.data.shape_keys:
            for kb in list(o.data.shape_keys.key_blocks)[1:]:
                if kb.name not in SPEECH_SUBSET:
                    o.shape_key_remove(kb)
    lod1 = [o for o in objs if not o.name.startswith(("DH_EyeOcclusion", "DH_Caruncle", "DH_Tearline"))]
    for o in lod1:
        if not o.data.shape_keys:
            d = o.modifiers.new("Dec", "DECIMATE")
            d.ratio = 0.45
            select_only([o])
            bpy.ops.object.modifier_apply(modifier="Dec")
    export_glb(os.path.join(out, "minjun_lod1.glb"), lod1, rig)
    # LOD2: no morphs, everything decimated, merged
    for o in lod1:
        if o.data.shape_keys:
            select_only([o])
            bpy.ops.object.shape_key_remove(all=True)
        d = o.modifiers.new("Dec", "DECIMATE")
        d.ratio = 0.35 if o.name in ("DH_Body",) else 0.4
        select_only([o])
        bpy.ops.object.modifier_apply(modifier="Dec")
    lod2 = [o for o in lod1 if not o.name.startswith(("DH_Eyelashes", "DH_Eyebrows", "DH_Tongue", "DH_Teeth", "DH_Eye_"))]
    export_glb(os.path.join(out, "minjun_lod2.glb"), lod2, rig, morphs=False)

    textures(tex, os.path.join(out, "textures"))
    meta = json.load(open(meta_path))
    meta["mesh_stats_lod0"] = stats
    meta["eye"] = json.load(open(os.path.join(tex, "eye_meta.json")))
    meta["skin_tex"] = json.load(open(os.path.join(tex, "skin_tex_meta.json")))
    meta["materials"] = {
        "DH_Skin": "skin", "DH_EyeSclera": "eye", "DH_Cornea": "cornea", "DH_TearFilm": "tearfilm",
        "DH_EyeOcclusion": "eye_occlusion", "DH_Caruncle": "caruncle", "DH_Teeth": "teeth", "DH_Tongue": "tongue",
        "DH_Eyebrows_Card": "brow_card", "DH_Eyelashes_Card": "lash_card", "DH_HairCards": "hair_cards",
        "DH_male_casualsuit01": "cloth", "DH_shoes06": "shoes"}
    meta["character"] = json.loads(scn["dh_character"])
    meta["stature_cm"] = scn["dh_stature_cm"]
    json.dump(meta, open(os.path.join(out, "rig_meta.json"), "w"), indent=1, ensure_ascii=False)
    print("[meta] written")


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    main(*a[:4])
