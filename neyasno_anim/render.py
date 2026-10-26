"""네야스노 분위기 2D 픽셀 애니 렌더러.

320x180으로 그린 뒤 nearest-neighbor로 4배 키우고, 자막은 720p에서 선명하게 얹는다.
사운드는 전부 numpy로 합성한다. 사용법: python3 render.py [--preview 초] [--out 파일]
"""
import argparse
import os
import re
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter
from scipy.signal import butter, lfilter

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 320, 180          # 실제 픽셀 해상도
PAD = 8                  # 카메라 흔들림용 여백
CW, CH = W + PAD * 2, H + PAD * 2
SCALE = 4
OW, OH = W * SCALE, H * SCALE
FPS = 24
SR = 44100

SCENES = [  # (시작, 끝, 이름)
    (0, 12, "title"), (12, 40, "room"), (40, 68, "street"), (68, 112, "store"),
    (112, 152, "roof"), (152, 166, "road"), (166, 212, "taxi"), (212, 228, "end"),
]
DURATION = SCENES[-1][1]

# 스타일 가이드 팔레트
C = {k: np.array([int(v[i:i + 2], 16) for i in (1, 3, 5)], np.float32) for k, v in {
    "sky0": "#1c1f2e", "sky1": "#2a2f45", "sky2": "#3b4160",
    "wall0": "#6e7086", "wall1": "#8f8e9c", "stone": "#a59a8a",
    "warm0": "#e0a050", "warm1": "#f2c272", "neonR": "#e3343a", "neonY": "#f2c84b",
    "cold": "#e8f0ff",
}.items()}


def hx(s):
    return tuple(int(s[i:i + 2], 16) for i in (1, 3, 5))


def hash2(a, b, seed=0):
    a = np.asarray(a, np.int64)
    b = np.asarray(b, np.int64)
    with np.errstate(over="ignore"):
        h = (a * 73856093) ^ (b * 19349663) ^ (seed * 83492791)
        h = (h ^ (h >> 13)) * 1274126177
    return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0


def smoothstep(e0, e1, x):
    x = np.clip((x - e0) / (e1 - e0), 0, 1)
    return x * x * (3 - 2 * x)


RNG = np.random.default_rng(7)

# ---------------------------------------------------------------- 공용 텍스처
_cloud = gaussian_filter(RNG.random((60, 260)), 2.2)
_cloud = (_cloud - _cloud.min()) / (_cloud.max() - _cloud.min())
CLOUD = np.kron(_cloud, np.ones((4, 4)))  # 블록진 구름 (240 x 1040)

_yy, _xx = np.mgrid[0:H, 0:W]
_d = np.sqrt(((_xx - W / 2) / (W / 2)) ** 2 + ((_yy - H / 2) / (H / 2)) ** 2)
VIGNETTE = (1 - 0.55 * smoothstep(0.55, 1.45, _d))[..., None].astype(np.float32)


def sky(arr, t, top, bot, horizon, cloud_speed=1.5, cloud_amt=0.35):
    """남청색 그라디언트 + 천천히 흐르는 먹구름."""
    h = horizon
    g = np.linspace(0, 1, h)[:, None, None]
    arr[:h] = top * (1 - g) + bot * g
    ox = int(t * cloud_speed) % (CLOUD.shape[1] - CW)
    cl = CLOUD[:h, ox:ox + CW][..., None]
    arr[:h] *= (1 - cloud_amt) + cloud_amt * 1.6 * cl


def cobbles(arr, horizon, cam_x, cam_z, base, fog, tint=None, seed=1):
    """원근 돌길. 가까울수록 블록이 커져서 모자이크처럼 보인다."""
    ys = np.arange(horizon + 1, CH)
    z = 260.0 / (ys - horizon)
    xs = np.arange(CW) - CW / 2
    Z = z[:, None]
    X = xs[None, :] * Z / 60.0 + cam_x
    cs = 1.1
    cx = np.floor(X / cs).astype(np.int64)
    cz = np.floor((Z + cam_z) / cs).astype(np.int64)
    v = hash2(cx, cz, seed)
    edge = ((X / cs) % 1 < 0.12) | (((Z + cam_z) / cs) % 1 < 0.12)
    shade = 0.7 + 0.45 * v - 0.25 * edge
    col = base[None, None] * shade[..., None]
    f = smoothstep(2, 40, Z)[..., None]
    col = col * (1 - f) + fog * f
    if tint is not None:
        col = col + tint[: len(ys)]
    arr[horizon + 1:] = col


def rain(arr, t, n=220, color=(150, 160, 195), speed=260, slant=0.25, light=None):
    rng = np.random.default_rng(3)
    x0 = rng.random(n) * (CW + 60) - 30
    y0 = rng.random(n) * CH
    sp = speed * (0.7 + 0.6 * rng.random(n))
    ys = (y0 + t * sp) % (CH + 20) - 10
    xs = x0 + ys * slant
    for x, y in zip(xs.astype(int), ys.astype(int)):
        for k in range(4):
            yy, xx = y + k, x + int(k * slant)
            if 0 <= yy < CH and 0 <= xx < CW:
                c = np.array(color, np.float32)
                if light is not None:
                    c = c + light[yy, xx] * 0.8
                arr[yy, xx] = arr[yy, xx] * 0.45 + c * 0.55


def glow(arr, thresh=195, radius=3.0, amt=0.55):
    lum = arr.max(axis=2, keepdims=True)
    m = np.clip(lum - thresh, 0, None) / (255 - thresh)
    g = gaussian_filter(arr * m, (radius, radius, 0))
    return arr + g * amt


def to_img(arr):
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def from_img(img):
    return np.asarray(img, np.float32).copy()


# ---------------------------------------------------------------- 그리기 도우미
def window_grid(draw, x, y, cols, rows, w, h, gx, gy, lit, base, rng, warm=hx("#e0a050")):
    for r in range(rows):
        for c in range(cols):
            wx, wy = x + c * gx, y + r * gy
            if (wx, wy) in lit:
                draw.rectangle([wx, wy, wx + w - 1, wy + h - 1], fill=warm)
            else:
                d = int(rng.integers(-6, 6))
                draw.rectangle([wx, wy, wx + w - 1, wy + h - 1], fill=tuple(max(0, v + d) for v in base))


def bare_tree(draw, x, y, h, col, rng, depth=4, ang=-np.pi / 2, width=2):
    if depth == 0 or h < 2:
        return
    x2 = x + np.cos(ang) * h
    y2 = y + np.sin(ang) * h
    draw.line([x, y, x2, y2], fill=col, width=width)
    for _ in range(2 + (depth > 2)):
        bare_tree(draw, x2, y2, h * (0.55 + 0.2 * rng.random()), col, rng, depth - 1,
                  ang + rng.uniform(-0.8, 0.8), max(1, width - 1))


def pixel_text(img, xy, text, size, fill, font="NanumGothic-ExtraBold.ttf"):
    f = ImageFont.truetype(os.path.join(HERE, "fonts", font), size)
    d = ImageDraw.Draw(img)
    d.fontmode = "1"  # 안티앨리어싱 없이 픽셀 그대로
    d.text(xy, text, font=f, fill=fill)


# ================================================================ 장면
class Room:
    """고시원 1.5평. 창문 대신 벽에 붙은 창문 그림. 차가운 형광등."""

    def __init__(self):
        rng = np.random.default_rng(11)
        Wd = 430
        img = Image.new("RGB", (Wd, CH))
        d = ImageDraw.Draw(img)
        # 벽: 얼룩진 청회색
        a = np.zeros((CH, Wd, 3), np.float32)
        a[:] = (54, 70, 78)
        st = gaussian_filter(rng.random((CH // 3 + 1, Wd // 3 + 1)), 1.0)
        st = np.kron(st, np.ones((3, 3)))[:CH, :Wd]
        a *= (0.82 + 0.3 * st)[..., None]
        a[:, :, :] *= np.linspace(1.0, 0.9, CH)[:, None, None]
        img = to_img(a)
        d = ImageDraw.Draw(img)
        # 걸레받이와 바닥 장판
        d.rectangle([0, 148, Wd, 151], fill=(38, 44, 50))
        for y in range(152, CH):
            k = (y - 152) / (CH - 152)
            d.line([0, y, Wd, y], fill=(int(78 - 20 * k), int(66 - 16 * k), int(58 - 12 * k)))
        for x in range(-200, Wd + 200, 26):
            d.line([x, 152, x + (x - Wd / 2) * 0.9, CH], fill=(60, 50, 44))
        # 침대 (왼쪽)
        d.rectangle([0, 112, 112, 160], fill=(46, 52, 66))
        d.rectangle([0, 104, 104, 118], fill=(70, 82, 104))
        d.rectangle([4, 96, 40, 108], fill=(150, 150, 140))  # 베개
        for x in range(0, 104, 7):
            d.line([x, 120, x + 4, 158], fill=(56, 64, 82))
        # 옷걸이 셔츠
        d.line([128, 40, 136, 40], fill=(30, 30, 34))
        d.polygon([(122, 46), (142, 46), (146, 82), (118, 82)], fill=(92, 96, 110))
        d.line([132, 46, 132, 82], fill=(70, 74, 88))
        # 창문 그림 (종이 + 크레용)
        px, py, pw, ph = 168, 38, 100, 74
        d.rectangle([px + 2, py + 2, px + pw + 2, py + ph + 2], fill=(30, 36, 42))
        d.rectangle([px, py, px + pw, py + ph], fill=(214, 208, 190))
        d.rectangle([px + 6, py + 6, px + pw - 6, py + ph - 6], fill=(108, 160, 214))
        d.rectangle([px + 6, py + ph - 26, px + pw - 6, py + ph - 6], fill=(92, 168, 84))
        d.line([px + pw / 2, py + 6, px + pw / 2, py + ph - 6], fill=(150, 100, 70), width=2)
        d.line([px + 6, py + ph / 2, px + pw - 6, py + ph / 2], fill=(150, 100, 70), width=2)
        for sx, sy in ((px + 22, py + 18), (px + pw - 22, py + 20)):  # 해가 두 개
            d.ellipse([sx - 7, sy - 7, sx + 7, sy + 7], fill=(246, 206, 60))
            for k in range(8):
                ang = k * np.pi / 4
                d.line([sx + np.cos(ang) * 9, sy + np.sin(ang) * 9,
                        sx + np.cos(ang) * 13, sy + np.sin(ang) * 13], fill=(246, 206, 60))
        d.polygon([(px + 60, py + ph - 26), (px + 72, py + ph - 38), (px + 84, py + ph - 26)], fill=(200, 70, 60))
        d.rectangle([px + 62, py + ph - 26, px + 82, py + ph - 12], fill=(230, 220, 200))
        for tx, ty in ((px - 3, py - 3), (px + pw - 7, py - 3), (px - 3, py + ph - 5), (px + pw - 7, py + ph - 5)):
            d.rectangle([tx, ty, tx + 9, ty + 7], fill=(226, 214, 168))  # 테이프
        # 책상과 삼각김밥 (오른쪽)
        d.rectangle([300, 118, Wd, 124], fill=(96, 80, 64))
        d.rectangle([304, 124, 310, CH], fill=(70, 58, 48))
        d.rectangle([Wd - 12, 124, Wd - 6, CH], fill=(70, 58, 48))
        d.rectangle([330, 70, 392, 112], fill=(24, 26, 30))  # 꺼진 모니터
        d.rectangle([356, 112, 366, 118], fill=(30, 32, 36))
        d.polygon([(338, 117), (350, 97), (362, 117)], fill=(236, 236, 230))
        d.rectangle([346, 105, 354, 117], fill=(26, 34, 30))
        d.rectangle([370, 108, 380, 117], fill=(210, 60, 50))  # 컵
        # 형광등
        d.rectangle([150, 8, 286, 13], fill=(200, 205, 210))
        self.base = from_img(img)
        self.Wd = Wd
        self.tube = (150, 8, 286, 13)

    def flicker(self, t):
        if 2.0 < t < 2.25 or 2.4 < t < 2.5 or 19.5 < t < 19.7:
            return 0.35
        n = hash2(int(t * 20), 5)
        return 1.0 if n > 0.04 else 0.55

    def frame(self, t):
        f = self.flicker(t)
        ox = int(50 + 44 * smoothstep(15.8, 17.3, t))  # 창문 그림 -> 책상 위 삼각김밥
        a = self.base[:, ox:ox + CW].copy()
        # 형광등 조명: 위쪽 중앙이 밝고 차가운 청록
        yy, xx = np.mgrid[0:CH, 0:CW]
        cx = (self.tube[0] + self.tube[2]) / 2 - ox
        light = np.exp(-(((xx - cx) / 190) ** 2 + ((yy - 6) / 150) ** 2))
        a *= (0.4 + 0.55 * light * f)[..., None]
        a += np.array([0, 8, 10]) * light[..., None] * f
        x0, y0, x1, y1 = self.tube
        if f > 0.5:
            a[y0:y1 + 1, max(0, x0 - ox):max(0, x1 - ox + 1)] = C["cold"]
        return a


class Street:
    """해 질 녘 동네. 판상 아파트, 낡은 2층 건물, 차고 줄, 앙상한 나무, 돌길. 옆으로 천천히 걷는다."""
    HZ = 120

    def __init__(self):
        rng = np.random.default_rng(21)
        self.speed = 25.0
        # 먼 레이어: 판상 아파트 실루엣
        far = Image.new("RGBA", (900, CH), (0, 0, 0, 0))
        d = ImageDraw.Draw(far)
        self.far_lit = []
        x = 0
        while x < 900:
            w = int(rng.integers(50, 90))
            h = int(rng.integers(55, 95))
            top = self.HZ - h
            base = (int(70 + rng.integers(-8, 8)), 74, 98)
            d.rectangle([x, top, x + w, self.HZ], fill=base + (255,))
            for r in range((h - 6) // 7):
                for c in range((w - 6) // 6):
                    wx, wy = x + 4 + c * 6, top + 4 + r * 7
                    d.rectangle([wx, wy, wx + 2, wy + 3], fill=(52, 56, 76, 255))
                    if rng.random() < 0.06:
                        self.far_lit.append((wx, wy, rng.random()))
            x += w + int(rng.integers(8, 30))
        self.far = far
        # 중간 레이어: 낡은 2층 건물, 차고, 나무, 가로등, 끝에 편의점
        mid = Image.new("RGBA", (1100, CH), (0, 0, 0, 0))
        d = ImageDraw.Draw(mid)
        self.mid_lit = []
        self.lamps = []
        x = 10
        kinds = ["old", "garage", "tree", "old", "garage", "garage", "tree", "old", "lamp", "garage", "tree"]
        for k in kinds:
            if k == "old":
                w = int(rng.integers(120, 160))
                top = self.HZ - 58
                wall = (int(118 + rng.integers(-10, 10)), 114, 128)
                d.rectangle([x, top, x + w, self.HZ + 4], fill=wall + (255,))
                d.polygon([(x - 4, top), (x + w + 4, top), (x + w - 6, top - 10), (x + 6, top - 10)], fill=(92, 70, 66, 255))
                d.rectangle([x, top + 26, x + w, top + 28], fill=(96, 94, 110, 255))
                for row in range(2):
                    for c in range((w - 14) // 22):
                        wx, wy = x + 10 + c * 22, top + 6 + row * 28
                        d.rectangle([wx - 1, wy - 1, wx + 10, wy + 16], fill=(150, 146, 156, 255))
                        d.ellipse([wx - 1, wy - 5, wx + 10, wy + 4], fill=(150, 146, 156, 255))
                        d.rectangle([wx, wy, wx + 9, wy + 15], fill=(40, 44, 62, 255))
                        if rng.random() < 0.3:
                            self.mid_lit.append((wx, wy, rng.random()))
                x += w + 12
            elif k == "garage":
                n = int(rng.integers(3, 6))
                for i in range(n):
                    gx = x + i * 30
                    d.rectangle([gx, self.HZ - 22, gx + 29, self.HZ + 4], fill=(150, 146, 150, 255))
                    door = [(120, 44, 44), (70, 80, 110), (88, 96, 80), (130, 90, 60)][int(rng.integers(0, 4))]
                    d.rectangle([gx + 4, self.HZ - 16, gx + 25, self.HZ + 4], fill=door + (255,))
                    d.line([gx + 14, self.HZ - 16, gx + 14, self.HZ + 4], fill=(40, 40, 50, 255))
                d.rectangle([x - 2, self.HZ - 25, x + n * 30 + 1, self.HZ - 22], fill=(110, 106, 112, 255))
                x += n * 30 + 14
            elif k == "tree":
                bare_tree(d, x + 15, self.HZ + 2, 22, (34, 34, 44, 255), rng, depth=5, width=3)
                x += 40
            elif k == "lamp":
                d.rectangle([x, self.HZ - 50, x + 1, self.HZ + 4], fill=(30, 30, 38, 255))
                d.line([x, self.HZ - 50, x + 8, self.HZ - 50], fill=(30, 30, 38, 255))
                self.lamps.append((x + 8, self.HZ - 48))
                x += 30
        # 편의점 (장면 끝에 보임)
        sx = 520
        self.store_x = sx
        d.rectangle([sx, self.HZ - 40, sx + 70, self.HZ + 4], fill=(70, 70, 88, 255))
        d.rectangle([sx + 6, self.HZ - 24, sx + 64, self.HZ + 2], fill=(226, 236, 248, 255))
        for r in range(3):
            for c in range(9):
                col = tuple(int(v) for v in rng.integers(60, 230, 3))
                d.rectangle([sx + 9 + c * 6, self.HZ - 21 + r * 7, sx + 13 + c * 6, self.HZ - 18 + r * 7], fill=col + (255,))
        d.rectangle([sx + 4, self.HZ - 36, sx + 66, self.HZ - 28], fill=(30, 30, 40, 255))
        self.mid = mid

    def frame(self, t):
        a = np.zeros((CH, CW, 3), np.float32)
        sky(a, t, C["sky0"], C["sky2"] * 1.15 + np.array([16, 8, 0]), self.HZ + 6, cloud_speed=2)
        cam = t * self.speed
        img = to_img(a)
        # 먼 레이어
        fo = int(cam * 0.18)
        far = self.far.crop((fo, 0, fo + CW, CH))
        img.paste(far, (0, 0), far)
        d = ImageDraw.Draw(img)
        for wx, wy, ph in self.far_lit:
            if 0 <= wx - fo < CW and np.sin(t * 0.4 + ph * 40) > -0.6:
                d.rectangle([wx - fo, wy, wx - fo + 2, wy + 3], fill=hx("#f2c272"))
        mo = int(cam * 0.5)
        mid = self.mid.crop((mo, 0, mo + CW, CH))
        img.paste(mid, (0, 0), mid)
        d = ImageDraw.Draw(img)
        for wx, wy, ph in self.mid_lit:
            if -12 < wx - mo < CW:
                on = hash2(int(t * 0.5 + ph * 9), int(ph * 100)) > 0.15
                if on:
                    d.rectangle([wx - mo, wy, wx - mo + 9, wy + 15], fill=hx("#e0a050"))
        sx = self.store_x - mo
        if -80 < sx < CW:
            pixel_text(img, (sx + 19, self.HZ - 38), "편의점", 10, hx("#f2c84b"))
        a = from_img(img)
        for lx, ly in self.lamps:
            px = lx - mo
            if -40 < px < CW + 40:
                fl = 1.0 if hash2(int(t * 12), 3) > 0.1 else 0.3
                yy, xx = np.mgrid[0:CH, 0:CW]
                cone = np.exp(-(((xx - px) / 30) ** 2 + ((yy - ly - 40) / 45) ** 2)) * fl
                a += np.array([90, 60, 20]) * cone[..., None]
                if 0 <= px < CW - 3:
                    a[ly:ly + 2, px - 1:px + 3] = C["warm1"]
        cobbles(a, self.HZ + 4, cam / 8.0, 0, np.array([96, 96, 116]), C["sky2"] * 0.95)
        rain(a, t, n=160)
        return a


class Store:
    """밤, 편의점 앞 플라스틱 테이블. 고개 숙인 아저씨, 컵라면 김."""
    HZ = 150

    def __init__(self):
        rng = np.random.default_rng(31)
        img = Image.new("RGB", (CW, CH), hx("#1c1f2e"))
        d = ImageDraw.Draw(img)
        # 건물 벽
        d.rectangle([0, 10, CW, self.HZ], fill=(46, 48, 64))
        for _ in range(500):
            x, y = int(rng.integers(0, CW)), int(rng.integers(10, self.HZ))
            v = int(rng.integers(-8, 8))
            d.rectangle([x, y, x + 2, y + 2], fill=(46 + v, 48 + v, 64 + v))
        # 위층 창문 (하나만 켜짐)
        for i, wx in enumerate(range(20, CW, 46)):
            col = hx("#e0a050") if i == 4 else (30, 34, 50)
            d.rectangle([wx, 22, wx + 20, 40], fill=col)
        # 쇼윈도
        self.win = (150, 70, 318, 148)
        x0, y0, x1, y1 = self.win
        d.rectangle([x0 - 3, y0 - 3, x1 + 3, y1], fill=(90, 92, 104))
        d.rectangle([x0, y0, x1, y1], fill=(178, 190, 204))
        for r in range(4):
            sy = y0 + 8 + r * 18
            d.rectangle([x0 + 4, sy + 12, x1 - 50, sy + 14], fill=(150, 156, 170))
            for c in range((x1 - 50 - x0 - 8) // 7):
                col = tuple(int(v) for v in rng.integers(40, 235, 3))
                hh = int(rng.integers(6, 12))
                d.rectangle([x0 + 6 + c * 7, sy + 12 - hh, x0 + 10 + c * 7, sy + 11], fill=col)
        d.rectangle([x1 - 44, y0 + 2, x1 - 4, y1], fill=(150, 164, 182))  # 문
        d.line([x1 - 24, y0 + 2, x1 - 24, y1], fill=(120, 130, 150))
        d.rectangle([x0 - 6, 50, x1 + 6, 66], fill=(24, 24, 34))  # 간판
        self.base_img = img
        self.sign_xy = (x0 + 34, 51)
        # 플라스틱 테이블/의자
        self.props = []

    def draw_props(self, d, t, talking):
        # 테이블 (초록)
        d.rectangle([84, 128, 146, 132], fill=(44, 120, 70))
        d.line([92, 132, 90, 160], fill=(36, 96, 56), width=2)
        d.line([138, 132, 140, 160], fill=(36, 96, 56), width=2)
        # 빈 의자 (빨강, 오른쪽)
        d.rectangle([150, 136, 166, 139], fill=(170, 46, 46))
        d.rectangle([162, 116, 166, 139], fill=(170, 46, 46))
        d.line([151, 139, 150, 160], fill=(140, 36, 36), width=2)
        d.line([165, 139, 166, 160], fill=(140, 36, 36), width=2)
        # 아저씨 의자 (파랑, 왼쪽)
        d.rectangle([52, 136, 76, 139], fill=(50, 70, 140))
        d.rectangle([48, 114, 52, 139], fill=(50, 70, 140))
        d.line([53, 139, 52, 160], fill=(40, 56, 110), width=2)
        d.line([75, 139, 76, 160], fill=(40, 56, 110), width=2)
        # 아저씨: 갈색 파카, 고개 숙임. 말할 때 고개가 살짝 움직인다
        bob = int(round(np.sin(t * 9) * 1)) if talking else 0
        d.rectangle([62, 138, 80, 144], fill=(40, 40, 52))       # 허벅지
        d.rectangle([76, 140, 82, 160], fill=(36, 36, 48))       # 다리
        d.rectangle([80, 158, 88, 161], fill=(20, 20, 24))       # 신발
        d.polygon([(54, 140), (52, 112), (60, 102), (74, 104), (80, 116), (78, 140)], fill=(92, 66, 46))
        d.line([62, 110, 84, 126], fill=(80, 56, 40), width=4)  # 팔
        d.ellipse([68 + 0, 94 + bob, 82, 108 + bob], fill=(170, 130, 104))  # 머리
        d.rectangle([68, 93 + bob, 82, 99 + bob], fill=(40, 36, 36))          # 모자
        # 컵라면
        d.rectangle([106, 120, 116, 128], fill=(220, 60, 40))
        d.rectangle([106, 120, 116, 121], fill=(240, 240, 230))
        # 캔
        d.rectangle([124, 121, 128, 128], fill=(200, 200, 70))

    def frame(self, t, talking=False):
        img = self.base_img.copy()
        pixel_text(img, self.sign_xy, "편의점  24", 12, hx("#f2c84b"))
        d = ImageDraw.Draw(img)
        if hash2(int(t * 8), 9) > 0.08:   # 빨간 24 네온 깜빡임
            d.rectangle([self.win[2] - 30, 54, self.win[2] - 6, 62], outline=hx("#e3343a"))
        a = from_img(img)
        # 바닥: 젖은 아스팔트 + 쇼윈도 반사
        cobbles(a, self.HZ, 0, 0, np.array([58, 60, 76]), C["sky0"], seed=4)
        x0, y0, x1, y1 = self.win
        refl = np.zeros_like(a)
        hgt = min(CH - self.HZ - 1, y1 - y0)
        src = a[y1 - hgt:y1, x0:x1][::-1]
        refl[self.HZ + 1:self.HZ + 1 + hgt, x0:x1] = src
        refl = gaussian_filter(refl, (1.5, 0.6, 0))
        wob = (np.sin(np.arange(CH)[:, None] * 1.3 + t * 3) * 0.5 + 0.5)
        a += refl * 0.32 * (0.7 + 0.3 * wob[..., None])
        img = to_img(a)
        self.draw_props(ImageDraw.Draw(img), t, talking)
        a = from_img(img)
        # 가게 불빛이 바깥을 비춤
        yy, xx = np.mgrid[0:CH, 0:CW]
        spill = np.exp(-(((xx - 234) / 120) ** 2 + ((yy - 140) / 50) ** 2))
        a += np.array([34, 38, 44]) * spill[..., None]
        light = np.array([40, 44, 50])[None, None] * spill[..., None]
        # 컵라면 김
        for i in range(6):
            ph = (t * 0.6 + i / 6) % 1
            sx = int(111 + np.sin(ph * 6 + i) * 3 + ph * 4)
            sy = int(118 - ph * 26)
            if 0 <= sy < CH:
                a[sy:sy + 2, sx:sx + 2] = a[sy:sy + 2, sx:sx + 2] * (0.5 + ph * 0.5) + 200 * (0.5 - ph * 0.5)
        rain(a, t, n=200, light=light)
        return a


class Roof:
    """지붕 위 밤 도시. 빨간 네온, 먹구름, 깜빡이는 창문들. 건너편 옥상에서 화분에 물 주는 사람."""
    HZ = 112

    def __init__(self):
        rng = np.random.default_rng(41)
        Wd = 420
        lay = Image.new("RGBA", (Wd, CH), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        self.lit = []
        for depth, (col, y0, hmin, hmax) in enumerate([((34, 38, 58), 108, 20, 46), ((28, 31, 48), 116, 14, 34)]):
            x = -10
            while x < Wd:
                w = int(rng.integers(14, 38))
                h = int(rng.integers(hmin, hmax))
                d.rectangle([x, y0 - h, x + w, CH], fill=col + (255,))
                for wy in range(y0 - h + 3, y0 + 14, 4 + depth):
                    for wx in range(x + 2, x + w - 2, 3 + depth):
                        if rng.random() < 0.13:
                            self.lit.append((wx, wy, rng.random(), depth))
                x += w + int(rng.integers(0, 6))
        self.city = lay
        self.Wd = Wd
        self.rng = rng

    def frame(self, t):
        a = np.zeros((CH, CW, 3), np.float32)
        sky(a, t, C["sky0"] * 0.8, C["sky2"] * 0.95, 124, cloud_speed=5, cloud_amt=0.75)
        ox = int(20 + t * 0.9)
        img = to_img(a)
        city = self.city.crop((ox, 0, ox + CW, CH))
        img.paste(city, (0, 0), city)
        d = ImageDraw.Draw(img)
        for wx, wy, ph, dep in self.lit:
            x = wx - ox
            if 0 <= x < CW and np.sin(t * (0.2 + ph * 0.3) + ph * 50) > -0.75:
                c = hx("#f2c272") if ph > 0.3 else hx("#e0a050")
                d.rectangle([x, wy, x + dep, wy + dep], fill=c)
        # 건너편 옥상 (중간)
        bx = 214 - ox + 20
        d.rectangle([bx, 128, bx + 110, CH], fill=(40, 42, 58))
        d.rectangle([bx - 3, 126, bx + 113, 129], fill=(56, 58, 74))
        # 화분에 물 주는 사람: 장면 28초쯤 불이 켜진다
        on = t > 29.0
        px = bx + 70
        if on:
            d.rectangle([px - 14, 104, px - 12, 128], fill=(30, 30, 36))
            d.rectangle([px - 18, 102, px - 8, 105], fill=hx("#f2c272"))
            d.rectangle([px, 112, px + 4, 126], fill=(70, 80, 100))
            d.ellipse([px, 107, px + 4, 111], fill=(190, 150, 120))
            d.line([px + 4, 116, px + 9, 118], fill=(150, 160, 170), width=2)
            d.rectangle([px + 10, 121, px + 16, 126], fill=(140, 80, 50))
            d.line([px + 13, 121, px + 11, 115], fill=(70, 140, 70))
            d.line([px + 13, 121, px + 16, 116], fill=(70, 140, 70))
            if int(t * 6) % 2:
                d.point([(px + 10, 119), (px + 11, 120)], fill=(170, 200, 230))
        # 빨간 네온 간판 "노래방" (왼쪽 건물 위)
        nx = 34 - int(ox * 0.3)
        d.rectangle([nx + 6, 104, nx + 8, 140], fill=(30, 26, 32))
        d.rectangle([nx + 58, 104, nx + 60, 140], fill=(30, 26, 32))
        neon_on = hash2(int(t * 7), 17) > 0.07
        pixel_text(img, (nx, 80), "노래방", 22, hx("#e3343a") if neon_on else (90, 30, 34))
        a = from_img(img)
        # 앞쪽 지붕: 골강판 줄무늬, 네온 쪽이 붉게 물듦
        top = 140
        ys = np.arange(top, CH)
        xs = np.arange(CW)
        k = (ys - top) / (CH - top)
        # 골강판 골이 소실점으로 모이도록: x를 깊이로 나눈 좌표에서 줄무늬
        u = (xs[None, :] - CW * 0.45) / (ys[:, None] - top + 8.0)
        corrug = 0.62 + 0.38 * (np.floor(u * 1.6) % 2)
        base = np.array([96, 92, 104])
        roof = base[None, None] * corrug[..., None] * (0.7 + 0.5 * k)[:, None, None]
        red = np.exp(-((xs - (nx + 30)) / 140.0) ** 2)[None, :] * (0.4 + 0.6 * (1 - k))[:, None]
        roof += np.array([150, 20, 30]) * red[..., None] * (1.0 if neon_on else 0.35)
        a[top:] = roof
        # 굴뚝
        a[118:142, 150:162] = np.array([66, 58, 60])
        a[116:119, 148:164] = np.array([50, 44, 48])
        rain(a, t, n=90, speed=200, color=(120, 120, 150))
        return a


class Road:
    """거의 검은 밤 도로. 먼 가로등 하나. 노란 등 켠 택시가 다가온다."""
    HZ = 104

    def frame(self, t):
        a = np.zeros((CH, CW, 3), np.float32)
        sky(a, t, np.array([6, 8, 16]), np.array([14, 18, 34]), self.HZ + 1, cloud_speed=1, cloud_amt=0.25)
        img = to_img(a)
        d = ImageDraw.Draw(img)
        # 먼 아파트 실루엣
        d.rectangle([50, 78, 98, self.HZ], fill=(26, 30, 46))
        d.rectangle([98, 86, 120, self.HZ], fill=(22, 26, 40))
        d.rectangle([230, 88, 268, self.HZ], fill=(22, 26, 40))
        d.point([(84, 86)], fill=(220, 60, 180))
        # 전깃줄
        for i in range(3):
            d.line([0, 18 + i * 6, 170, 70 + i * 3], fill=(10, 12, 18))
        # 가로등 기둥
        d.rectangle([292, 30, 294, self.HZ + 30], fill=(16, 18, 26))
        a = from_img(img)
        cobbles(a, self.HZ, 0, t * 0.1, np.array([40, 46, 74]), np.array([14, 18, 34]), seed=9)
        yy, xx = np.mgrid[0:CH, 0:CW]
        lamp = np.exp(-(((xx - 290) / 60) ** 2 + ((yy - 40) / 70) ** 2))
        a += np.array([70, 90, 130]) * lamp[..., None]
        a[34:37, 282:292] = C["cold"]
        # 택시: 6초부터 소실점에서 다가와 12.5초에 멈춘다
        p = smoothstep(5.5, 12.5, t)
        if t > 5.5:
            s = 0.08 + p * 1.6
            cx = CW / 2 + p * 40
            cy = self.HZ + 2 + p * 52
            img = to_img(a)
            d = ImageDraw.Draw(img)
            bw, bh = 70 * s, 18 * s
            d.rectangle([cx - bw / 2, cy - bh, cx + bw / 2, cy], fill=(104, 110, 126))
            d.rectangle([cx - bw / 2, cy - bh * 0.25, cx + bw / 2, cy], fill=(70, 74, 86))
            d.polygon([(cx - bw * 0.35, cy - bh), (cx + bw * 0.35, cy - bh), (cx + bw * 0.25, cy - bh * 1.8),
                       (cx - bw * 0.25, cy - bh * 1.8)], fill=(90, 96, 110))
            d.polygon([(cx - bw * 0.3, cy - bh * 1.05), (cx + bw * 0.3, cy - bh * 1.05), (cx + bw * 0.22, cy - bh * 1.7),
                       (cx - bw * 0.22, cy - bh * 1.7)], fill=(20, 24, 34))
            d.rectangle([cx - bw * 0.1, cy - bh * 2.1, cx + bw * 0.1, cy - bh * 1.8], fill=hx("#f2c84b"))
            for sx in (-1, 1):
                d.rectangle([cx + sx * bw * 0.38 - 3 * s, cy - bh * 0.6, cx + sx * bw * 0.38 + 3 * s, cy - bh * 0.3],
                            fill=(240, 232, 200))
            a = from_img(img)
            # 헤드라이트 빛
            hl = np.exp(-(((xx - cx) / (30 + 80 * p)) ** 2 + ((yy - cy - 8 * s) / (6 + 20 * p)) ** 2))
            a += np.array([60, 55, 40]) * hl[..., None] * (0.3 + 0.7 * p)
        rain(a, t, n=70, color=(70, 80, 110))
        return a


class Taxi:
    """택시 뒷좌석. 거의 암전, 계기판 초록빛, 지나가는 가로등이 실내를 훑는다."""

    def frame(self, t):
        a = np.zeros((CH, CW, 3), np.float32)
        yy, xx = np.mgrid[0:CH, 0:CW]
        # 앞유리 너머 도로
        ws = (yy > 40) & (yy < 96) & (xx > 70 + (96 - yy) * 0.6) & (xx < 280 - (96 - yy) * 0.6)
        road = np.zeros_like(a)
        road[:] = (10, 14, 28)
        road[70:96] = (16, 20, 34)
        for i in range(6):   # 가로등이 다가와 지나감
            ph = (t * 0.35 + i / 6) % 1
            lx = int(CW / 2 + 20 + ph ** 2 * 140)
            ly = int(66 - ph ** 2 * 30)
            r = 1 + int(ph * 3)
            road[max(0, ly - r):ly + r, max(0, lx - r):lx + r] = (230, 170, 90)
        a[ws] = road[ws]
        # 오른쪽 옆 창문: 도시 불빛이 흘러간다
        sw = (yy > 46) & (yy < 104) & (xx > 292) & (xx < CW - 2)
        side = np.zeros_like(a)
        side[:] = (12, 16, 30)
        for i in range(40):
            hy = 60 + int(hash2(i, 2) * 36)
            hxp = int((hash2(i, 3) * 400 - t * 60) % 400) - 40 + 290
            col = (240, 190, 110) if hash2(i, 4) > 0.3 else (120, 150, 230)
            side[hy:hy + 2, max(0, hxp):max(0, hxp + 6)] = col
        a[sw] = side[sw]
        # 실내: 앞좌석 헤드레스트, 기사 어깨 실루엣
        img = to_img(a)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([86, 74, 136, 118], 8, fill=(14, 14, 18))     # 기사 머리받침
        d.rectangle([104, 118, 118, 128], fill=(12, 12, 16))
        d.rectangle([70, 124, 160, CH], fill=(16, 16, 20))                # 기사 좌석
        d.rounded_rectangle([196, 80, 244, 120], 8, fill=(18, 18, 22))    # 조수석 머리받침
        d.rectangle([182, 126, 262, CH], fill=(20, 20, 24))
        d.rectangle([0, 0, CW, 34], fill=(6, 6, 8))                       # 천장
        d.rectangle([0, 0, 62, CH], fill=(8, 8, 10))                      # 왼쪽 기둥
        a = from_img(img)
        # 계기판 초록빛
        dash = np.exp(-(((xx - 166) / 14) ** 2 + ((yy - 104) / 7) ** 2))
        a += np.array([20, 120, 50]) * dash[..., None]
        a[102:105, 160:173] += np.array([30, 140, 60])
        # 가로등 스윕: 주기적으로 실내가 주황빛으로 밝아짐
        sweep_ph = (t * 0.35) % 1
        sweep = np.exp(-((xx - (CW - sweep_ph * CW * 1.6)) / 70.0) ** 2) * np.exp(-((sweep_ph - 0.5) / 0.3) ** 2)
        a += np.array([60, 38, 14]) * sweep[..., None] * 0.6
        # 잠드는 눈꺼풀 (택시 장면 끝)
        close = smoothstep(40.5, 45.5, t)
        blink = 0.0
        if 36.0 < t < 36.4 or 38.6 < t < 39.2:
            blink = 0.6
        lid = max(close, blink)
        if lid > 0:
            cut = int(lid * CH / 2)
            a[:cut] = 0
            a[CH - cut:] = 0
        return a


# ================================================================ 자막
def parse_script(path):
    lines = []
    pat = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)-(\d+):(\d+(?:\.\d+)?)\]\s*\[(T|A!|A|B)\]\s*(.+)")
    with open(path, encoding="utf-8") as f:
        for raw in f:
            m = pat.match(raw.strip())
            if not m:
                continue
            t0 = int(m[1]) * 60 + float(m[2])
            t1 = int(m[3]) * 60 + float(m[4])
            ko, _, en = m[6].partition("|")
            lines.append((t0, t1, m[5], ko.strip(), en.strip()))
    return lines


class Subs:
    def __init__(self):
        fdir = os.path.join(HERE, "fonts")
        self.fa = ImageFont.truetype(os.path.join(fdir, "NanumGothic-ExtraBold.ttf"), 34)
        self.fa_big = ImageFont.truetype(os.path.join(fdir, "NanumGothic-ExtraBold.ttf"), 44)
        self.fb = ImageFont.truetype(os.path.join(fdir, "NanumGothic-ExtraBold.ttf"), 30)
        self.fen = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", 19)
        self.ft = ImageFont.truetype(os.path.join(fdir, "NanumGothic-ExtraBold.ttf"), 36)

    def draw(self, img, lines, t):
        d = ImageDraw.Draw(img)
        for t0, t1, kind, ko, en in lines:
            if not (t0 <= t < t1):
                continue
            alpha = min(1.0, (t - t0) / 0.15, (t1 - t) / 0.15)
            if kind == "T":
                a = int(255 * min(1.0, (t - t0) / 0.6, (t1 - t) / 0.6))
                layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
                ImageDraw.Draw(layer).text((OW / 2, OH / 2), ko, font=self.ft, fill=(225, 225, 230, a), anchor="mm")
                img.paste(layer, (0, 0), layer)
            elif kind in ("A", "A!"):
                f = self.fa_big if kind == "A!" else self.fa
                d.text((OW / 2, OH - 64), ko, font=f, fill=(255, 255, 255), anchor="mm",
                       stroke_width=3, stroke_fill=(0, 0, 0))
            elif kind == "B":
                d.text((OW / 2, OH - 92), ko, font=self.fb, fill=(245, 214, 58), anchor="mm",
                       stroke_width=2, stroke_fill=(0, 0, 0))
                d.text((OW / 2, OH - 58), en, font=self.fen, fill=(235, 235, 235), anchor="mm",
                       stroke_width=1, stroke_fill=(0, 0, 0))
            _ = alpha


# ================================================================ 사운드
def butter_f(x, cutoff, kind="low", order=2):
    b, a = butter(order, cutoff / (SR / 2), btype=kind)
    return lfilter(b, a, x).astype(np.float32)


def env_scene(n, s0, s1, fade=0.8):
    e = np.zeros(n, np.float32)
    i0, i1 = int(s0 * SR), int(min(s1, n / SR) * SR)
    e[i0:i1] = 1
    k = int(fade * SR)
    if i1 - i0 > 2 * k:
        e[i0:i0 + k] = np.linspace(0, 1, k)
        e[i1 - k:i1] = np.linspace(1, 0, k)
    return e


def chord_pad(n, chords, dur, gain=0.12, seed=0):
    rng = np.random.default_rng(seed)
    out = np.zeros(n, np.float32)
    t = np.arange(int(dur * SR)) / SR
    a = np.minimum(1, t / (dur * 0.35)) * np.minimum(1, (dur - t) / (dur * 0.35))
    for i in range(n // len(t) + 1):
        notes = chords[i % len(chords)]
        seg = np.zeros(len(t), np.float32)
        for f in notes:
            for det in (-0.6, 0.6):
                ph = rng.random() * 2 * np.pi
                seg += np.sin(2 * np.pi * (f + det) * t + ph) + 0.3 * np.sin(4 * np.pi * (f + det) * t + ph)
        seg *= a
        s = i * len(t)
        e = min(n, s + len(t))
        if s >= n:
            break
        out[s:e] += seg[:e - s]
    return out * gain / 6


def bell(n, times, freqs, gain=0.15):
    out = np.zeros(n, np.float32)
    L = int(2.5 * SR)
    tt = np.arange(L) / SR
    for tm, f in zip(times, freqs):
        s = int(tm * SR)
        if s >= n:
            continue
        x = (np.sin(2 * np.pi * f * tt) + 0.4 * np.sin(2 * np.pi * f * 2.01 * tt)) * np.exp(-tt * 2.2)
        e = min(n, s + L)
        out[s:e] += x[:e - s] * gain
    return out


def synth_audio(path, dur):
    n = int(dur * SR)
    rng = np.random.default_rng(99)
    t = np.arange(n) / SR
    white = rng.standard_normal(n).astype(np.float32)
    mix = np.zeros(n, np.float32)
    sc = {name: (s0, s1) for s0, s1, name in SCENES}

    rain_ = butter_f(butter_f(white, 400, "high"), 6000) * 0.10
    brown = butter_f(np.cumsum(white) / 300, 0.5, "high")
    wind = butter_f(brown, 500) * (0.6 + 0.4 * np.sin(t * 0.21) * np.sin(t * 0.13))[: n] * 0.05

    # 오프닝 / 엔딩: 낮은 드론
    drone = (np.sin(2 * np.pi * 55 * t) + 0.5 * np.sin(2 * np.pi * 82.4 * t)) * 0.05
    mix += drone * (env_scene(n, *sc["title"], 1.5) + env_scene(n, *sc["end"], 1.5))
    # 고시원: 형광등 험 + 벽 너머 먹먹한 빗소리
    hum = (np.sin(2 * np.pi * 120 * t) + 0.3 * np.sin(2 * np.pi * 240 * t)) * 0.025
    mix += (hum + butter_f(rain_, 700) * 0.8) * env_scene(n, *sc["room"])
    # 동네: 비 + 바람 + 멀리 개
    mix += (rain_ + wind) * env_scene(n, *sc["street"])
    # 편의점: 비 + 먹먹한 가게 음악
    shop = chord_pad(n, [[261.6, 329.6, 392], [220, 261.6, 329.6], [174.6, 220, 261.6], [196, 246.9, 293.7]], 2.0, 0.6, 1)
    shop = butter_f(shop, 900) * 0.25
    mix += (rain_ * 0.9 + wind * 0.5 + shop) * env_scene(n, *sc["store"])
    # 옥상: 감상 음악 (Am-F-C-G) + 종소리 + 약한 비
    pad = chord_pad(n, [[110, 220, 261.6, 329.6], [87.3, 174.6, 220, 261.6], [130.8, 196, 261.6, 329.6],
                        [98, 196, 246.9, 293.7]], 4.0, 1.0, 2)
    s0 = sc["roof"][0]
    melody_t = [s0 + 2 + i * 2.0 for i in range(18)]
    melody_f = [659.3, 523.3, 440, 523.3, 587.3, 523.3, 440, 392, 440, 523.3, 659.3, 587.3, 523.3, 440, 392, 329.6, 440, 440]
    roof_music = butter_f(pad, 1800) * 0.9 + bell(n, melody_t, melody_f, 0.05)
    mix += (roof_music + rain_ * 0.55 + wind * 0.6) * env_scene(n, *sc["roof"], 1.5)
    # 밤 도로: 바람 + 다가오는 차
    r0 = sc["road"][0]
    approach = smoothstep(r0 + 5, r0 + 12, t) * (1 - smoothstep(r0 + 12.5, r0 + 14, t) * 0.6)
    engine = butter_f(white, 180) * 0.6 + np.sin(2 * np.pi * 45 * t) * 0.05
    mix += (wind * 1.4 + rain_ * 0.3 + engine * approach * 0.8) * env_scene(n, *sc["road"])
    # 택시: 엔진 + 타이어 + 아주 작은 패드
    rumble = butter_f(white, 120) * 0.9 + np.sin(2 * np.pi * 38 * t) * 0.04 + butter_f(rain_, 1200) * 0.5
    taxi_pad = butter_f(chord_pad(n, [[110, 164.8, 220], [98, 146.8, 196]], 6.0, 0.5, 3), 700)
    tx = sc["taxi"]
    fade_out = 1 - smoothstep(tx[0] + 40, tx[1], t) * 0.9
    mix += (rumble + taxi_pad) * env_scene(n, *tx, 1.0) * fade_out
    # 엔딩 개그: 알람
    e0 = sc["end"][1] - 1.6
    for k in range(3):
        s = int((e0 + k * 0.25) * SR)
        L = int(0.12 * SR)
        if s + L < n:
            mix[s:s + L] += np.sign(np.sin(2 * np.pi * 1760 * np.arange(L) / SR)) * 0.05

    mix = np.tanh(mix * 1.4) * 0.8
    pcm = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ================================================================ 렌더
def scene_at(t):
    for s0, s1, name in SCENES:
        if s0 <= t < s1:
            return name, t - s0, s0, s1
    return "end", t - SCENES[-1][0], SCENES[-1][0], SCENES[-1][1]


def render(out, start=0.0, end=DURATION, still=None):
    lines = parse_script(os.path.join(HERE, "script", "ep01.txt"))
    subs = Subs()
    objs = {"room": Room(), "street": Street(), "store": Store(), "roof": Roof(), "road": Road(), "taxi": Taxi()}
    b_lines = [(a, b) for a, b, k, *_ in lines if k == "B"]

    def make(t):
        name, lt, s0, s1 = scene_at(t)
        if name in ("title", "end"):
            a = np.zeros((CH, CW, 3), np.float32)
        elif name == "store":
            talking = any(a0 <= t < a1 for a0, a1 in b_lines)
            a = objs[name].frame(lt, talking)
        else:
            a = objs[name].frame(lt)
        # 카메라 흔들림: 걸을 때 크게, 택시는 진동
        if name == "street":
            dx, dy = np.sin(lt * 2.2) * 2, abs(np.sin(lt * 4.4)) * 3
        elif name == "taxi":
            dx, dy = 0, (hash2(int(lt * 30), 1) - 0.5) * 1.5
        else:
            dx, dy = np.sin(lt * 0.5) * 1.5, np.sin(lt * 0.7) * 1.2
        ox, oy = int(round(PAD + dx)), int(round(PAD + dy))
        a = a[oy:oy + H, ox:ox + W]
        if name not in ("title", "end"):
            a = glow(a)
        a = a * VIGNETTE + np.random.default_rng(int(t * FPS)).normal(0, 5, (H, W, 1))
        fade = min(1.0, (t - s0) / 0.7, (s1 - t) / 0.7)
        a = a * max(0.0, fade)
        img = to_img(a).resize((OW, OH), Image.NEAREST)
        subs.draw(img, lines, t)
        return img

    if still is not None:
        make(still).save(out)
        return

    wav = out + ".wav"
    synth_audio(wav, DURATION)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OW}x{OH}",
           "-r", str(FPS), "-i", "-", "-ss", str(start), "-t", str(end - start), "-i", wav,
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-shortest", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    nframes = int((end - start) * FPS)
    for i in range(nframes):
        t = start + i / FPS
        p.stdin.write(make(t).tobytes())
        if i % (FPS * 10) == 0:
            print(f"{t:6.1f}s / {end:.0f}s", flush=True)
    p.stdin.close()
    p.wait()
    os.remove(wav)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "ep01.mp4"))
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=DURATION)
    ap.add_argument("--still", type=float, help="이 시각의 한 프레임만 PNG로 저장")
    args = ap.parse_args()
    render(args.out, args.start, args.end, args.still)
