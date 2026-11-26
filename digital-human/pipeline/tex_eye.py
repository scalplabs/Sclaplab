"""Procedural eye textures for the anatomical eyeball's polar UV
(uv = 0.5 + 0.5*(angle_from_gaze/pi)*(cos phi, sin phi)).

The iris is authored for a NOMINAL pupil fraction (PUPIL0 of the iris radius); renderers warp
the radial coordinate to dilate/constrict the pupil physically (stroma compresses/stretches).

Outputs: eye_albedo.png (sRGB), eye_normal.png (tangent, iris fibre relief + scleral veins),
eye_meta.json (iris/pupil uv radii).
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from noise3d import perlin2_periodic, smoothstep  # noqa: E402

R_EYE, IRIS_D = 0.0120, 0.0117
LIM_ANG = math.asin(IRIS_D / 2 / R_EYE)
IRIS_UV = 0.5 * LIM_ANG / math.pi          # iris radius in uv units
PUPIL0 = 0.36                               # nominal pupil diameter fraction of iris (≈4.2 mm)


def s2l(c):
    c = np.asarray(c, np.float32) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def l2s(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def main(out, res=2048, seed=3, palette="brown"):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:res, 0:res].astype(np.float32)
    u, v = (xx + 0.5) / res, 1 - (yy + 0.5) / res
    du, dv = u - 0.5, v - 0.5
    r_uv = np.hypot(du, dv)
    phi = np.arctan2(dv, du)
    a = r_uv * 2 * np.pi                    # angle from gaze axis (rad)
    rho = np.clip(r_uv / IRIS_UV, 0, 2)     # 0 pupil centre .. 1 limbus (in iris)
    tphi = (phi / (2 * np.pi)) % 1.0

    # ------------------------------------------------------------- iris
    P = {"brown": dict(base=[86, 52, 30], light=[150, 98, 52], dark=[34, 20, 12], ring=[40, 26, 18]),
         "hazel": dict(base=[110, 82, 40], light=[160, 130, 70], dark=[50, 36, 18], ring=[50, 40, 28]),
         "blue": dict(base=[95, 120, 140], light=[170, 190, 200], dark=[40, 55, 70], ring=[40, 50, 60])}[palette]
    base, light, dark, ringc = (s2l(P[k]) for k in ("base", "light", "dark", "ring"))

    def pnoise(fa, fr, sd, oct_=3):
        o = 0
        amp = 1
        for i in range(oct_):
            o = o + amp * perlin2_periodic(tphi * fa * 2 ** i, rho * fr * 2 ** i + 13.7, int(fa * 2 ** i), sd + i)
            amp *= 0.5
        return o

    fib = pnoise(180, 3, seed + 1, 3)                      # radial stroma fibres
    fib2 = pnoise(420, 6, seed + 2, 2)
    coll_r = 0.48 + 0.035 * pnoise(14, 1, seed + 3, 2)     # collarette radius (wavy)
    pupillary = 1 - smoothstep(coll_r - 0.03, coll_r + 0.02, rho)
    collarette = np.exp(-((rho - coll_r) / 0.025) ** 2)
    crypts = smoothstep(0.25, 0.55, pnoise(40, 7, seed + 4, 2)) * np.exp(-((rho - coll_r - 0.08) / 0.12) ** 2)
    furrows = 0.5 + 0.5 * np.sin((rho - 0.6) * 2 * np.pi * 7 + 0.6 * pnoise(10, 1, seed + 5, 1))
    furrows = smoothstep(0.85, 1.0, furrows) * smoothstep(0.62, 0.7, rho) * (1 - smoothstep(0.9, 0.97, rho))
    limbal = smoothstep(0.80, 0.99, rho)
    ruff = np.exp(-((rho - PUPIL0) / 0.02) ** 2)

    t = 0.5 + 0.5 * fib
    col = base[None, None, :] * (0.65 + 0.7 * t[..., None])
    col = col * (1 - pupillary[..., None] * 0.5) + light[None, None, :] * (pupillary[..., None] * 0.5) * (0.7 + 0.6 * (0.5 + 0.5 * fib2[..., None]))
    col = col + light[None, None, :] * collarette[..., None] * 0.35
    col = col * (1 - 0.55 * crypts[..., None]) + dark[None, None, :] * 0.55 * crypts[..., None]
    col = col * (1 - 0.25 * furrows[..., None])
    col = col * (1 - limbal[..., None] * 0.85) + ringc[None, None, :] * limbal[..., None] * 0.85
    col = col * (1 - ruff[..., None] * 0.6) + dark[None, None, :] * ruff[..., None] * 0.6
    pupil = 1 - smoothstep(PUPIL0 - 0.01, PUPIL0 + 0.005, rho)
    col = col * (1 - pupil[..., None]) + np.array([0.004, 0.004, 0.005])[None, None, :] * pupil[..., None]
    iris_h = (0.5 + 0.5 * fib) * 0.6 + collarette * 0.8 - crypts * 0.8 - furrows * 0.3

    # ------------------------------------------------------------- sclera
    scl = s2l([226, 218, 208])[None, None, :] * np.ones((res, res, 1), np.float32)
    # exposed nasal/temporal sectors (horizontal) slightly yellow/pink; deeper = bluish-white
    horiz = np.abs(np.cos(phi)) ** 2
    scl = scl * (1 + (horiz * smoothstep(IRIS_UV, 0.35, r_uv))[..., None] * (s2l([255, 236, 225]) / s2l([255, 255, 255]) - 1)[None, None, :] * 0.6)
    scl *= (0.97 + 0.03 * perlin2_periodic(tphi * 16, r_uv * 20, 16, seed + 9))[..., None]
    # vessels: random walks from the equator toward the limbus, thinner as they approach
    vein = np.zeros((res, res), np.float32)
    img_r = res / 2
    for k in range(70):
        ang = rng.uniform(0, 2 * np.pi)
        # concentrate in visible horizontal sectors
        if rng.random() < 0.65:
            ang = rng.choice([0.0, np.pi]) + rng.normal(0, 0.45)
        rr = rng.uniform(0.33, 0.47)
        width = rng.uniform(1.2, 2.6) * res / 2048
        strength = rng.uniform(0.35, 1.0)
        heading = np.pi + ang  # inward
        x, y = 0.5 + rr * np.cos(ang), 0.5 + rr * np.sin(ang)
        steps = int(rng.uniform(60, 160))
        for s_ in range(steps):
            heading += rng.normal(0, 0.18)
            # bias toward the centre
            to_c = math.atan2(0.5 - y, 0.5 - x)
            heading += 0.08 * math.atan2(math.sin(to_c - heading), math.cos(to_c - heading))
            x += math.cos(heading) * 0.0016
            y += math.sin(heading) * 0.0016
            rnow = math.hypot(x - 0.5, y - 0.5)
            if rnow < IRIS_UV * 1.12:
                break
            w = width * (0.45 + 0.55 * (rnow - IRIS_UV) / (0.47 - IRIS_UV))
            cx, cy = int(x * res), int((1 - y) * res)
            r_px = int(w * 2 + 2)
            y0, y1, x0, x1 = max(cy - r_px, 0), min(cy + r_px + 1, res), max(cx - r_px, 0), min(cx + r_px + 1, res)
            gy, gx = np.mgrid[y0:y1, x0:x1]
            d = np.hypot(gx - cx, gy - cy)
            vein[y0:y1, x0:x1] = np.maximum(vein[y0:y1, x0:x1], strength * np.exp(-(d / w) ** 2))
            if rng.random() < 0.02:  # branch: start a thinner offshoot
                width *= 0.8
    vcol = s2l([170, 40, 40])
    scl = scl * (1 - vein[..., None] * 0.55) + vcol[None, None, :] * vein[..., None] * 0.55
    # limbus blend
    lim_mix = smoothstep(IRIS_UV * 0.985, IRIS_UV * 1.06, r_uv)
    outc = col * (1 - lim_mix[..., None]) + scl * lim_mix[..., None]
    # back of eye darker (never visible)
    outc *= (1 - 0.5 * smoothstep(0.38, 0.5, r_uv))[..., None]

    os.makedirs(out, exist_ok=True)
    Image.fromarray((l2s(outc) * 255 + 0.5).astype(np.uint8)).save(os.path.join(out, "eye_albedo.png"))
    # normal from height (iris relief inside iris, veins slightly raised)
    h = np.where(r_uv < IRIS_UV, iris_h * 1.0, vein * 0.4)
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5
    gy = -(np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5
    k = 6.0
    nn = np.stack([-gx * k, -gy * k, np.ones_like(h)], -1)
    nn /= np.linalg.norm(nn, axis=-1, keepdims=True)
    Image.fromarray(((nn * 0.5 + 0.5) * 255 + 0.5).astype(np.uint8)).save(os.path.join(out, "eye_normal.png"))
    json.dump({"iris_uv_radius": IRIS_UV, "pupil_fraction_nominal": PUPIL0, "palette": palette,
               "eye_radius_m": R_EYE, "iris_diameter_m": IRIS_D}, open(os.path.join(out, "eye_meta.json"), "w"), indent=1)
    print("iris uv radius", IRIS_UV)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/home/user/work/tex")
