"""Tileable skin micro-detail (pores + dermal cross-hatch grooves), 2048^2.

The tile represents ~32 mm x 32 mm of skin. It is applied in both renderers with a
per-region strength mask (pore_mask channel of the macro 'skin_masks' texture), the same way
production digital humans layer a tiling micro normal over the unique macro maps.

Outputs (OUT_DIR):
  skin_micro_normal.png   tangent-space normal (OpenGL +Y)
  skin_micro_height.png   16-bit height (for Cycles displacement / bump)
  skin_micro_cavity.png   cavity (pores dark) used to modulate specular/roughness
"""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from noise3d import perlin2_periodic, worley2_periodic, smoothstep  # noqa: E402

TILE_MM = 32.0


def height_to_normal(h, px_mm, strength=1.0):
    # periodic central differences, h in mm
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) / (2 * px_mm)
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) / (2 * px_mm)
    n = np.stack([-dx * strength, dy * strength, np.ones_like(h)], -1)  # image row 0 = top -> +Y up flip
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n


def main(out, res=2048, seed=7):
    os.makedirs(out, exist_ok=True)
    yy, xx = np.mgrid[0:res, 0:res].astype(np.float32)
    u, v = xx / res, yy / res
    mm = TILE_MM / res

    # --- pores: ~0.55 mm spacing => 58 cells per tile
    P = 58
    F1, F2, ID = worley2_periodic(u * P, v * P, P, seed=seed, jitter=0.95)
    r_cell = 0.18 + 0.22 * ID                              # radius in cell units (0.1..0.22 mm)
    pores = np.exp(-(F1 / (r_cell * 0.55)) ** 2) * (0.6 + 0.4 * ID)   # depth weight
    # some cells have no visible pore
    pores *= (ID > 0.12)

    # --- secondary finer pores / follicles
    P2 = 97
    G1, _, GID = worley2_periodic(u * P2, v * P2, P2, seed=seed + 5)
    pores2 = np.exp(-(G1 / 0.12) ** 2) * 0.35 * (GID > 0.4)

    # --- dermal grooves: cell borders of an anisotropic Voronoi (1.6 mm plates)
    Pg = 20
    warp_u = u + 0.012 * perlin2_periodic(u * 6, v * 6, 6, seed + 11)
    warp_v = v + 0.012 * perlin2_periodic(u * 6 + 3.1, v * 6, 6, seed + 12)
    H1, H2, _ = worley2_periodic(warp_u * Pg, warp_v * Pg, Pg, seed=seed + 3, jitter=1.0)
    border = H2 - H1
    grooves = np.exp(-(border / 0.045) ** 2)
    Pg2 = 44
    K1, K2, _ = worley2_periodic(warp_u * Pg2, warp_v * Pg2, Pg2, seed=seed + 4, jitter=1.0)
    grooves2 = np.exp(-((K2 - K1) / 0.06) ** 2) * 0.45

    # --- micro relief noise
    n1 = sum(perlin2_periodic(u * f, v * f, f, seed + 20 + i) * (0.5 ** i) for i, f in enumerate((64, 128, 256)))

    h_mm = (-0.030 * pores - 0.012 * pores2 - 0.012 * grooves - 0.006 * grooves2 + 0.0035 * n1)
    h_mm = h_mm.astype(np.float32)
    n = height_to_normal(h_mm, mm, strength=1.0)
    nrm = ((n * 0.5 + 0.5) * 255 + 0.5).astype(np.uint8)
    Image.fromarray(nrm).save(os.path.join(out, "skin_micro_normal.png"))
    hn = (h_mm - h_mm.min()) / (h_mm.max() - h_mm.min())
    Image.fromarray((hn * 65535).astype(np.uint16)).save(os.path.join(out, "skin_micro_height.png"))
    cav = np.clip(1 - 1.6 * pores - 0.6 * pores2 - 0.35 * grooves, 0, 1)
    Image.fromarray((cav * 255).astype(np.uint8)).save(os.path.join(out, "skin_micro_cavity.png"))
    print("micro height range mm", float(h_mm.min()), float(h_mm.max()))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/home/user/work/tex")
