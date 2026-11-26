"""Vectorised procedural noise (numpy): gradient (Perlin) noise 2D/3D with
optional periodicity, fBm, ridged, and Worley/cellular F1/F2. Deterministic by seed."""
import numpy as np

_GRAD3 = np.array([[1, 1, 0], [-1, 1, 0], [1, -1, 0], [-1, -1, 0], [1, 0, 1], [-1, 0, 1], [1, 0, -1], [-1, 0, -1],
                   [0, 1, 1], [0, -1, 1], [0, 1, -1], [0, -1, -1], [1, 1, 0], [-1, 1, 0], [0, -1, 1], [0, -1, -1]],
                  dtype=np.float32)


def _perm(seed):
    rng = np.random.default_rng(seed)
    p = rng.permutation(256).astype(np.int64)
    return np.concatenate([p, p])


def _fade(t):
    return t * t * t * (t * (t * 6 - 15) + 10)


def perlin3(x, y, z, seed=0):
    p = _perm(seed)
    xi, yi, zi = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64), np.floor(z).astype(np.int64)
    xf, yf, zf = (x - xi).astype(np.float32), (y - yi).astype(np.float32), (z - zi).astype(np.float32)
    xi &= 255
    yi &= 255
    zi &= 255
    u, v, w = _fade(xf), _fade(yf), _fade(zf)

    def g(ix, iy, iz, dx, dy, dz):
        h = p[p[p[ix] + iy] + iz] & 15
        gr = _GRAD3[h]
        return gr[..., 0] * dx + gr[..., 1] * dy + gr[..., 2] * dz

    x1, y1, z1 = (xi + 1) & 255, (yi + 1) & 255, (zi + 1) & 255
    n000 = g(xi, yi, zi, xf, yf, zf)
    n100 = g(x1, yi, zi, xf - 1, yf, zf)
    n010 = g(xi, y1, zi, xf, yf - 1, zf)
    n110 = g(x1, y1, zi, xf - 1, yf - 1, zf)
    n001 = g(xi, yi, z1, xf, yf, zf - 1)
    n101 = g(x1, yi, z1, xf - 1, yf, zf - 1)
    n011 = g(xi, y1, z1, xf, yf - 1, zf - 1)
    n111 = g(x1, y1, z1, xf - 1, yf - 1, zf - 1)
    nx00 = n000 + u * (n100 - n000)
    nx10 = n010 + u * (n110 - n010)
    nx01 = n001 + u * (n101 - n001)
    nx11 = n011 + u * (n111 - n011)
    nxy0 = nx00 + v * (nx10 - nx00)
    nxy1 = nx01 + v * (nx11 - nx01)
    return nxy0 + w * (nxy1 - nxy0)


def fbm3(P, freq, octaves=4, lac=2.0, gain=0.5, seed=0):
    """P (...,3) metres; freq cycles/metre"""
    out = np.zeros(P.shape[:-1], np.float32)
    amp, f, norm = 1.0, freq, 0.0
    for o in range(octaves):
        out += amp * perlin3(P[..., 0] * f, P[..., 1] * f, P[..., 2] * f, seed + o * 31)
        norm += amp
        amp *= gain
        f *= lac
    return out / norm


def worley3(P, cell, seed=0, jitter=0.9):
    """Cellular noise. cell = feature spacing (metres). returns F1, F2 (metres), and cell id hash (0..1)."""
    Q = P / cell
    base = np.floor(Q).astype(np.int64)
    F1 = np.full(P.shape[:-1], 1e9, np.float32)
    F2 = np.full(P.shape[:-1], 1e9, np.float32)
    ID = np.zeros(P.shape[:-1], np.float32)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                c = base + np.array([dx, dy, dz])
                h = (c[..., 0] * 73856093) ^ (c[..., 1] * 19349663) ^ (c[..., 2] * 83492791) ^ (seed * 2654435761)
                h = h & 0x7FFFFFFF
                r1 = ((h * 1103515245 + 12345) & 0x7FFFFFFF) / 2147483647.0
                r2 = ((h * 22695477 + 1) & 0x7FFFFFFF) / 2147483647.0
                r3 = ((h * 134775813 + 7) & 0x7FFFFFFF) / 2147483647.0
                fp = c + 0.5 + jitter * (np.stack([r1, r2, r3], -1) - 0.5)
                d = np.linalg.norm(Q - fp, axis=-1).astype(np.float32)
                closer = d < F1
                F2 = np.where(closer, F1, np.minimum(F2, d))
                ID = np.where(closer, r1.astype(np.float32), ID)
                F1 = np.where(closer, d, F1)
    return F1 * cell, F2 * cell, ID


# ---------------------------------------------------------------- periodic 2D
def perlin2_periodic(x, y, period, seed=0):
    """Tileable 2D gradient noise; x,y in cells, period integer cells."""
    rng = np.random.default_rng(seed)
    ang = rng.uniform(0, 2 * np.pi, (period, period)).astype(np.float32)
    G = np.stack([np.cos(ang), np.sin(ang)], -1)
    xi, yi = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    xf, yf = (x - xi).astype(np.float32), (y - yi).astype(np.float32)
    x0, y0 = xi % period, yi % period
    x1, y1 = (xi + 1) % period, (yi + 1) % period

    def d(ix, iy, dx, dy):
        g = G[iy, ix]
        return g[..., 0] * dx + g[..., 1] * dy

    u, v = _fade(xf), _fade(yf)
    a = d(x0, y0, xf, yf) + u * (d(x1, y0, xf - 1, yf) - d(x0, y0, xf, yf))
    b = d(x0, y1, xf, yf - 1) + u * (d(x1, y1, xf - 1, yf - 1) - d(x0, y1, xf, yf - 1))
    return a + v * (b - a)


def worley2_periodic(x, y, period, seed=0, jitter=0.9):
    rng = np.random.default_rng(seed)
    F = rng.uniform(0.5 - jitter / 2, 0.5 + jitter / 2, (period, period, 2)).astype(np.float32)
    S = rng.uniform(0, 1, (period, period)).astype(np.float32)
    xi, yi = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    F1 = np.full(x.shape, 1e9, np.float32)
    F2 = np.full(x.shape, 1e9, np.float32)
    ID = np.zeros(x.shape, np.float32)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            cx, cy = xi + dx, yi + dy
            f = F[cy % period, cx % period]
            px, py = cx + f[..., 0], cy + f[..., 1]
            dd = np.hypot(x - px, y - py).astype(np.float32)
            closer = dd < F1
            F2 = np.where(closer, F1, np.minimum(F2, dd))
            ID = np.where(closer, S[cy % period, cx % period], ID)
            F1 = np.where(closer, dd, F1)
    return F1, F2, ID


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)
