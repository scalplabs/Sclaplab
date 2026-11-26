"""Procedural strand grooming (Blender, run inside lookdev).

All hair is generated on the rest-pose body surface:
  scalp   : guide strands from a flow field (forward-combed top, side/back fall, crown whorl),
            children clumped to guides with frizz; layered volume via surface-offset constraint
  brows   : roots sampled from eyebrow card alpha, lying flat, medial hairs upward
  lashes  : rooted on the lid-margin boundary loops, curled away from the eye
  stubble : 0.4-1.2 mm stubs on the beard mask follicles
  vellus  : 1-2.5 mm fine translucent hair on face/neck
  arms    : 4-10 mm hair on forearms
Outputs Blender hair-curves objects (offline strands) and realtime hair CARDS mesh
(ribbons following each guide, UV'd onto a generated strand atlas).
"""
import math

import bpy
import bmesh
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def _bvh(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    return BVHTree.FromObject(ob, dg)


def _tri_data(ob):
    me = ob.data
    me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    vi = np.zeros(nt * 3, np.int32)
    me.loop_triangles.foreach_get("vertices", vi)
    li = np.zeros(nt * 3, np.int32)
    me.loop_triangles.foreach_get("loops", li)
    co = np.zeros(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    uv = np.zeros(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    return co, vi.reshape(-1, 3), uv[li.reshape(-1, 3)]


def sample_surface(ob, n, rng, mask_img=None, mask_ch=0, region=None, mask_thresh=None):
    """area-weighted random surface samples, accepted with prob = mask(uv)"""
    co, tri, tuv = _tri_data(ob)
    a, b, c = co[tri[:, 0]], co[tri[:, 1]], co[tri[:, 2]]
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
    if region is not None:
        cen = (a + b + c) / 3
        area = area * region(cen)
    p = area / area.sum()
    out_p, out_uv, out_n = [], [], []
    need = n
    tries = 0
    while need > 0 and tries < 40:
        tries += 1
        m = int(need * 2.2) + 64
        t = rng.choice(len(tri), m, p=p)
        r1, r2 = rng.random(m), rng.random(m)
        s = np.sqrt(r1)
        w = np.stack([1 - s, s * (1 - r2), s * r2], 1)
        pts = a[t] * w[:, :1] + b[t] * w[:, 1:2] + c[t] * w[:, 2:]
        uvs = tuv[t, 0] * w[:, :1] + tuv[t, 1] * w[:, 1:2] + tuv[t, 2] * w[:, 2:]
        nrm = np.cross(b[t] - a[t], c[t] - a[t])
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
        if mask_img is not None:
            H, W = mask_img.shape[:2]
            px = np.clip((uvs[:, 0] * W).astype(int), 0, W - 1)
            py = np.clip(((1 - uvs[:, 1]) * H).astype(int), 0, H - 1)
            mv = mask_img[py, px, mask_ch] / 255.0
            if mask_thresh is not None:
                acc = mv > mask_thresh
            else:
                acc = rng.random(m) < mv
            pts, uvs, nrm = pts[acc], uvs[acc], nrm[acc]
        take = min(need, len(pts))
        out_p.append(pts[:take])
        out_uv.append(uvs[:take])
        out_n.append(nrm[:take])
        need -= take
    return np.concatenate(out_p), np.concatenate(out_uv), np.concatenate(out_n)


def make_curves(name, strands, radii, material=None, parent=None):
    """strands: list/array (S, K, 3) ; radii (S, K)"""
    strands = np.asarray(strands, np.float32)
    S, K, _ = strands.shape
    cv = bpy.data.hair_curves.new(name) if hasattr(bpy.data, "hair_curves") else None
    if cv is None:
        raise RuntimeError("hair curves API unavailable")
    cv.add_curves([K] * S)
    cv.position_data.foreach_set("vector", strands.reshape(-1))
    rad = cv.attributes.get("radius") or cv.attributes.new("radius", "FLOAT", "POINT")
    rad.data.foreach_set("value", np.asarray(radii, np.float32).reshape(-1))
    ob = bpy.data.objects.new(name, cv)
    bpy.context.scene.collection.objects.link(ob)
    if material:
        cv.materials.append(material)
    if parent:
        ob.parent = parent
    return ob


# ------------------------------------------------------------------- scalp
def groom_scalp(body, scalp_mask, head_frame, rng, n_guides=2200, n_children=70000, K=14):
    """head_frame: dict(O=origin(mid-eyes), s=scale). Returns strands (S,K,3), radii, guides."""
    O = np.array(head_frame["O"])
    s = head_frame["s"]
    bvh = _bvh(body)
    crown = O + np.array([0.012, 0.075, 0.115]) * s      # crown whorl (x,y=back(+Y),z up) in Blender coords
    crown = O + np.array([0.012 * s, 0.075 * s, 0.112 * s])

    def head_coords(p):
        q = p - O
        return q[:, 0], q[:, 2], -q[:, 1]  # hx, hy(up), hz(fwd)

    def flow(p, nrm):
        hx, hy, hz = head_coords(p)
        theta = np.arctan2(hx, hz + 0.045 * s)
        ath = np.abs(theta)
        # top: forward with slight sweep to character's right (-x); sides: down/back; back: down
        fwd = np.stack([-0.25 * np.ones_like(hx), -np.ones_like(hx), 0.15 * np.ones_like(hx)], 1)  # -Y forward
        down = np.stack([np.zeros_like(hx), 0.35 * np.ones_like(hx), -np.ones_like(hx)], 1)
        side_out = np.stack([np.sign(hx) * 0.3, 0.6 * np.ones_like(hx), -np.ones_like(hx)], 1)
        top_w = np.clip((hy - 0.05 * s) / (0.05 * s), 0, 1) * np.clip(1 - (ath - 1.3) / 0.6, 0, 1)
        back_w = np.clip((ath - 2.0) / 0.6, 0, 1)
        side_w = np.clip(1 - top_w - back_w, 0, 1)
        f = top_w[:, None] * fwd + side_w[:, None] * side_out + back_w[:, None] * down
        # crown whorl swirl
        dc = p - crown
        rc = np.linalg.norm(dc, axis=1)
        swirl = np.cross(nrm, dc)
        sw = np.exp(-(rc / (0.03 * s)) ** 2)[:, None]
        f = f * (1 - sw) + swirl / (np.linalg.norm(swirl, axis=1, keepdims=True) + 1e-9) * sw
        # project to tangent plane
        f = f - (f * nrm).sum(1, keepdims=True) * nrm
        return f / (np.linalg.norm(f, axis=1, keepdims=True) + 1e-9)

    def length(p):
        hx, hy, hz = head_coords(p)
        theta = np.arctan2(hx, hz + 0.045 * s)
        ath = np.abs(theta)
        top = np.clip((hy - 0.04 * s) / (0.05 * s), 0, 1)
        L = 0.018 + 0.040 * top * np.clip(1 - (ath - 1.0) / 1.2, 0, 1)
        L += 0.010 * np.clip((0.3 - ath) / 0.3, 0, 1) * top          # fringe longer
        L = np.where(ath > 2.2, 0.022 - 0.008 * np.clip((0.02 * s - hy) / (0.08 * s), 0, 1), L)
        return L * s

    gp, guv, gn = sample_surface(body, n_guides, rng, scalp_mask, 2, mask_thresh=0.45)
    G = _grow(gp, gn, flow, length(gp), bvh, K, rng, lift=0.9, offset0=0.0015, offset_gain=0.18)
    # children
    cp, cuv, cn = sample_surface(body, n_children, rng, scalp_mask, 2)
    # nearest guide (root distance)
    from scipy.spatial import cKDTree
    tree = cKDTree(gp)
    _, gi = tree.query(cp, k=1)
    Gr = G[gi]                                     # (S,K,3)
    tpar = np.linspace(0, 1, K)[None, :, None]
    off = (cp - gp[gi])[:, None, :]
    clump = 0.55 * tpar ** 1.2                    # tips converge to guide
    frz = rng.normal(0, 1, (len(cp), K, 3)).cumsum(1) * 0.00025 * s * tpar
    lenscale = rng.uniform(0.82, 1.05, len(cp))[:, None, None]
    C = Gr[:, :1] + off + (Gr - Gr[:, :1]) * lenscale + (-off) * clump + frz
    # keep children outside the scalp
    C = _push_out(C, bvh, 0.0008)
    rad = (0.000045 * (1 - 0.6 * np.linspace(0, 1, K)))[None, :].repeat(len(C), 0)
    return C, rad, G, gp, gn


def _push_out(S, bvh, mind):
    sh = S.shape
    P = S.reshape(-1, 3)
    for i in range(len(P)):
        if i % sh[1] == 0:
            continue  # roots stay
        loc, nrm, _, d = bvh.find_nearest(Vector(P[i]))
        if loc is None:
            continue
        v = Vector(P[i]) - loc
        inside = v.dot(nrm) < 0
        if inside or d < mind:
            P[i] = np.array(loc + nrm * mind)
    return P.reshape(sh)


def _grow(roots, nrms, flow_fn, lengths, bvh, K, rng, lift=0.8, offset0=0.001, offset_gain=0.15, gravity=0.0):
    S = len(roots)
    out = np.zeros((S, K, 3), np.float32)
    out[:, 0] = roots
    p = roots.copy()
    n0 = nrms.copy()
    f0 = flow_fn(roots, nrms)
    d = n0 * math.cos(lift) + f0 * math.sin(lift)
    seg = lengths / (K - 1)
    for k in range(1, K):
        t = k / (K - 1)
        # blend direction toward flow tangent (hair lies down), plus a little gravity
        cur_n = np.zeros_like(p)
        dist = np.zeros(S)
        for i in range(S):
            loc, nrm, _, dd = bvh.find_nearest(Vector(p[i]))
            cur_n[i] = nrm if loc is not None else n0[i]
            dist[i] = dd if loc is not None else 0
        f = flow_fn(p, cur_n)
        d = d * 0.55 + f * 0.45 + np.array([0, 0, -gravity])
        d += rng.normal(0, 0.05, d.shape)
        d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-9
        p = p + d * seg[:, None]
        # volume: keep a minimum height above scalp that grows along the strand
        want = offset0 + offset_gain * lengths * t
        for i in range(S):
            loc, nrm, _, dd = bvh.find_nearest(Vector(p[i]))
            if loc is None:
                continue
            v = Vector(p[i]) - loc
            h = v.dot(nrm)
            if h < want[i]:
                p[i] = np.array(loc + nrm * want[i] + (v - nrm * h) * 1.0)
        out[:, k] = p
    return out


# ------------------------------------------------------------------- face hair
def groom_brows(body, brow_card, rng, n=1400, s=1.0):
    """roots inside eyebrow card alpha, projected to skin; direction from card UV (u along brow)."""
    img = None
    mat = brow_card.active_material
    for nd in mat.node_tree.nodes if mat and mat.use_nodes else []:
        if nd.type == "TEX_IMAGE" and nd.image:
            img = nd.image
    co, tri, tuv = _tri_data(brow_card)
    a, b, c = co[tri[:, 0]], co[tri[:, 1]], co[tri[:, 2]]
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
    px_arr = None
    if img is not None:
        W, H = img.size
        px_arr = np.array(img.pixels[:], np.float32).reshape(H, W, 4)
    bvh = _bvh(body)
    roots, dirs = [], []
    p = area / area.sum()
    while len(roots) < n:
        t = rng.choice(len(tri), 4000, p=p)
        r1, r2 = rng.random(4000), rng.random(4000)
        sq = np.sqrt(r1)
        w = np.stack([1 - sq, sq * (1 - r2), sq * r2], 1)
        pts = a[t] * w[:, :1] + b[t] * w[:, 1:2] + c[t] * w[:, 2:]
        uvs = tuv[t, 0] * w[:, :1] + tuv[t, 1] * w[:, 1:2] + tuv[t, 2] * w[:, 2:]
        if px_arr is not None:
            H, W = px_arr.shape[:2]
            al = px_arr[np.clip((uvs[:, 1] * H).astype(int), 0, H - 1), np.clip((uvs[:, 0] * W).astype(int), 0, W - 1), 3]
            keep = rng.random(4000) < al ** 0.7
            pts, uvs = pts[keep], uvs[keep]
        for q, uv in zip(pts, uvs):
            loc, nrm, _, _ = bvh.find_nearest(Vector(q))
            if loc is None:
                continue
            side = 1 if q[0] > 0 else -1
            # brow hair direction: lateral, rising medially, descending laterally
            ulat = abs(q[0])
            along = Vector((side, 0, 0))
            rise = np.interp(ulat, [0.012 * s, 0.022 * s, 0.045 * s, 0.06 * s], [1.6, 0.6, 0.05, -0.35])
            dv = (along + Vector((0, 0, rise))).normalized()
            dv = (dv - nrm * dv.dot(nrm)).normalized()
            roots.append((np.array(loc), np.array(nrm), np.array(dv)))
            if len(roots) >= n:
                break
    K = 6
    S = np.zeros((len(roots), K, 3), np.float32)
    for i, (r, nr, dv) in enumerate(roots):
        L = rng.uniform(0.006, 0.011) * s
        ang = rng.normal(0, 0.18)
        lift = rng.uniform(0.15, 0.35)
        for k in range(K):
            t = k / (K - 1)
            S[i, k] = r + dv * L * t + nr * (L * lift * math.sin(t * math.pi * 0.6)) + \
                np.cross(nr, dv) * L * ang * t
    rad = (0.000045 * (1 - 0.7 * np.linspace(0, 1, K)))[None, :].repeat(len(S), 0)
    return S, rad


def eyelid_loops(body, eye_centres, R=0.012, bins=72):
    """Lid-margin rings. The hm08 body is closed (lids fold into the socket), so the margin is found
    geometrically: for each angular bin around the gaze axis (-Y), the front vertex nearest the eye
    surface with the smallest distance from the gaze axis. Ring is ordered and smoothed."""
    me = body.data
    co = np.zeros(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    res = {}
    for side, c in eye_centres.items():
        d = co - c
        dist = np.linalg.norm(d, axis=1)
        front = (d[:, 1] < -0.004) & (dist < R + 0.0045) & (dist > R - 0.0035)
        idx = np.nonzero(front)[0]
        ang = np.arctan2(d[idx, 2], d[idx, 0])
        rax = np.hypot(d[idx, 0], d[idx, 2])
        ring = []
        for k in range(bins):
            a0 = -np.pi + 2 * np.pi * k / bins
            sel = np.abs(np.angle(np.exp(1j * (ang - a0)))) < np.pi / bins * 1.5
            if not sel.any():
                continue
            j = idx[sel][np.argmin(rax[sel])]
            ring.append(co[j])
        ring = np.array(ring)
        # smooth (circular)
        for _ in range(2):
            ring = (np.roll(ring, 1, 0) + 2 * ring + np.roll(ring, -1, 0)) / 4
        res[side] = ring
    return res


def groom_lashes(loop_pts, eye_c, rng, upper_n=110, lower_n=55, s=1.0):
    """loop_pts: ordered lid-margin points. Upper = above eye centre z."""
    S = []
    K = 7
    c = np.array(eye_c)
    pts = np.asarray(loop_pts)
    # resample loop densely
    seg = np.linalg.norm(np.diff(np.vstack([pts, pts[:1]]), axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    total = cum[-1]
    for upper, cnt in ((True, upper_n), (False, lower_n)):
        k = 0
        tries = 0
        while k < cnt and tries < cnt * 20:
            tries += 1
            t = rng.random() * total
            i = np.searchsorted(cum, t) - 1
            i = np.clip(i, 0, len(pts) - 1)
            f = (t - cum[i]) / max(seg[i], 1e-9)
            p = pts[i] * (1 - f) + pts[(i + 1) % len(pts)] * f
            if (p[2] > c[2] + 0.0005) != upper:
                continue
            # exclude extreme corners (canthi)
            lat = abs(p[0] - c[0])
            if lat > 0.0125 * s:
                continue
            out = p - c
            out[1] = 0
            out /= np.linalg.norm(out) + 1e-9
            fwd = np.array([0, -1.0, 0])
            centr = 1 - (lat / (0.0125 * s)) ** 2
            L = (rng.uniform(0.0075, 0.0105) if upper else rng.uniform(0.004, 0.0065)) * s * (0.6 + 0.4 * centr)
            curl = 1.0 if upper else -1.0
            strand = []
            for j in range(K):
                tt = j / (K - 1)
                ang = tt * (0.9 + rng.normal(0, 0.1))
                d = fwd * math.cos(ang) + out * math.sin(ang)
                d[2] = abs(d[2]) * curl if upper else -abs(d[2])
                strand.append(p + fwd * 0.0004 + (fwd * 0.7 + out * 0.3) * L * tt +
                              np.array([0, 0, curl]) * L * 0.55 * tt ** 1.6)
            S.append(strand)
            k += 1
    S = np.array(S, np.float32)
    rad = (0.00005 * (1 - 0.8 * np.linspace(0, 1, K)))[None, :].repeat(len(S), 0)
    return S, rad


def groom_short(body, mask_img, ch, rng, n, length_range, s=1.0, flow=None, radius=0.00003, region=None,
                lie=0.6, K=4):
    pts, uvs, nrm = sample_surface(body, n, rng, mask_img, ch, region=region)
    S = np.zeros((len(pts), K, 3), np.float32)
    for i in range(len(pts)):
        nr = nrm[i]
        if flow is not None:
            f = flow(pts[i], nr)
        else:
            f = np.array([0, 0, -1.0])
        f = f - nr * f.dot(nr)
        f /= np.linalg.norm(f) + 1e-9
        L = rng.uniform(*length_range) * s
        for k in range(K):
            t = k / (K - 1)
            S[i, k] = pts[i] + (nr * math.cos(lie) + f * math.sin(lie)) * L * t + nr * 0.00002
    rad = (radius * (1 - 0.7 * np.linspace(0, 1, K)))[None, :].repeat(len(S), 0)
    return S, rad


# ------------------------------------------------------------------- realtime cards
def cards_from_guides(G, roots_n, width=0.010, name="DH_HairCards", atlas_cols=8):
    """Each guide strand -> camera-independent ribbon (2 verts per point) oriented along the scalp
    tangent, UV v along strand, u across; u range assigned to one of atlas_cols strand-bundle tiles."""
    S, K, _ = G.shape
    verts, faces, uvs = [], [], []
    for i in range(S):
        g = G[i]
        n0 = roots_n[i]
        col = i % atlas_cols
        u0, u1 = col / atlas_cols, (col + 1) / atlas_cols
        base = len(verts)
        for k in range(K):
            t = k / (K - 1)
            tan = g[min(k + 1, K - 1)] - g[max(k - 1, 0)]
            tan /= np.linalg.norm(tan) + 1e-9
            side = np.cross(tan, n0)
            side /= np.linalg.norm(side) + 1e-9
            w = width * (1 - 0.55 * t)
            verts.append(g[k] - side * w / 2)
            verts.append(g[k] + side * w / 2)
            uvs.append(((u0, 1 - t), (u1, 1 - t)))
        for k in range(K - 1):
            a = base + 2 * k
            faces.append((a, a + 1, a + 3, a + 2))
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    uvl = me.uv_layers.new(name="UVMap")
    flat = []
    for f in faces:
        for vi in f:
            k = vi // 2
            gi = 0
            flat.append(None)
    # assign per-loop uv from vertex uv table
    vuv = []
    for pair in uvs:
        vuv.extend(pair)
    for poly in me.polygons:
        poly.use_smooth = True
        for li in poly.loop_indices:
            uvl.data[li].uv = vuv[me.loops[li].vertex_index]
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def hair_card_atlas(path, res=1024, cols=8, seed=5, color=(0.05, 0.035, 0.028)):
    """Strand-bundle atlas: RGBA, alpha = strand coverage, RGB = per-strand tint variation."""
    rng = np.random.default_rng(seed)
    img = np.zeros((res, res, 4), np.float32)
    tw = res // cols
    yy = np.arange(res)
    for cidx in range(cols):
        x0 = cidx * tw
        nstr = rng.integers(28, 46)
        for _ in range(nstr):
            xc = x0 + rng.uniform(0.12, 0.88) * tw
            tip = rng.uniform(0.55, 1.0) * res
            amp = rng.uniform(0.5, 3.0)
            ph = rng.uniform(0, 6.28)
            w = rng.uniform(0.7, 1.6)
            tint = rng.uniform(0.75, 1.3)
            for y in range(int(tip)):
                t = y / res
                x = xc + amp * math.sin(t * 9 + ph) + (t ** 2) * rng.normal(0, 0.0)
                taper = 1 - (y / tip) ** 3
                xs = np.arange(max(int(x - 3), x0), min(int(x + 4), x0 + tw))
                if len(xs) == 0:
                    continue
                cov = np.exp(-((xs - x) / (w * taper + 0.25)) ** 2) * taper
                row = img[y, xs]
                row[:, 3] = 1 - (1 - row[:, 3]) * (1 - cov)
                row[:, :3] = np.maximum(row[:, :3], np.array(color) * tint * cov[:, None])
                img[y, xs] = row
    from PIL import Image
    a8 = (np.clip(img, 0, 1) * 255).astype(np.uint8)
    a8[..., :3] = (np.clip(np.where(img[..., 3:] > 0, img[..., :3] / np.maximum(img[..., 3:], 1e-3), color), 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
    Image.fromarray(a8, "RGBA").save(path)
    return path
