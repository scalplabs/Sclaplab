"""Make the master .blend portable: copy every referenced image into OUT/textures and make paths relative.
venv/bin/python pipeline/package_source.py IN.blend OUT_DIR"""
import os
import shutil
import sys

import bpy

a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
src, out = a[0], os.path.abspath(a[1])
os.makedirs(os.path.join(out, "textures"), exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=src)
for im in bpy.data.images:
    if im.source != "FILE" or not im.filepath:
        continue
    p = bpy.path.abspath(im.filepath)
    if not os.path.exists(p):
        print("missing", p)
        continue
    dst = os.path.join(out, "textures", os.path.basename(p))
    if not os.path.exists(dst):
        shutil.copy2(p, dst)
    im.filepath = "//textures/" + os.path.basename(p)
for o in list(bpy.data.objects):
    if o.name in ("DH_PreviewGround",):
        bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, os.path.basename(src)), relative_remap=True, compress=True)
print("[packaged]", out, len(os.listdir(os.path.join(out, "textures"))), "textures")
