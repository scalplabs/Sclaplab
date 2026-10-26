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
from scipy.signal import butter, fftconvolve, lfilter

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 320, 180          # 실제 픽셀 해상도
PAD = 8                  # 카메라 흔들림용 여백
CW, CH = W + PAD * 2, H + PAD * 2
SCALE = 4
OW, OH = W * SCALE, H * SCALE
FPS = 24
SR = 44100

# 장면: (시작, 끝, 이름, 장면 안에서 몇 초부터 보여줄지)
EPISODES = {
    "ep01": dict(script="ep01.txt", layout="wide", music="ep01", scenes=[
        (0, 12, "title", 0), (12, 40, "room", 0), (40, 68, "street", 0), (68, 112, "store", 0),
        (112, 152, "roof", 0), (152, 166, "road", 0), (166, 212, "taxi", 0), (212, 228, "end", 0)]),
    # 인스타 릴스 1분 세로판, 1인칭: 소주 → 비틀비틀 택시 잡기 → 허무주의 기사. 음악은 처음부터 끝까지 음침하게
    "insta01": dict(script="insta01.txt", layout="reel", music="gloom", scenes=[
        (0, 16, "soju", 0), (16, 26, "road", 3), (26, 60, "taxi", 11)],
        drunk=[(0, 0.25), (5.0, 0.3), (6.5, 0.7), (16, 0.85), (26, 0.8), (31, 0.4), (60, 0.55)]),
}
SCENES = EPISODES["ep01"]["scenes"]
DURATION = SCENES[-1][1]
RW, RH = 1080, 1920          # 릴스 캔버스
RS = 3                       # 릴스에서 픽셀 배율 (960x540)
RY = 600                     # 릴스에서 화면이 놓이는 y


def use_episode(name):
    global SCENES, DURATION
    SCENES = EPISODES[name]["scenes"]
    DURATION = SCENES[-1][1]
    return EPISODES[name]

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


class Soju:
    """1인칭, 편의점 앞 초록 플라스틱 테이블. 빈 소주병들과 소주잔. 뒤 가게는 초점 밖으로 뭉개진다."""
    DRINK = (4.0, 6.2)   # 잔을 들이키는 구간 (장면 안 시간)

    def __init__(self, store):
        self.store = store

    @staticmethod
    def bottle(d, x, base, h, level):
        w = int(h * 0.3)
        neck = int(h * 0.3)
        d.rectangle([x, base - h + neck, x + w, base], fill=(34, 104, 58))
        d.polygon([(x, base - h + neck), (x + w, base - h + neck), (x + w * 0.7, base - h + neck * 0.45),
                   (x + w * 0.3, base - h + neck * 0.45)], fill=(34, 104, 58))
        d.rectangle([x + w * 0.3, base - h + 2, x + w * 0.7, base - h + neck * 0.5], fill=(34, 104, 58))
        d.rectangle([x + w * 0.28, base - h, x + w * 0.72, base - h + 3], fill=(46, 150, 70))      # 뚜껑
        if level > 0:
            d.rectangle([x + 1, base - (h - neck) * level, x + w - 1, base - 1], fill=(120, 190, 140))
        d.rectangle([x, base - h * 0.45, x + w, base - h * 0.28], fill=(214, 230, 214))           # 라벨
        d.rectangle([x + w * 0.2, base - h * 0.42, x + w * 0.8, base - h * 0.31], fill=(40, 120, 70))
        d.line([x + 2, base - h + neck + 2, x + 2, base - 3], fill=(90, 170, 110))                   # 유리 하이라이트

    def frame(self, t):
        bg = self.store.frame(t)
        crop = to_img(bg[30:150, 110:CW])
        a = from_img(crop.resize((CW, CH), Image.BILINEAR))
        a = gaussian_filter(a, (2.2, 2.2, 0)) * 0.85
        img = to_img(a)
        d = ImageDraw.Draw(img)
        # 테이블 상판 (원근)
        d.polygon([(-40, 112), (CW + 40, 112), (CW + 120, CH), (-120, CH)], fill=(26, 72, 44))
        d.line([(-40, 112), (CW + 40, 112)], fill=(60, 128, 80), width=2)
        for gx in range(-200, CW + 200, 36):   # 플라스틱 테이블 홈
            d.line([(CW / 2 + (gx - CW / 2) * 0.55, 114), (gx, CH)], fill=(22, 62, 38))
        # 빈 병들 (뒤쪽), 하나는 누워 있음
        for x, h in ((26, 58), (54, 60), (250, 58)):
            self.bottle(d, x, 124, h, 0)
        d.polygon([(270, 130), (318, 122), (322, 132), (274, 140)], fill=(34, 104, 58))
        d.rectangle([314, 121, 324, 128], fill=(46, 150, 70))
        # 반 남은 병 (앞쪽, 크게)
        self.bottle(d, 214, 160, 84, 0.45)
        # 컵라면
        d.rectangle([100, 120, 128, 140], fill=(200, 56, 40))
        d.rectangle([98, 118, 130, 122], fill=(232, 232, 224))
        # 소주잔: 평소엔 테이블 위, 마실 땐 얼굴 쪽으로 올라온다
        d0, d1 = self.DRINK
        if d0 < t < d1:
            p = (t - d0) / (d1 - d0)
            lift = np.sin(np.pi * p)
            sc = 1 + 6 * lift                 # 잔이 카메라(입) 쪽으로 다가온다
            cx, cy = 168, 150 + 60 * lift
        else:
            sc, cx, cy = 1.0, 168, 150
        gw, gh = 12 * sc, 14 * sc
        d.polygon([(cx - gw / 2, cy - gh), (cx + gw / 2, cy - gh), (cx + gw * 0.38, cy), (cx - gw * 0.38, cy)],
                  fill=(150, 176, 168))
        if t < (d0 + d1) / 2:   # 잔이 입에 닿기 전까지는 소주가 담겨 있음
            d.polygon([(cx - gw * 0.45, cy - gh * 0.7), (cx + gw * 0.45, cy - gh * 0.7), (cx + gw * 0.38, cy - 1),
                       (cx - gw * 0.38, cy - 1)], fill=(206, 226, 220))
        d.line([(cx - gw / 2, cy - gh), (cx + gw / 2, cy - gh)], fill=(230, 240, 236), width=max(1, int(sc)))
        a = from_img(img)
        # 가게 불빛이 테이블에 번짐
        yy, xx = np.mgrid[0:CH, 0:CW]
        a += np.array([30, 34, 40]) * np.exp(-(((xx - 200) / 160) ** 2 + ((yy - 110) / 40) ** 2))[..., None]
        a[112:] *= np.linspace(1.0, 0.55, CH - 112)[:, None, None]   # 앞쪽 테이블은 어둡게
        rain(a, t, n=90, color=(110, 120, 150))
        return a


def drunk(a, t, k):
    """취한 시선: 흔들리고, 기울고, 두 개로 보이고, 흐릿하다. k는 0(멀쩡)~1(만취)."""
    if k <= 0.01:
        return a
    img = to_img(a)
    ang = np.sin(t * 0.7) * 3.5 * k + np.sin(t * 1.9) * 1.0 * k
    img = img.rotate(ang, resample=Image.BILINEAR, center=(CW / 2, CH / 2))
    zoom = 1 + 0.1 * k
    w2, h2 = int(CW / zoom), int(CH / zoom)
    l, u = (CW - w2) // 2 + int(np.sin(t * 0.9) * 6 * k), (CH - h2) // 2 + int(np.sin(t * 1.3) * 3 * k)
    a = from_img(img.crop((l, u, l + w2, u + h2)).resize((CW, CH), Image.BILINEAR))
    off = int(round((5 + 4 * np.sin(t * 0.6)) * k)) + 1
    a = a * 0.6 + np.roll(np.roll(a, off, axis=1), off // 2, axis=0) * 0.4
    sig = 0.3 + 1.5 * k * (0.7 + 0.3 * np.sin(t * 0.9))
    a = gaussian_filter(a, (sig, sig, 0))
    a *= np.array([1.05, 1.0, 0.93]) * (1 - 0.12 * k * (0.5 + 0.5 * np.sin(t * 1.1)))
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
        # 백미러: 기사 눈만 보인다
        d.rectangle([146, 34, 194, 46], fill=(30, 30, 36))
        d.rectangle([148, 36, 192, 44], fill=(22, 26, 34))
        if hash2(int(t * 3), 21) > 0.12:   # 가끔 깜빡
            for ex in (162, 174):
                d.rectangle([ex, 39, ex + 3, 40], fill=(220, 236, 210))
                d.point((ex + 1, 39), fill=(10, 10, 10))
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
    pat = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)-(\d+):(\d+(?:\.\d+)?)\]\s*\[(T|A!|A~|A|B)\]\s*(.+)")
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
    def __init__(self, layout="wide"):
        fdir = os.path.join(HERE, "fonts")
        k = 1.45 if layout == "reel" else 1.0
        ko = os.path.join(fdir, "NanumGothic-ExtraBold.ttf")
        self.fa = ImageFont.truetype(ko, int(34 * k))
        self.fa_big = ImageFont.truetype(ko, int(44 * k))
        self.fb = ImageFont.truetype(ko, int(30 * k))
        self.fen = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", int(19 * k))
        self.ft = ImageFont.truetype(ko, int(36 * k))
        self.fen_title = ImageFont.truetype(ko, 34)
        if layout == "reel":   # 화면 아래 검은 여백에 자막, 인스타 UI에 안 가리게
            self.cx, self.ct, self.ya, self.yb, self.yen = RW / 2, RY + H * RS / 2, RY + H * RS + 110, RY + H * RS + 95, RY + H * RS + 160
        else:
            self.cx, self.ct, self.ya, self.yb, self.yen = OW / 2, OH / 2, OH - 64, OH - 92, OH - 58

    def draw(self, img, lines, t):
        d = ImageDraw.Draw(img)
        for t0, t1, kind, ko, en in lines:
            if not (t0 <= t < t1):
                continue
            alpha = min(1.0, (t - t0) / 0.15, (t1 - t) / 0.15)
            if kind == "T":
                a = int(255 * min(1.0, (t - t0) / 0.6, (t1 - t) / 0.6))
                layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
                ImageDraw.Draw(layer).text((self.cx, self.ct), ko, font=self.ft, fill=(225, 225, 230, a), anchor="mm")
                img.paste(layer, (0, 0), layer)
            elif kind in ("A", "A!", "A~"):
                f = self.fa_big if kind == "A!" else self.fa
                d.text((self.cx, self.ya), ko, font=f, fill=(255, 255, 255), anchor="mm",
                       stroke_width=3, stroke_fill=(0, 0, 0))
            elif kind == "B":
                d.text((self.cx, self.yb), ko, font=self.fb, fill=(245, 214, 58), anchor="mm",
                       stroke_width=2, stroke_fill=(0, 0, 0))
                d.text((self.cx, self.yen), en, font=self.fen, fill=(235, 235, 235), anchor="mm",
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


# ---------------------------------------------------------------- 기계음 목소리
# 한글을 음절로 쪼개서 모음마다 포먼트(공명 주파수)를 걸고, 비트를 깎아 레트로 게임 NPC처럼 만든다.
VOWEL_F = {"a": (800, 1300, 2600), "e": (550, 1900, 2600), "eo": (600, 1000, 2500), "o": (450, 800, 2400),
           "u": (350, 850, 2300), "eu": (380, 1450, 2400), "i": (300, 2300, 3000)}
# 중성 21개 -> (시작 모음, 끝 모음). 이중모음은 시작 모음에서 미끄러진다
JUNG = [("a", "a"), ("e", "e"), ("i", "a"), ("i", "e"), ("eo", "eo"), ("e", "e"), ("i", "eo"), ("i", "e"),
        ("o", "o"), ("u", "a"), ("u", "e"), ("u", "e"), ("i", "o"), ("u", "u"), ("u", "eo"), ("u", "e"),
        ("u", "i"), ("i", "u"), ("eu", "eu"), ("eu", "i"), ("i", "i")]
PLOSIVE = {0, 1, 3, 4, 7, 8, 15, 16, 17}
FRIC = {9, 10, 12, 13, 14}
NASAL_CHO = {2, 6}
NASAL_JONG = {4, 16, 21}
VOICES = {
    #      기본 음높이, 음절 길이, 샘플레이트 깎기, 비트, 대사 음량(dB RMS)
    "A": dict(f0=205, syl=0.085, sr=11025, bits=6, gain=-17, fall=0.06, jitter=0.10),
    "A!": dict(f0=185, syl=0.115, sr=11025, bits=6, gain=-15, fall=0.10, jitter=0.06),
    "A~": dict(f0=170, syl=0.135, sr=8000, bits=6, gain=-17, fall=0.18, jitter=0.22),
    "B": dict(f0=92, syl=0.15, sr=8000, bits=5, gain=-18, fall=0.16, jitter=0.03),
}


def _resonate(x, f, bw):
    lo, hi = max(40, f - bw), min(SR / 2 - 100, f + bw)
    b, a = butter(2, [lo / (SR / 2), hi / (SR / 2)], btype="band")
    return lfilter(b, a, x)


def _tokens(text):
    """대사 -> [('syl', 초성, 중성, 종성) | ('pause', 초)]"""
    text = text.replace("[웃음]", "흐흐흐").replace("...", "…")
    text = re.sub(r"\[[^\]]*\]", "", text)
    out = []
    digits = {"0": "영", "1": "일", "2": "이", "3": "삼", "4": "사", "5": "오", "6": "육", "7": "칠", "8": "팔", "9": "구"}
    for ch in text:
        ch = digits.get(ch, ch)
        o = ord(ch)
        if 0xAC00 <= o <= 0xD7A3:
            c = o - 0xAC00
            out.append(("syl", c // 588, (c % 588) // 28, c % 28))
        elif ch == "…":
            out.append(("pause", 0.32))
        elif ch in ".?!":
            out.append(("pause", 0.18))
        elif ch == ",":
            out.append(("pause", 0.12))
        elif ch == " ":
            out.append(("pause", 0.05))
    while out and out[-1][0] == "pause":
        out.pop()
    while out and out[0][0] == "pause":
        out.pop(0)
    return out


def speak(text, kind, avail, rng):
    v = VOICES[kind]
    toks = _tokens(text)
    nsyl = sum(1 for tk in toks if tk[0] == "syl")
    if nsyl == 0:
        return np.zeros(1, np.float32)
    need = nsyl * v["syl"] + sum(tk[1] for tk in toks if tk[0] == "pause")
    k = min(1.0, max(0.3, avail - 0.15) / need)  # 자막 시간 안에 들어가도록 압축
    question = text.rstrip().endswith("?")
    segs = []
    si = 0
    for tk in toks:
        if tk[0] == "pause":
            segs.append(np.zeros(int(tk[1] * k * SR), np.float32))
            continue
        _, cho, jung, jong = tk
        si += 1
        L = int(v["syl"] * k * SR * (0.8 if jong else 1.0) * rng.uniform(0.9, 1.15))
        tt = np.arange(L) / SR
        # 음높이: 문장 끝으로 갈수록 내려가고, 해설의 질문은 끝을 올린다
        prog = si / nsyl
        f0 = v["f0"] * (1 - v["fall"] * prog) * (1 + v["jitter"] * rng.uniform(-1, 1))
        if question and kind != "B" and si >= nsyl - 1:
            f0 *= 1.25 + 0.15 * (si == nsyl)
        f0 = 2 ** (np.round(12 * np.log2(f0 / 55)) / 12) * 55   # 반음 단위로 끊어서 기계 느낌
        phase = np.cumsum(np.full(L, f0 / SR))
        src = 2 * (phase % 1.0) - 1                              # 톱니파 성대
        start, end = JUNG[jung]
        h = len(src) // 2
        voiced = np.zeros(L)
        for part, vw in ((slice(0, h), start), (slice(h, L), end)):
            f1, f2, f3 = VOWEL_F[vw]
            s = src[part]
            voiced[part] = _resonate(s, f1, 90) + 0.7 * _resonate(s, f2, 140) + 0.25 * _resonate(s, f3, 200)
        env = np.minimum(1, tt / 0.012) * np.minimum(1, (L / SR - tt) / 0.02)
        syl = voiced * env
        # 초성
        if cho in PLOSIVE:
            b = int(0.012 * SR)
            burst = butter_f(rng.standard_normal(b), 2000, "high") * np.exp(-np.arange(b) / (0.003 * SR))
            syl[:b] = syl[:b] * 0.2 + burst * 0.6
        elif cho in FRIC:
            b = int(0.04 * SR)
            hiss = butter_f(rng.standard_normal(b), 3800, "high") * 0.35
            syl = np.concatenate([hiss, syl])
        elif cho == 18:
            b = int(0.03 * SR)
            syl = np.concatenate([butter_f(rng.standard_normal(b), 1200, "high") * 0.2, syl])
        elif cho in NASAL_CHO:
            b = int(0.03 * SR)
            syl = np.concatenate([np.sin(2 * np.pi * f0 * np.arange(b) / SR) * 0.3, syl])
        # 종성 비음은 웅 하고 끌기
        if jong in NASAL_JONG:
            b = int(0.035 * SR)
            ph = np.cumsum(np.full(b, f0 / SR))
            syl = np.concatenate([syl, butter_f(2 * (ph % 1) - 1, 400) * 0.6 * np.linspace(1, 0, b)])
        segs.append(syl.astype(np.float32))
    y = np.concatenate(segs)
    y /= np.max(np.abs(y)) + 1e-6
    # 기계음 처리: 샘플레이트 깎기 + 비트 깎기
    hold = max(1, int(SR / v["sr"]))
    y = np.repeat(y[::hold], hold)[: len(y)]
    q = 2 ** (v["bits"] - 1)
    y = np.round(y * q) / q
    if kind == "B":   # 지친 NPC: 낮은 링모듈레이션 + 울림
        tt = np.arange(len(y)) / SR
        y = y * (0.75 + 0.25 * np.sin(2 * np.pi * 31 * tt))
        y = butter_f(y, 2600)
        d = int(0.11 * SR)
        y = np.concatenate([y, np.zeros(d * 3)])
        for i in (1, 2, 3):
            y[d * i:] += y[: len(y) - d * i] * (0.3 ** i)
    elif kind == "A~":  # 취해서 웅얼: 음이 출렁이고 먹먹하게
        tt = np.arange(len(y)) / SR
        y = y * (0.8 + 0.2 * np.sin(2 * np.pi * 5.5 * tt))
        y = butter_f(y, 2200)
    else:
        y = butter_f(y, 4500)
    rms = np.sqrt(np.mean(y[: len(y) - (d * 3 if kind == "B" else 0)] ** 2)) + 1e-6
    return (y * 10 ** (v["gain"] / 20) / rms).astype(np.float32)


def voice_track(lines, n):
    rng = np.random.default_rng(5)
    voice = np.zeros(n, np.float32)
    duck = np.zeros(n, np.float32)
    for t0, t1, kind, ko, _ in lines:
        if kind not in VOICES:
            continue
        y = speak(ko, kind, t1 - t0, rng)
        s = int((t0 + 0.05) * SR)
        e = min(n, s + len(y))
        voice[s:e] += y[: e - s]
        duck[max(0, s - 2000):e] = 1
    k = int(0.6 * SR)  # 0.6초에 걸쳐 부드럽게 줄였다가 돌아오게
    duck = fftconvolve(duck, np.hanning(k) / np.hanning(k).sum(), mode="same").astype(np.float32)
    return voice, duck


def reverb(x, secs=3.0, wet=0.35, seed=4):
    rng = np.random.default_rng(seed)
    L = int(secs * SR)
    ir = rng.standard_normal(L) * np.exp(-np.arange(L) / (secs * SR / 6))
    ir = butter_f(ir, 3000)
    ir /= np.sqrt((ir ** 2).sum())
    return x * (1 - wet) + fftconvolve(x, ir)[: len(x)].astype(np.float32) * wet * 1.5


def gloom_music(n, t, rng):
    """음침한 배경음: 바닥에 깔리는 저음 드론, 숨 쉬는 듯한 단조 패드, 띄엄띄엄 떨어지는 피아노, 심장 박동 같은 저음."""
    drone = (np.sin(2 * np.pi * 41.2 * t) + 0.6 * np.sin(2 * np.pi * 61.7 * t + np.sin(t * 0.3))) * 0.06
    drone *= 0.75 + 0.25 * np.sin(2 * np.pi * t / 9.0)
    # Em - C - Am - B (각 7.5초)
    pad = chord_pad(n, [[82.4, 164.8, 196, 246.9], [65.4, 130.8, 196, 164.8], [55, 110, 130.8, 164.8],
                        [61.7, 123.5, 185, 155.6]], 7.5, 1.0, 8)
    pad = butter_f(pad, 900) * 0.55
    # 피아노 비슷한 종소리: 낮은 음역에서 드문드문
    notes_t, notes_f = [], []
    seq = [329.6, 246.9, 196, 246.9, 261.6, 196, 164.8, 196, 220, 164.8, 130.8, 164.8, 185, 155.6, 123.5, 155.6]
    for i, f in enumerate(seq * 2):
        tm = 1.0 + i * 1.875 + rng.uniform(-0.05, 0.05)
        if rng.random() < 0.8:
            notes_t.append(tm)
            notes_f.append(f)
    piano = bell(n, notes_t, notes_f, 0.06)
    # 심장 박동 (쿵… 쿵)
    beat = np.zeros(n, np.float32)
    L = int(0.25 * SR)
    tt = np.arange(L) / SR
    thump = np.sin(2 * np.pi * (55 - 25 * tt / 0.25) * tt) * np.exp(-tt * 18)
    for bt in np.arange(2.0, n / SR, 1.6):
        for off, g in ((0, 0.12), (0.28, 0.07)):
            s = int((bt + off) * SR)
            if s + L < n:
                beat[s:s + L] += thump * g
    return reverb(drone + pad + piano, 3.5, 0.45) + beat


def synth_audio(path, dur, lines=(), music="ep01"):
    n = int(dur * SR)
    if music == "gloom":
        return synth_gloom(path, n, lines)
    rng = np.random.default_rng(99)
    t = np.arange(n) / SR
    white = rng.standard_normal(n).astype(np.float32)
    mix = np.zeros(n, np.float32)
    sc = {name: (s0, s1) for s0, s1, name, _ in SCENES}

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
    roof_music = butter_f(pad, 1800) * 0.5 + bell(n, melody_t, melody_f, 0.035)
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

    # 대사가 나올 때 배경음을 살짝 낮추고 기계음 목소리를 얹는다
    voice, duck = voice_track(lines, n)
    mix = mix * (1 - 0.5 * duck) + voice

    write_wav(path, mix)


def synth_gloom(path, n, lines):
    rng = np.random.default_rng(77)
    t = np.arange(n) / SR
    white = rng.standard_normal(n).astype(np.float32)
    sc = {name: (s0, s1) for s0, s1, name, _ in SCENES}
    rain_ = butter_f(butter_f(white, 400, "high"), 5000) * 0.06
    brown = butter_f(np.cumsum(white) / 300, 0.5, "high")
    wind = butter_f(brown, 400) * 0.05
    amb = (rain_ + wind) * 0.8
    if "taxi" in sc:   # 택시 안: 비 대신 엔진 소리
        e = env_scene(n, *sc["taxi"], 1.0)
        rumble = butter_f(white, 110) * 0.7 + np.sin(2 * np.pi * 38 * t) * 0.03
        amb = amb * (1 - e * 0.7) + rumble * e
    music = gloom_music(n, t, rng) * 0.4
    offs = {name: off for _, _, name, off in SCENES}
    if "soju" in sc:   # 소주: 잔 부딪는 소리, 꿀꺽, 그리고 취하면서 소리가 먹먹해진다
        s0 = sc["soju"][0] - offs["soju"]
        amb = amb + bell(n, [s0 + Soju.DRINK[0] - 0.4], [2350], 0.05) + bell(n, [s0 + Soju.DRINK[0] - 0.33], [3120], 0.03)
        g = int((s0 + 5.0) * SR)
        L = int(0.18 * SR)
        tt = np.arange(L) / SR
        amb[g:g + L] += (np.sin(2 * np.pi * (180 - 300 * tt) * tt) * np.exp(-tt * 20) * 0.12).astype(np.float32)
    if "road" in sc:   # 비틀대는 밤 도로: 택시가 다가오는 소리
        r0 = sc["road"][0] - offs["road"]
        approach = smoothstep(r0 + 5.5, r0 + 12.5, t) * env_scene(n, *sc["road"], 0.6)
        amb = amb + (butter_f(white, 180) * 0.6 + np.sin(2 * np.pi * 45 * t) * 0.04) * approach
    drunk_w = np.zeros(n, np.float32)
    for nm in ("soju", "road"):
        if nm in sc:
            drunk_w += env_scene(n, *sc[nm], 1.0)
    drunk_w *= 0.65
    music = music * (1 - drunk_w) + butter_f(music, 500) * drunk_w
    amb = amb * (1 - drunk_w) + butter_f(amb, 900) * drunk_w
    fade = np.minimum(1, t / 1.5) * np.minimum(1, (n / SR - t) / 2.5)
    voice, duck = voice_track(lines, n)
    mix = (music * (1 - 0.35 * duck) + amb * (1 - 0.5 * duck)) * fade + voice
    write_wav(path, mix)


def write_wav(path, mix):
    mix = np.tanh(mix * 1.4) * 0.8
    pcm = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ================================================================ 렌더
def scene_at(t):
    for s0, s1, name, off in SCENES:
        if s0 <= t < s1:
            return name, t - s0 + off, s0, s1
    s0, s1, name, off = SCENES[-1]
    return name, t - s0 + off, s0, s1


def render(out, episode="ep01", start=0.0, end=None, still=None, audio_only=False):
    ep = use_episode(episode)
    end = DURATION if end is None else end
    lines = parse_script(os.path.join(HERE, "script", ep["script"]))
    reel = ep["layout"] == "reel"
    subs = Subs(ep["layout"])
    fw, fh = (RW, RH) if reel else (OW, OH)
    objs = {"room": Room(), "street": Street(), "store": Store(), "roof": Roof(), "road": Road(), "taxi": Taxi()}
    objs["soju"] = Soju(objs["store"])
    drunk_curve = ep.get("drunk")
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
        if drunk_curve:
            xs, ks = zip(*drunk_curve)
            a = drunk(a, t, float(np.interp(t, xs, ks)))
        ox, oy = int(round(PAD + dx)), int(round(PAD + dy))
        a = a[oy:oy + H, ox:ox + W]
        if name not in ("title", "end"):
            a = glow(a)
        a = a * VIGNETTE + np.random.default_rng(int(t * FPS)).normal(0, 5, (H, W, 1))
        fade = min(1.0, (t - s0) / 0.7, (s1 - t) / 0.7)
        a = a * max(0.0, fade)
        if reel:
            img = Image.new("RGB", (RW, RH), (0, 0, 0))
            img.paste(to_img(a).resize((W * RS, H * RS), Image.NEAREST), ((RW - W * RS) // 2, RY))
            hd = ImageDraw.Draw(img)
            hd.text((RW / 2, RY - 70), "확실한 건 없다", font=subs.fen_title, fill=(150, 150, 160), anchor="mm")
        else:
            img = to_img(a).resize((OW, OH), Image.NEAREST)
        subs.draw(img, lines, t)
        return img

    if still is not None:
        make(still).save(out)
        return

    wav = out + ".wav"
    synth_audio(wav, DURATION, lines, ep["music"])
    if audio_only:
        os.replace(wav, out)
        return
    # 화면 노이즈 때문에 용량이 커서 grain 튜닝 + crf 29로 GitHub 한도(100MB) 아래로 맞춘다
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{fw}x{fh}",
           "-r", str(FPS), "-i", "-", "-ss", str(start), "-t", str(end - start), "-i", wav,
           "-c:v", "libx264", "-preset", "slow", "-crf", "29", "-tune", "grain", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-shortest", out]
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
    ap.add_argument("--episode", default="ep01", choices=sorted(EPISODES))
    ap.add_argument("--out")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float)
    ap.add_argument("--still", type=float, help="이 시각의 한 프레임만 PNG로 저장")
    ap.add_argument("--audio-only", action="store_true", help="사운드만 WAV로 저장")
    args = ap.parse_args()
    out = args.out or os.path.join(HERE, args.episode + ".mp4")
    render(out, args.episode, args.start, args.end, args.still, args.audio_only)
