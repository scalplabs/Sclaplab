"""Dump rest-pose bone heads/tails + eye centres to JSON (object space, metres)."""
import json, sys
import bpy
a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
bpy.ops.wm.open_mainfile(filepath=a[0])
rig = bpy.data.objects["DH_Rig"]
out = {"bones": {b.name: {"head": list(b.head_local), "tail": list(b.tail_local), "parent": b.parent.name if b.parent else None}
                 for b in rig.data.bones}}
for s in ("L", "R"):
    e = bpy.data.objects[f"DH_Eye_{s}"]
    vs = [e.matrix_world @ v.co for v in e.data.vertices]
    c = e.matrix_world.translation
    out[f"eye_{s}"] = {"centre": list(c), "radius": max((v - c).length for v in vs)}
json.dump(out, open(a[1], "w"), indent=1)
print("ok", len(out["bones"]))
