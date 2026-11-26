"""Macro skin texture synthesis in UV space, driven by per-texel 3D position.

Inputs : baked maps (position32.npy, normal_obj32.npy, coverage.npy, ao.npy) at RES,
         landmarks.json (rest skeleton), MakeHuman CC0 albedo (low-frequency painted detail),
         MPFB CC0 region masks (lips, eyelids, ears, nails).
Outputs (OUT_DIR, PNG, row 0 = top / OpenGL UV):
  skin_albedo.png        base colour (sRGB)
  skin_normal.png        tangent-space normal: static folds, wrinkles, knuckles, palm creases
  skin_rough_spec.png    R = roughness, G = specular level, B = cavity, A = translucency
  skin_masks.png         R = pore strength, G = beard/stubble, B = scalp, A = oiliness
  skin_wrinkle_normal.png  tangent normal of EXPRESSION wrinkles (fully compressed state)
  skin_wrinkle_mask.png  R forehead (brow raise), G glabella (brow lower), B crow's feet / lower lid
                         (squint, smile), A nasolabial + bunny lines (smile, sneer)
  skin_height.png        16-bit macro height for offline displacement
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from noise3d import fbm3, worley3, smoothstep  # noqa: E402
import mhcore as mh  # noqa: E402

Image.MAX_IMAGE_PIXELS = None


def srgb2lin(c):
    c = np.asarray(c, np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin2srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def load_mask(path, res):
    im = Image.open(path).convert("L").resize((res, res), Image.BILINEAR)
    return np.flipud(np.asarray(im, np.float32) / 255.0)


def gauss(d, w):
    return np.exp(-(d / w) ** 2)


def seg_dist(px, py, ax, ay, bx, by):
    """distance from points to segment (2D) + param t"""
    vx, vy = bx - ax, by - ay
    t = np.clip(((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy + 1e-12), 0, 1)
    return np.hypot(px - (ax + t * vx), py - (ay + t * vy)), t


def polyline_dist(px, py, pts):
    d = np.full(px.shape, 1e9, np.float32)
    tt = np.zeros(px.shape, np.float32)
    L = 0.0
    seglen = [np.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1)]
    tot = sum(seglen)
    for i in range(len(pts) - 1):
        di, ti = seg_dist(px, py, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
        better = di < d
        d = np.where(better, di, d)
        tt = np.where(better, (L + ti * seglen[i]) / tot, tt)
        L += seglen[i]
    return d, tt


def main(maps_dir, landmarks, cfg_path, out_dir, res_out=None):
    cfg = json.load(open(cfg_path))
    look = cfg["look"]
    rng = np.random.default_rng(look.get("seed", 1))
    seed = int(look.get("seed", 1))
    P_full = np.load(os.path.join(maps_dir, "position32.npy"))
    P_full = (P_full - 0.5) / 0.4
    N_full = np.load(os.path.join(maps_dir, "normal_obj32.npy")) * 2 - 1
    C = np.load(os.path.join(maps_dir, "coverage.npy"))
    AO = np.load(os.path.join(maps_dir, "ao.npy"))[..., 0].astype(np.float32)
    R = C.shape[0]
    # dilate coverage slightly so bake margins get valid values too
    cov = np.asarray(Image.fromarray((C * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(9))) > 0
    idx = np.nonzero(cov.ravel())[0]
    P = P_full.reshape(-1, 3)[idx].astype(np.float32)
    Nn = N_full.reshape(-1, 3)[idx].astype(np.float32)
    Nn /= np.linalg.norm(Nn, axis=1, keepdims=True) + 1e-9
    n = len(idx)
    print(f"[tex] res {R} texels {n}")

    L = json.load(open(landmarks))
    B = L["bones"]
    eL, eR = np.array(B["eye.L"]["head"]), np.array(B["eye.R"]["head"])
    O = (eL + eR) / 2
    iod = np.linalg.norm(eL - eR)
    # head frame: hx lateral (+ = character left), hy up, hz forward
    hx, hy, hz = P[:, 0] - O[0], P[:, 2] - O[2], -(P[:, 1] - O[1])
    fwd = -Nn[:, 1]                                   # normal facing forward
    head = (P[:, 2] > B["neck02"]["head"][2] - 0.02).astype(np.float32)
    s = iod / 0.062                                   # scale relative to average adult

    # ---------------------------------------------------------------- region masks (UV)
    T = os.path.join(mh.EXT, "mpfb2/src/mpfb/data/textures")
    lips = load_mask(os.path.join(T, "mpfb_lips.jpg"), R).ravel()[idx]
    lids = load_mask(os.path.join(T, "mpfb_eyelids.jpg"), R).ravel()[idx]
    ears = load_mask(os.path.join(T, "mpfb_ears.jpg"), R).ravel()[idx]
    nails = np.maximum(load_mask(os.path.join(T, "mpfb_fingernails.jpg"), R),
                       load_mask(os.path.join(T, "mpfb_toenails.jpg"), R)).ravel()[idx]
    mouth_in = load_mask(os.path.join(T, "mpfb_inside-mouth.jpg"), R).ravel()[idx]

    # landmarks measured from geometry
    lipsel = lips > 0.5
    mc_x = np.percentile(np.abs(hx[lipsel]), 99.5)              # mouth corner half-width
    mouth_y = np.median(hy[lipsel])
    lip_top = np.percentile(hy[lipsel], 98)
    lip_bot = np.percentile(hy[lipsel], 2)
    mid = (np.abs(hx) < 0.004) & (head > 0) & (fwd > 0.3)
    nose_tip_z = hz[mid & (hy < -0.01) & (hy > mouth_y)].max()
    nt_sel = mid & (hy < -0.01) & (hy > mouth_y) & (hz > nose_tip_z - 0.0008)
    nose_tip_y = hy[nt_sel].mean()
    nose_base_y = nose_tip_y - 0.012 * s
    brow_y = 0.012 * s + 0.0
    print(f"[landmarks] iod {iod*1000:.1f}mm mouth half-width {mc_x*1000:.1f}mm mouth_y {mouth_y*1000:.1f} "
          f"nose tip y {nose_tip_y*1000:.1f} z {nose_tip_z*1000:.1f} lip top {lip_top*1000:.1f} bot {lip_bot*1000:.1f}")

    face_front = smoothstep(0.05, 0.35, fwd) * head
    theta = np.arctan2(hx, hz + 0.045 * s)                   # azimuth about a vertical axis through head centre
    ath = np.abs(theta)

    # scalp / hairline (natural male hairline with temporal recession)
    hl = np.interp(ath, [0, 0.35, 0.62, 1.05, 1.45, 1.75, 2.3, 3.15],
                   [0.072, 0.070, 0.060, 0.045, 0.030, 0.035, 0.0, -0.072]) * s
    hl += 0.004 * fbm3(P, 180, 3, seed=seed + 1)
    scalp = smoothstep(-0.003, 0.005, hy - hl) * head
    # sideburns
    sb = gauss(ath - 1.58, 0.06) * smoothstep(-0.030, -0.020, hy) * (1 - smoothstep(0.03, 0.04, hy)) * head
    scalp = np.maximum(scalp, sb * 0.6)

    # beard zone: front of ears, below cheek line, above neck crease; excludes lips margin
    cheek_line = np.interp(ath, [0, 0.25, 0.6, 1.0, 1.45], [nose_base_y - 0.002, nose_base_y - 0.004,
                                                            -0.036 * s, -0.030 * s, -0.020 * s])
    upper = 1 - smoothstep(-0.002, 0.006, hy - cheek_line)
    neck_line = np.interp(ath, [0, 0.8, 1.5], [-0.135 * s, -0.125 * s, -0.10 * s])
    lower = smoothstep(-0.004, 0.012, hy - neck_line)
    lipmargin = 1 - smoothstep(0.25, 0.6, lips) * 1.0
    lipmargin *= 1 - gauss(np.maximum(0, np.hypot(hx / max(mc_x, 1e-3), (hy - mouth_y) / 0.012) - 1.0), 0.08) * 0.7
    beard = upper * lower * (ath < 1.62) * head * lipmargin
    beard *= 0.75 + 0.25 * smoothstep(-0.3, 0.3, fbm3(P, 60, 3, seed=seed + 2))
    # cheeks thinner density
    beard *= 1 - 0.45 * gauss(hy - (-0.03 * s), 0.012) * smoothstep(0.35, 0.8, ath)
    beard = np.clip(beard, 0, 1)

    # ---------------------------------------------------------------- HEIGHT (mm): static + expression
    h_static = np.zeros(n, np.float32)
    h_expr = np.zeros(n, np.float32)
    wm = np.zeros((n, 4), np.float32)
    wav = 0.0012 * fbm3(P, 90, 2, seed=seed + 7)          # waviness for line shapes

    # forehead lines
    fh_region = face_front * smoothstep(brow_y + 0.012, brow_y + 0.02, hy) * \
        (1 - smoothstep(-0.012, -0.004, hy - hl)) * (1 - smoothstep(0.035, 0.05, np.abs(hx)))
    lines = 0.0
    for k, y0 in enumerate(np.arange(0.028, 0.068, 0.0085) * s):
        amp = 1.0 - 0.15 * k
        yk = y0 + 0.002 * np.sin(hx * 55 + k) + wav
        lines = lines + amp * gauss(hy - yk, 0.0009)
    h_static -= 0.02 * lines * fh_region
    h_expr -= 0.20 * lines * fh_region
    wm[:, 0] = np.maximum(wm[:, 0], fh_region)

    # glabella (frown lines) + transverse nasal line
    gl_region = face_front * gauss(hy - (brow_y + 0.004), 0.010)
    g_lines = gauss(np.abs(hx) - 0.0065 * s - wav * 0.5, 0.0007) * (1 - smoothstep(0.0, 0.006, np.abs(hy - brow_y - 0.003) - 0.009))
    h_static -= 0.02 * g_lines * gl_region
    h_expr -= 0.22 * g_lines * gl_region
    wm[:, 1] = np.maximum(wm[:, 1], gauss(hy - (brow_y + 0.004), 0.013) * gauss(hx, 0.016) * face_front)

    # crow's feet: rays from lateral canthus
    for side in (1, -1):
        cx, cy = side * (iod / 2 + 0.0155 * s), -0.001
        dx, dy = hx - cx, hy - cy
        rr = np.hypot(dx, dy)
        ang = np.arctan2(dy, dx * side)
        rays = 0.0
        for a0 in np.radians([-38, -22, -8, 6, 20, 34]):
            dang = np.angle(np.exp(1j * (ang - a0 - 0.08 * np.sin(rr * 400))))
            rays = rays + gauss(dang * rr, 0.0007)
        reg = smoothstep(0.003, 0.007, rr) * (1 - smoothstep(0.018, 0.026, rr)) * (dx * side > -0.001) * head
        h_static -= 0.008 * rays * reg
        h_expr -= 0.24 * rays * reg
        wm[:, 2] = np.maximum(wm[:, 2], reg * (dx * side > 0))
        # lower lid crease / tear trough
        ex = side * iod / 2
        de = np.hypot(hx - ex, (hy + 0.004) * 1.25)
        trough = gauss(de - 0.0165 * s, 0.0012) * (hy < -0.004) * smoothstep(0.0, 0.004, -(hy + 0.006))
        h_static -= 0.06 * trough * head
        h_expr -= 0.12 * trough * head
        wm[:, 2] = np.maximum(wm[:, 2], gauss(de - 0.016 * s, 0.006) * (hy < 0) * head)
        # upper lid crease (supratarsal fold) - Asian eyelid: low/partial crease
        uc = gauss(np.hypot(hx - ex, (hy - 0.002) * 1.5) - 0.0135 * s, 0.0006) * (hy > 0.003)
        h_static -= 0.05 * uc * head * (np.abs(hx - ex) < 0.012)

    # nasolabial fold: ala crease -> beyond mouth corner
    for side in (1, -1):
        pts = [(side * 0.0185 * s, nose_tip_y + 0.002), (side * 0.024 * s, nose_base_y - 0.004),
               (side * (mc_x + 0.006), mouth_y + 0.002), (side * (mc_x + 0.010), mouth_y - 0.014)]
        d, t = polyline_dist(hx, hy, pts)
        fold_side = (np.abs(hx) - (np.abs(pts[1][0]) + (np.abs(pts[2][0]) - np.abs(pts[1][0])) * t)) * 1.0
        prof = -gauss(d, 0.0016 * (1 + 0.6 * t)) + 0.35 * gauss(d - 0.004, 0.003) * (fold_side > 0)
        fade = (1 - smoothstep(0.75, 1.0, t)) * face_front
        h_static += 0.10 * prof * fade
        h_expr += 0.30 * prof * fade
        wm[:, 3] = np.maximum(wm[:, 3], gauss(d, 0.007) * fade)
    # bunny lines (nose sides)
    bun_reg = face_front * gauss(hy - (brow_y - 0.018 * s), 0.008) * gauss(np.abs(hx) - 0.009 * s, 0.006)
    bl = gauss(np.sin((hx * np.sign(hx) * 0.6 + hy) * 900), 0.25)
    h_expr -= 0.12 * bl * bun_reg
    wm[:, 3] = np.maximum(wm[:, 3], bun_reg)
    # lip vertical lines
    lipl = gauss(np.sin(hx * 2 * np.pi / 0.0011 + 6 * fbm3(P, 300, 1, seed=seed + 9)), 0.35)
    h_static -= 0.010 * lipl * smoothstep(0.4, 0.9, lips) * (1 - 0.6 * gauss(hx / max(mc_x, 1e-3), 0.25) * 0)
    # mentolabial sulcus + chin
    msl = gauss(hy - (lip_bot - 0.010 * s) - 0.004 * (hx / max(mc_x, 1e-3)) ** 2, 0.0025) * gauss(hx, 0.018)
    h_static -= 0.05 * msl * face_front
    # philtrum
    ph = (gauss(np.abs(hx) - 0.0045 * s, 0.0012) * 0.6 - gauss(hx, 0.0018) * 0.4) * \
        smoothstep(lip_top, lip_top + 0.002, hy) * (1 - smoothstep(nose_base_y - 0.003, nose_base_y, hy))
    h_static += 0.12 * ph * face_front
    # neck lines
    neck = (P[:, 2] < O[2] - 0.12 * s) & (P[:, 2] > O[2] - 0.24 * s)
    nl = 0.0
    for k, yy in enumerate((-0.165, -0.19, -0.215)):
        nl = nl + gauss(hy - yy * s - 0.003 * np.sin(theta * 3 + k) - wav, 0.0012)
    h_static -= 0.05 * nl * neck * smoothstep(-0.2, 0.4, fwd) * (ath < 1.9)

    # hands: knuckle wrinkle rings and flexion creases
    knuck = np.zeros(n, np.float32)
    for side in ("L", "R"):
        for f in range(1, 6):
            for seg in (1, 2, 3):
                bn = f"finger{f}-{seg}.{side}"
                if bn not in B:
                    continue
                hb, tb = np.array(B[bn]["head"]), np.array(B[bn]["tail"])
                ax = tb - hb
                ln = np.linalg.norm(ax)
                ax /= ln
                rel = P - hb
                along = rel @ ax
                radial = np.linalg.norm(rel - along[:, None] * ax, axis=1)
                ring = (radial < 0.016) * gauss(along, 0.0045 if seg > 1 else 0.006)
                lines_k = gauss(np.sin(along * 2 * np.pi / 0.0011), 0.45)
                knuck += ring * (0.6 * lines_k + 0.6 * gauss(along, 0.0007))
    h_static -= 0.06 * np.clip(knuck, 0, 1.5)
    # palms: three major creases in wrist-local frame
    for side in ("L", "R"):
        w = np.array(B[f"wrist.{side}"]["head"])
        m2 = np.array(B[f"finger2-1.{side}"]["head"])
        m5 = np.array(B[f"finger5-1.{side}"]["head"])
        ax = (m2 + m5) / 2 - w
        ln = np.linalg.norm(ax)
        ax /= ln
        lat = m2 - m5
        lat -= (lat @ ax) * ax
        lat /= np.linalg.norm(lat)
        palm_n = np.cross(ax, lat)
        rel = P - w
        a_, l_ = rel @ ax / ln, rel @ lat / ln
        inpalm = (a_ > 0.05) & (a_ < 1.05) & (np.abs(l_) < 0.75) & (np.linalg.norm(rel, axis=1) < ln * 1.3)
        facing = np.abs(Nn @ palm_n)
        palm = inpalm * smoothstep(0.4, 0.8, facing)
        cre = (gauss(a_ - (0.80 - 0.10 * l_), 0.012) * (l_ < 0.45) +        # distal transverse
               gauss(a_ - (0.62 + 0.18 * l_), 0.012) * (l_ > -0.5) +        # proximal transverse
               gauss(np.hypot(a_ - 0.15, l_ - 0.55) - 0.55, 0.014) * (a_ < 0.7))  # thenar
        h_static -= 0.05 * np.clip(cre, 0, 1) * palm

    # elbow/knee folds, navel left to geometry
    # low-frequency subcutaneous bumpiness
    h_static += 0.025 * fbm3(P, 40, 3, seed=seed + 13)

    # ---------------------------------------------------------------- ALBEDO (linear)
    base = srgb2lin(np.array([206, 158, 128]) / 255.0)
    mhalb = Image.open(os.path.join(mh.MH_ASSETS, look["skin_base"])).convert("RGB").resize((R, R), Image.BICUBIC)
    mhb = np.flipud(srgb2lin(np.asarray(mhalb, np.float32) / 255.0)).reshape(-1, 3)[idx]
    mh_low = np.flipud(srgb2lin(np.asarray(mhalb.filter(ImageFilter.GaussianBlur(R / 160)), np.float32) / 255.0)).reshape(-1, 3)[idx]
    detail = np.clip(mhb / (mh_low + 1e-4), 0.6, 1.5) ** 0.8
    col = np.tile(base, (n, 1)) * detail

    def tint(mask, rgb, k=1.0):
        nonlocal col
        rgb = np.asarray(rgb, np.float32)
        col = col * (1 - mask[:, None] * k) + col * rgb[None, :] * (mask[:, None] * k)

    mel = look.get("melanin", 0.3)
    hem = look.get("hemoglobin", 0.5)
    # melanin mottling (multi-scale) and hemoglobin blotches
    m1 = fbm3(P, 22, 4, seed=seed + 20)
    m2 = fbm3(P, 120, 3, seed=seed + 21)
    col *= (1 + 0.06 * m1 + 0.025 * m2)[:, None] ** np.array([1.3, 1.0, 0.8])
    hb = smoothstep(-0.1, 0.5, fbm3(P, 35, 3, seed=seed + 22))
    tint(hb * 0.25 * hem, [1.05, 0.86, 0.84])
    # face vascular map: cheeks, nose, ears, chin, forehead centre
    cheeks = sum(gauss(np.hypot(hx - sd * 0.036 * s, (hy + 0.028 * s) * 1.2), 0.020) for sd in (1, -1)) * face_front
    nose_red = gauss(np.hypot(hx * 1.3, hy - nose_tip_y), 0.012) * face_front
    tint(np.clip(cheeks * 0.45 * hem + nose_red * 0.5 * hem, 0, 1), [1.06, 0.80, 0.80])
    tint(ears * 0.45, [1.04, 0.80, 0.80])
    tint(np.clip(lids, 0, 1) * 0.35, [0.93, 0.80, 0.84])
    # under-eye darkness (thin skin, venous)
    for sd in (1, -1):
        ue = gauss(np.hypot(hx - sd * iod / 2, (hy + 0.016 * s) * 1.6), 0.010) * face_front
        tint(ue * 0.35, [0.90, 0.84, 0.88])
    # forehead slightly sallow/yellow, jaw lighter
    tint(face_front * smoothstep(0.02, 0.05, hy) * (1 - scalp) * 0.25, [1.02, 1.0, 0.92])
    # lips colour
    lipcol = srgb2lin(np.array([184, 124, 116]) / 255.0) / base
    lip_k = smoothstep(0.3, 0.95, lips) * (0.8 + 0.2 * fbm3(P, 400, 2, seed=seed + 23))
    # darker oral commissure / lip contact line
    tint(gauss(hy - mouth_y + 0.0005 * np.sin(hx * 200), 0.0009) * gauss(hx / max(mc_x, 1e-3), 0.9) * face_front * 0.5, [0.7, 0.55, 0.55])
    tint(lip_k, lipcol)
    tint(mouth_in, srgb2lin(np.array([150, 70, 72]) / 255.0) / base)
    # beard shadow (stubble under the skin + follicle openings)
    bs = look.get("beard_shadow", 0.5)
    tint(beard * bs * 0.55, [0.80, 0.83, 0.90])
    F1, _, fid = worley3(P, 0.00065, seed=seed + 30)
    follicle = gauss(F1, 0.00012) * (fid > 0.15)
    tint(np.clip(beard * follicle * 1.4 * bs, 0, 1), [0.25, 0.24, 0.26])
    # scalp: hair roots / dark follicles
    F1s, _, sid = worley3(P, 0.0005, seed=seed + 31)
    tint(scalp * 0.35, [0.70, 0.68, 0.70])
    tint(np.clip(scalp * gauss(F1s, 0.00016) * 1.6, 0, 1), [0.15, 0.14, 0.14])
    # body: knuckles, elbows, knees darker/redder; palms lighter; nails
    tint(np.clip(knuck, 0, 1) * 0.5, [0.92, 0.80, 0.78])
    for jn, wdt in (("lowerarm01.L", 0.03), ("lowerarm01.R", 0.03), ("lowerleg01.L", 0.04), ("lowerleg01.R", 0.04)):
        jp = np.array(B[jn]["head"])
        tint(gauss(np.linalg.norm(P - jp, axis=1), wdt) * 0.35, [0.93, 0.82, 0.80])
    tint(nails, srgb2lin(np.array([214, 160, 150]) / 255.0) / base)
    # moles and freckles
    for k in range(70):
        # random surface sample
        j = rng.integers(0, n)
        c0 = P[j]
        dd = np.linalg.norm(P - c0, axis=1)
        r0 = rng.uniform(0.0004, 0.0016)
        tint(gauss(dd, r0) * rng.uniform(0.25, 0.7), [0.55, 0.42, 0.38])
    fr = look.get("freckle_density", 0.1)
    Ff, _, ffid = worley3(P, 0.004, seed=seed + 33)
    frk = gauss(Ff, 0.0006) * (ffid < fr) * (face_front + 0.3 * (P[:, 2] > 1.2)) * (1 - scalp)
    tint(np.clip(frk, 0, 1) * 0.3, [0.85, 0.74, 0.66])
    # capillaries (nose wings, cheeks): ridged noise
    rid = 1 - np.abs(fbm3(P, 700, 2, seed=seed + 40))
    cap = smoothstep(0.92, 0.985, rid) * np.clip(nose_red * 1.5 + cheeks * 0.4, 0, 1)
    tint(cap * 0.35, [1.0, 0.62, 0.62])
    # global melanin level
    col *= (1 - 0.35 * (mel - 0.3))
    # cavity darkening from AO (very subtle, physically the GI does the rest)
    ao = AO.ravel()[idx]
    col *= (0.85 + 0.15 * ao)[:, None]

    # ---------------------------------------------------------------- ROUGHNESS / SPEC / TRANSLUCENCY
    tzone = face_front * (gauss(hx, 0.012) * smoothstep(nose_tip_y - 0.01, brow_y + 0.03, hy) +
                          gauss(hy - (brow_y + 0.04), 0.02) * gauss(hx, 0.04))
    oily = np.clip(tzone * 1.1 + nose_red * 0.8 + gauss(hy - (lip_bot - 0.025), 0.01) * gauss(hx, 0.012) * 0.5, 0, 1)
    rough = 0.52 - 0.16 * oily
    rough = rough - 0.18 * smoothstep(0.3, 0.8, lips) + 0.06 * scalp + 0.05 * beard
    palms = 0.0
    rough += 0.02 * fbm3(P, 150, 2, seed=seed + 50)
    rough = np.clip(rough - 0.12 * nails, 0.18, 0.8)
    spec = np.clip(0.5 + 0.12 * oily - 0.15 * beard - 0.2 * scalp, 0, 1)
    cav = np.clip(1 + h_static / 0.12, 0, 1) * (0.6 + 0.4 * ao)
    thick_in = np.clip(ears * 0.9 + gauss(np.hypot(np.abs(hx) - 0.016 * s, hy - nose_tip_y + 0.004), 0.006) * 0.6 * face_front
                       + lids * 0.5 + 0.15, 0, 1)
    # fingers: thin
    thick_in = np.maximum(thick_in, 0.5 * np.clip(knuck, 0, 1))
    pore = np.clip(0.35 + 0.65 * face_front * (0.5 + 0.5 * np.clip(nose_red * 2 + cheeks * 0.6 + tzone, 0, 1)), 0, 1)
    pore *= (1 - smoothstep(0.3, 0.7, lips)) * (1 - 0.6 * scalp) * (1 - nails)

    # ---------------------------------------------------------------- write
    def full(vals, ch, fill=0.0):
        arr = np.full((R * R, ch), fill, np.float32)
        arr[idx] = vals.reshape(n, ch)
        return arr.reshape(R, R, ch)

    def save(arr, name, mode="RGB", bits=8):
        arr = np.flipud(arr)
        if res_out and res_out != R:
            pass
        if bits == 16:
            Image.fromarray((np.clip(arr[..., 0], 0, 1) * 65535).astype(np.uint16)).save(os.path.join(out_dir, name))
        else:
            a8 = (np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8)
            im = Image.fromarray(a8.squeeze() if a8.shape[-1] == 1 else a8, mode)
            if res_out and res_out != R:
                im = im.resize((res_out, res_out), Image.LANCZOS)
            im.save(os.path.join(out_dir, name), optimize=False)
        print("[write]", name)

    os.makedirs(out_dir, exist_ok=True)
    fill_rgb = col.mean(0)
    alb = full(lin2srgb(col), 3)
    alb[~cov] = lin2srgb(fill_rgb)
    save(alb, "skin_albedo.png")

    # height -> tangent normal (UV-space gradients scaled by texel world size)
    def to_normal(hmm, strength=1.0):
        H = full(hmm, 1)[..., 0] / 1000.0          # metres
        Pf = P_full.astype(np.float32)
        du = np.linalg.norm(np.roll(Pf, -1, 1) - np.roll(Pf, 1, 1), axis=-1) / 2
        dv = np.linalg.norm(np.roll(Pf, -1, 0) - np.roll(Pf, 1, 0), axis=-1) / 2
        du = np.where(du > 1e-7, du, 1e-3)
        dv = np.where(dv > 1e-7, dv, 1e-3)
        gx = (np.roll(H, -1, 1) - np.roll(H, 1, 1)) / 2 / du
        gy = (np.roll(H, -1, 0) - np.roll(H, 1, 0)) / 2 / dv
        gx = np.clip(gx, -2, 2) * cov
        gy = np.clip(gy, -2, 2) * cov
        nn = np.stack([-gx * strength, -gy * strength, np.ones_like(gx)], -1)
        nn /= np.linalg.norm(nn, axis=-1, keepdims=True)
        return nn * 0.5 + 0.5

    save(to_normal(h_static * 3.0), "skin_normal.png")
    save(to_normal(h_expr * 3.5), "skin_wrinkle_normal.png")
    save(full(np.stack([rough, spec, cav, thick_in], 1), 4, 0.5), "skin_rough_spec.png", "RGBA")
    save(full(np.stack([pore, beard, scalp, oily], 1), 4, 0.0), "skin_masks.png", "RGBA")
    wm = np.clip(wm, 0, 1)
    save(full(wm, 4, 0.0), "skin_wrinkle_mask.png", "RGBA")
    hmin, hmax = h_static.min(), h_static.max()
    save(full((h_static - hmin) / (hmax - hmin), 1, (0 - hmin) / (hmax - hmin)), "skin_height.png", bits=16)
    json.dump({"height_min_mm": float(hmin), "height_max_mm": float(hmax),
               "landmarks_mm": {"mouth_half_width": float(mc_x * 1000), "nose_tip_y": float(nose_tip_y * 1000)}},
              open(os.path.join(out_dir, "skin_tex_meta.json"), "w"), indent=1)


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], a[2], a[3], int(a[4]) if len(a) > 4 else None)
