"""Synthesize the 30s soundtrack: school bell, light BGM, voice blips, stings. Writes a 16-bit WAV."""
import sys, wave
import numpy as np

SR = 44100
DUR = 30.0
N = int(SR * DUR)
out = np.zeros(N)
rng = np.random.default_rng(1)

def t_(d): return np.arange(int(SR * d)) / SR
def hz(n): return 440.0 * 2 ** ((n - 69) / 12)
def add(at, sig, gain=1.0):
    i = int(at * SR); j = min(N, i + len(sig))
    if i < N: out[i:j] += sig[: j - i] * gain

def bell(f, d=1.6):
    t = t_(d)
    s = sum(a * np.sin(2 * np.pi * f * r * t) * np.exp(-t * k) for r, a, k in [(1, 1, 2.2), (2.76, .4, 4), (5.4, .2, 6), (0.5, .3, 1.5)])
    return s * np.minimum(1, t * 200)

def pluck(f, d=0.5):
    t = t_(d)
    return (np.sin(2 * np.pi * f * t) + .3 * np.sin(4 * np.pi * f * t)) * np.exp(-t * 7) * np.minimum(1, t * 300)

def pad(f, d):
    t = t_(d)
    env = np.minimum(1, t / .3) * np.minimum(1, (d - t) / .3)
    return sum(np.sin(2 * np.pi * f * m * t + m) for m in (1, 1.005, 2.0)) / 3 * env

# school bell: 딩동댕동 (E5 C5 D5 G4)
for i, n in enumerate([76, 72, 74, 67]):
    add(0.15 + i * 0.5, bell(hz(n)), 0.22)

# BGM 2.6s-27.5s: I-V-vi-IV in C, 104 bpm, eighth-note plucks + pad
beat = 60 / 104
chords = [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]]
t0, tend, k = 2.6, 27.45, 0
while t0 < tend:
    ch = chords[k % 4]
    dark = 21.0 <= t0 < 25.2
    if dark: ch = [c - 1 for c in ch]  # menacing half-step down during the creepy line
    bar = beat * 4
    add(t0, pad(hz(ch[0] - 12), min(bar, tend - t0)), 0.05)
    for e in range(8):
        tt = t0 + e * beat / 2
        if tt >= tend: break
        n = ch[[0, 1, 2, 1, 2, 0, 1, 2][e]] + 12
        add(tt, pluck(hz(n)), 0.05 if not dark else 0.035)
        if e % 2 == 0: add(tt, pluck(hz(ch[0] - 24), .35), 0.07)
    t0 += bar; k += 1

# voice blips (one per revealed syllable)
LINES = [(2.8, 7.7, 'T', 30), (7.95, 11.7, 'H', 19), (11.95, 16.9, 'T', 29), (17.1, 20.9, 'M', 17),
         (21.1, 25.0, 'T', 31), (25.3, 27.5, 'O', 14), (28.35, 30.0, 'T', 14)]
VOICE = {'T': 150, 'H': 520, 'M': 360, 'O': 300}
for s, e, who, n in LINES:
    span = (e - s) * 0.6
    for i in range(n):
        f = VOICE[who] * (1 + 0.12 * rng.standard_normal() * 0.6)
        tt = t_(0.06)
        sig = np.sign(np.sin(2 * np.pi * f * tt)) * 0.35 + np.sin(2 * np.pi * f * tt)
        add(s + span * i / n, sig * np.exp(-tt * 40) * np.minimum(1, tt * 500), 0.05)

# chalk scratches while the board is written
for a, b in [(3.6, 6.4), (12.3, 13.6), (13.8, 15.4), (21.6, 23.4)]:
    d = b - a; tt = t_(d)
    noise = rng.standard_normal(len(tt))
    env = (0.5 + 0.5 * np.abs(np.sin(2 * np.pi * 3.2 * tt))) * np.minimum(1, tt / .05) * np.minimum(1, (d - tt) / .05)
    hp = np.diff(noise, prepend=0)
    add(a, hp * env, 0.02)

# whoosh / impact helpers
def whoosh(d=0.35, up=True):
    tt = t_(d); n = rng.standard_normal(len(tt))
    env = np.sin(np.pi * tt / d) ** 2
    return np.convolve(n, np.ones(8) / 8, 'same') * env
def hit(f=60, d=0.8):
    tt = t_(d); return np.sin(2 * np.pi * f * tt * (1 + 2 * np.exp(-tt * 20))) * np.exp(-tt * 4)

add(7.78, whoosh(), 0.15)            # cut to Hana
add(13.8, hit(70, .6), 0.35)         # "모든 접촉은" impact
add(21.0, hit(45, 1.6), 0.3)         # creepy turn
add(25.2, whoosh(.25), 0.18)         # Taeo wakes
# dissonant sting into the silence
tt = t_(1.0)
st = sum(np.sin(2 * np.pi * hz(n) * tt) for n in (71, 72, 77)) * np.exp(-tt * 3)
add(27.5, st, 0.12)
add(27.5, hit(55, .7), 0.3)
# glasses glint "ting"
tt = t_(1.2)
add(28.58, (np.sin(2 * np.pi * 2640 * tt) + .5 * np.sin(2 * np.pi * 3960 * tt)) * np.exp(-tt * 5), 0.12)
# ending sting
add(29.25, sum(pluck(hz(n), 0.8) for n in (48, 55, 63)), 0.25)

# master: fade in/out, normalize
fade = np.ones(N); fi = int(.3 * SR); fo = int(.4 * SR)
fade[:fi] = np.linspace(0, 1, fi); fade[-fo:] = np.linspace(1, 0, fo)
out *= fade
out = np.tanh(out / np.max(np.abs(out)) * 1.2) * 0.85
with wave.open(sys.argv[1], 'wb') as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((out * 32767).astype('<i2').tobytes())
