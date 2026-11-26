"""Offline (Cycles path-traced) renders of the look-dev scene.

venv/bin/python pipeline/render.py IN.blend OUT_DIR --shots face_front,face_34,... [--res 1024] [--spp 128]
       [--hdri NAME] [--hdri-rot DEG] [--expr json] [--pose json] [--light studio|window|overcast|night]

Shots are camera presets (see SHOTS). Expression / pose JSON allow rendering any rig state:
  --expr '{"jawOpen":0.3,"mouthSmileLeft":0.6}'   (shape keys if present)
  --pose '{"neck02":[0,10,0]}'                     (bone XYZ euler degrees)
"""
import argparse
import json
import math
import os
import sys

import bpy
from mathutils import Euler, Vector

HDRI_DIR = os.environ.get("DH_HDRI", "/home/user/work/hdri")

SHOTS = {
    # name: (target, distance, azimuth, elevation, lens, aspect(w/h), fstop or 0)
    "face_front": ((0, -0.03, 1.685), 0.58, 0, 1, 85, 0.8, 4.0),
    "face_34": ((0.0, -0.03, 1.685), 0.58, 32, 3, 85, 0.8, 4.0),
    "face_side": ((0.0, -0.0, 1.685), 0.60, 90, 1, 85, 0.8, 4.0),
    "face_back": ((0.0, 0.03, 1.70), 0.62, 180, 4, 85, 0.8, 0),
    "eye_macro": ((0.031, -0.015, 1.706), 0.17, 18, 2, 100, 1.5, 5.6),
    "mouth_macro": ((0.0, -0.035, 1.63), 0.22, 12, 2, 100, 1.5, 5.6),
    "skin_macro": ((0.045, -0.01, 1.655), 0.14, 40, 0, 100, 1.5, 8.0),
    "bust": ((0, -0.01, 1.55), 1.25, 20, 3, 70, 0.8, 4.0),
    "full_front": ((0, 0, 0.93), 4.3, 0, 3, 50, 0.5, 0),
    "full_34": ((0, 0, 0.93), 4.3, 35, 5, 50, 0.5, 0),
    "full_side": ((0, 0, 0.93), 4.3, 90, 3, 50, 0.5, 0),
    "full_back": ((0, 0, 0.93), 4.3, 180, 3, 50, 0.5, 0),
    "hand": ((0.0, 0, 0.0), 0.45, 0, 0, 85, 1.2, 0),
}


def look_at(ob, target):
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def setup_world(scn, hdri, rot_deg, strength):
    w = bpy.data.worlds.new("DH_World")
    scn.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(os.path.join(HDRI_DIR, hdri + ".exr"), check_existing=True)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (0, 0, math.radians(rot_deg))
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    nt.links.new(mp.outputs[0], env.inputs["Vector"])
    nt.links.new(env.outputs[0], bg.inputs[0])
    bg.inputs[1].default_value = strength
    # camera sees a soft neutral backdrop instead of the low-res 1k HDRI
    lp = nt.nodes.new("ShaderNodeLightPath")
    bg2 = nt.nodes.new("ShaderNodeBackground")
    bg2.inputs[0].default_value = (0.18, 0.185, 0.19, 1)
    bg2.inputs[1].default_value = 1.0
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    nt.links.new(bg.outputs[0], mix.inputs[1])
    nt.links.new(bg2.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])


def area(scn, name, loc, target, energy, size, color=(1, 1, 1), spread=180):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = energy
    ld.size = size
    ld.color = color
    ld.spread = math.radians(spread)
    ob = bpy.data.objects.new(name, ld)
    scn.collection.objects.link(ob)
    ob.location = loc
    look_at(ob, target)
    return ob


LIGHTS = {
    "studio": dict(hdri="brown_photostudio_02", rot=40, strength=0.35,
                   lights=[("Key", (-1.1, -1.5, 2.15), 70, 0.9, (1.0, 0.95, 0.9)),
                           ("Rim", (0.9, 1.4, 2.1), 60, 0.6, (0.92, 0.96, 1.0))]),
    "window": dict(hdri="hotel_room", rot=120, strength=0.9,
                   lights=[("Window", (-2.0, -0.8, 1.9), 650, 2.0, (0.95, 0.97, 1.0))]),
    "overcast": dict(hdri="kloofendal_48d_partly_cloudy_puresky", rot=0, strength=1.0, lights=[]),
    "park": dict(hdri="cloudy_vondelpark", rot=200, strength=1.0, lights=[]),
    "night": dict(hdri="monochrome_studio_02", rot=0, strength=0.08,
                  lights=[("Practical", (1.2, -0.9, 1.9), 120, 0.25, (1.0, 0.7, 0.45))]),
}


def apply_state(expr, pose):
    if expr:
        for ob in bpy.data.objects:
            if ob.type == "MESH" and ob.data.shape_keys:
                for k, v in expr.items():
                    kb = ob.data.shape_keys.key_blocks.get(k)
                    if kb:
                        kb.value = v
        body = bpy.data.objects.get("DH_Body")
        if body and "_wrinkles" in expr:
            for k, v in expr["_wrinkles"].items():
                body[k] = v
    if pose:
        rig = bpy.data.objects["DH_Rig"]
        for bn, e in pose.items():
            pb = rig.pose.bones[bn]
            pb.rotation_mode = "XYZ"
            pb.rotation_euler = Euler([math.radians(x) for x in e], "XYZ")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("blend")
    ap.add_argument("out")
    ap.add_argument("--shots", default="face_34")
    ap.add_argument("--res", type=int, default=1024)
    ap.add_argument("--spp", type=int, default=128)
    ap.add_argument("--light", default="studio")
    ap.add_argument("--expr", default="")
    ap.add_argument("--pose", default="")
    ap.add_argument("--tag", default="")
    ap.add_argument("--exposure", type=float, default=0.0)
    ap.add_argument("--realtime-proxies", action="store_true", help="render cards instead of strands")
    a = ap.parse_args(argv)
    bpy.ops.wm.open_mainfile(filepath=a.blend)
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.cycles.samples = a.spp
    scn.cycles.use_adaptive_sampling = True
    scn.cycles.adaptive_threshold = 0.02
    scn.cycles.use_denoising = True
    scn.cycles.max_bounces = 12
    scn.cycles.transparent_max_bounces = 32
    scn.cycles.transmission_bounces = 12
    scn.view_settings.view_transform = "AgX"
    try:
        scn.view_settings.look = "AgX - Base Contrast"
    except Exception:
        pass
    scn.view_settings.exposure = a.exposure
    for o in scn.objects:
        if o.get("realtime_only"):
            o.hide_render = not a.realtime_proxies
        if o.get("offline_only"):
            o.hide_render = a.realtime_proxies
        if o.name == "DH_PreviewGround":
            o.hide_render = True
    L = LIGHTS[a.light]
    setup_world(scn, L["hdri"], L["rot"], L["strength"])
    tgt_head = (0, -0.02, 1.68)
    for nm, loc, en, sz, col in L["lights"]:
        area(scn, nm, loc, tgt_head, en, sz, col)
    # floor (shadow catcher-ish neutral)
    me = bpy.data.meshes.new("floor")
    me.from_pydata([(-6, -6, 0), (6, -6, 0), (6, 6, 0), (-6, 6, 0)], [], [(0, 1, 2, 3)])
    fl = bpy.data.objects.new("DH_Floor", me)
    scn.collection.objects.link(fl)
    fm = bpy.data.materials.new("floor")
    fm.diffuse_color = (0.2, 0.2, 0.2, 1)
    fl.data.materials.append(fm)
    apply_state(json.loads(a.expr) if a.expr else None, json.loads(a.pose) if a.pose else None)

    cam_d = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cam_d)
    scn.collection.objects.link(cam)
    scn.camera = cam
    os.makedirs(a.out, exist_ok=True)
    for shot in a.shots.split(","):
        tgt, dist, az, el, lens, aspect, fstop = SHOTS[shot]
        if shot == "hand":
            hb = bpy.data.objects["DH_Rig"].data.bones["wrist.L"]
            tgt = tuple(hb.head_local + Vector((0, -0.0, -0.05)))
            az = 60
        ar, er = math.radians(az), math.radians(el)
        cam.location = Vector(tgt) + Vector((dist * math.sin(ar) * math.cos(er), -dist * math.cos(ar) * math.cos(er),
                                             dist * math.sin(er)))
        look_at(cam, tgt)
        cam_d.lens = lens
        cam_d.clip_start = 0.005
        cam_d.dof.use_dof = fstop > 0
        if fstop:
            cam_d.dof.focus_distance = dist
            cam_d.dof.aperture_fstop = fstop
        scn.render.resolution_y = a.res
        scn.render.resolution_x = int(a.res * aspect)
        scn.render.filepath = os.path.join(a.out, f"{shot}{a.tag}.png")
        bpy.ops.render.render(write_still=True)
        print("[render]", scn.render.filepath)


if __name__ == "__main__":
    main()
