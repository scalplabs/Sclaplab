"""Quick inspection renders (Cycles CPU, low samples).

venv/bin/python pipeline/preview.py IN.blend OUT_PREFIX [views] [res] [samples]
views: comma list of full_front, full_side, full_back, face_front, face_34, face_side, wire_face
"""
import math
import os
import sys

import bpy
from mathutils import Vector

VIEWS = {
    # name: (target, distance, azimuth deg, elevation deg, lens mm)
    "full_front": ((0, 0, 0.92), 4.2, 0, 4, 50),
    "full_side": ((0, 0, 0.92), 4.2, 90, 4, 50),
    "full_back": ((0, 0, 0.92), 4.2, 180, 4, 50),
    "full_34": ((0, 0, 0.92), 4.2, 35, 6, 50),
    "face_front": ((0, -0.02, 1.66), 0.62, 0, 2, 85),
    "face_34": ((0, -0.02, 1.66), 0.62, 35, 4, 85),
    "face_side": ((0, -0.02, 1.66), 0.62, 90, 2, 85),
    "eye_close": ((0.032, -0.07, 1.705), 0.16, 20, 3, 100),
    "mouth_close": ((0.0, -0.08, 1.60), 0.25, 15, 3, 100),
    "hand_close": ((0.0, 0, 0.9), 0.5, 0, 0, 85),
}


def look_at(cam, target):
    d = Vector(target) - cam.location
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def setup_lights(scn, mode="studio"):
    for o in [o for o in scn.objects if o.get("dh_preview")]:
        bpy.data.objects.remove(o, do_unlink=True)
    w = scn.world or bpy.data.worlds.new("World")
    scn.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.32, 0.33, 0.36, 1)
    bg.inputs[1].default_value = 0.35

    def area(name, loc, energy, size, color=(1, 1, 1)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = color
        lo = bpy.data.objects.new(name, ld)
        lo["dh_preview"] = 1
        scn.collection.objects.link(lo)
        lo.location = loc
        look_at(lo, (0, 0, 1.4))
        return lo

    area("Key", (-1.6, -2.2, 2.4), 520, 1.4, (1.0, 0.96, 0.9))
    area("Fill", (2.2, -1.6, 1.6), 140, 2.0, (0.9, 0.95, 1.0))
    area("Rim", (0.8, 2.4, 2.4), 380, 1.0)
    # ground
    if not bpy.data.objects.get("DH_PreviewGround"):
        me = bpy.data.meshes.new("g")
        me.from_pydata([(-5, -5, 0), (5, -5, 0), (5, 5, 0), (-5, 5, 0)], [], [(0, 1, 2, 3)])
        g = bpy.data.objects.new("DH_PreviewGround", me)
        g["dh_preview"] = 1
        scn.collection.objects.link(g)
        m = bpy.data.materials.new("ground")
        m.diffuse_color = (0.25, 0.25, 0.25, 1)
        g.data.materials.append(m)


def render(blend, prefix, views, res=640, samples=48, wire=False):
    bpy.ops.wm.open_mainfile(filepath=blend)
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.cycles.samples = samples
    scn.cycles.use_denoising = True
    try:
        scn.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
    scn.view_settings.view_transform = "AgX"
    scn.render.film_transparent = False
    setup_lights(scn)
    cam_d = bpy.data.cameras.new("PrevCam")
    cam = bpy.data.objects.new("PrevCam", cam_d)
    cam["dh_preview"] = 1
    scn.collection.objects.link(cam)
    scn.camera = cam
    outs = []
    for v in views:
        tgt, dist, az, el, lens = VIEWS[v]
        a, e = math.radians(az), math.radians(el)
        cam.location = Vector(tgt) + Vector((dist * math.sin(a) * math.cos(e), -dist * math.cos(a) * math.cos(e),
                                             dist * math.sin(e)))
        look_at(cam, tgt)
        cam_d.lens = lens
        cam_d.clip_start = 0.01
        full = v.startswith("full")
        scn.render.resolution_x = int(res * (0.6 if full else 1))
        scn.render.resolution_y = res
        scn.render.filepath = f"{prefix}_{v}.png"
        bpy.ops.render.render(write_still=True)
        outs.append(scn.render.filepath)
    return outs


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    views = a[2].split(",") if len(a) > 2 else ["full_front", "full_side", "face_front", "face_34"]
    res = int(a[3]) if len(a) > 3 else 640
    spp = int(a[4]) if len(a) > 4 else 48
    print(render(a[0], a[1], views, res, spp))
