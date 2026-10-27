"""Synthesize an episode's 30s soundtrack: school bell, BGM, robotic formant voices, SFX.

Usage: python3 tools/soundtrack.py <ep> <out.wav>

Voices use the same approach as neyasno_anim: each Hangul syllable is split into
초성/중성/종성, a sawtooth "vocal cord" is filtered through the vowel's formants, then
sample-rate and bit depth are crushed for a retro machine sound. Each syllable is placed
in the same per-character slot the subtitles and mouths use, so everything stays in sync.
"""
import json, os, subprocess, sys, wave
import numpy as np
from scipy.signal import butter, fftconvolve, lfilter

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 44100
N = int(SR * 30.0)  # set per episode in main()
BLEEP = '(삐-)'


def load_episode(ep):
    js = os.path.join(HERE, '..', 'episodes.js')
    raw = subprocess.run(['node', '-e', f'process.stdout.write(JSON.stringify(require({json.dumps(js)})))'],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(raw)['EPISODES'][str(ep)]


def butter_f(x, f, kind='low'):
    b, a = butter(2, f / (SR / 2), btype=kind)
    return lfilter(b, a, x)


def resonate(x, f, bw):
    lo, hi = max(40, f - bw), min(SR / 2 - 100, f + bw)
    b, a = butter(2, [lo / (SR / 2), hi / (SR / 2)], btype='band')
    return lfilter(b, a, x)


def t_(d): return np.arange(int(SR * d)) / SR
def hz(n): return 440.0 * 2 ** ((n - 69) / 12)


# ---------------------------------------------------------------- 기계음 목소리
VOWEL_F = {'a': (800, 1300, 2600), 'e': (550, 1900, 2600), 'eo': (600, 1000, 2500), 'o': (450, 800, 2400),
           'u': (350, 850, 2300), 'eu': (380, 1450, 2400), 'i': (300, 2300, 3000)}
JUNG = [('a', 'a'), ('e', 'e'), ('i', 'a'), ('i', 'e'), ('eo', 'eo'), ('e', 'e'), ('i', 'eo'), ('i', 'e'),
        ('o', 'o'), ('u', 'a'), ('u', 'e'), ('u', 'e'), ('i', 'o'), ('u', 'u'), ('u', 'eo'), ('u', 'e'),
        ('u', 'i'), ('i', 'u'), ('eu', 'eu'), ('eu', 'i'), ('i', 'i')]
PLOSIVE = {0, 1, 3, 4, 7, 8, 15, 16, 17}
FRIC = {9, 10, 12, 13, 14}
NASAL_CHO = {2, 6}
NASAL_JONG = {4, 16, 21}
READ = {'0': '영', '1': '일', '2': '이', '3': '삼', '4': '사', '5': '오', '6': '육', '7': '칠', '8': '팔', '9': '구',
        'm': '엠', 'l': '엘', 'D': '디', 'N': '엔', 'A': '에', 'ㅆ': '씨', 'ㅃ': '빠', 'ㅂ': '바', 'ㅅ': '시'}
VOICES = {
    #        기본 음높이, 샘플레이트 깎기, 비트, 음량(dB RMS), 문장 끝 처짐, 음높이 흔들림, 떨림(민준), 링모듈(태오)
    '선생님': dict(f0=118, sr=11025, bits=6, gain=-15, fall=0.10, jitter=0.05, tremble=0, ring=0),
    '하나':   dict(f0=262, sr=11025, bits=6, gain=-16, fall=0.04, jitter=0.12, tremble=0, ring=0),
    '민준':   dict(f0=196, sr=11025, bits=6, gain=-17, fall=0.06, jitter=0.10, tremble=9, ring=0),
    '하나정색': dict(f0=175, sr=11025, bits=5, gain=-14, fall=0.18, jitter=0.02, tremble=0, ring=0),  # 죽은 눈 정색
    '반 애들': dict(f0=150, sr=11025, bits=5, gain=-13, fall=0.05, jitter=0.08, tremble=0, ring=0, chorus=(0.75, 1.0, 1.35)),  # 단체 고함
    '태오':   dict(f0=140, sr=8000,  bits=5, gain=-17, fall=0.14, jitter=0.04, tremble=0, ring=0.3),
}


def syllable(cho, jung, jong, f0, L, rng, tremble):
    tt = np.arange(L) / SR
    f = f0 * (1 + (0.04 * np.sin(2 * np.pi * tremble * tt) if tremble else 0))
    phase = np.cumsum(np.broadcast_to(f, (L,)) / SR)
    src = 2 * (phase % 1.0) - 1
    start, end = JUNG[jung]
    h = L // 2
    voiced = np.zeros(L)
    for part, vw in ((slice(0, h), start), (slice(h, L), end)):
        f1, f2, f3 = VOWEL_F[vw]
        s = src[part]
        voiced[part] = resonate(s, f1, 90) + 0.7 * resonate(s, f2, 140) + 0.25 * resonate(s, f3, 200)
    syl = voiced * np.minimum(1, tt / 0.012) * np.minimum(1, (L / SR - tt) / 0.02)
    if cho in PLOSIVE:
        b = min(L, int(0.012 * SR))
        syl[:b] = syl[:b] * 0.2 + butter_f(rng.standard_normal(b), 2000, 'high') * np.exp(-np.arange(b) / (0.003 * SR)) * 0.6
    elif cho in FRIC:
        b = min(L // 3, int(0.04 * SR))
        syl[:b] = syl[:b] * 0.3 + butter_f(rng.standard_normal(b), 3800, 'high') * 0.35
    elif cho == 18:
        b = min(L // 3, int(0.03 * SR))
        syl[:b] = syl[:b] * 0.4 + butter_f(rng.standard_normal(b), 1200, 'high') * 0.2
    elif cho in NASAL_CHO:
        b = min(L // 3, int(0.03 * SR))
        syl[:b] = syl[:b] * 0.4 + np.sin(2 * np.pi * f0 * np.arange(b) / SR) * 0.3
    if jong in NASAL_JONG:
        b = min(L // 3, int(0.035 * SR))
        ph = np.cumsum(np.full(b, f0 / SR))
        syl[-b:] = syl[-b:] * 0.3 + butter_f(2 * (ph % 1) - 1, 400) * 0.6 * np.linspace(1, 0, b)
    return syl


def speak_line(line, rng):
    """Returns (start_sample, audio) for one line; syllable i sits in character slot i."""
    v = VOICES[line.get('voice', line['who'])]
    text = line['text']
    span = (line['e'] - line['s']) * line.get('speak', 0.6)
    slot = span / len(text)
    b0 = text.find(BLEEP)
    bleep = range(b0, b0 + len(BLEEP)) if b0 >= 0 else range(0)
    spoken = [i for i, ch in enumerate(text) if i not in bleep and (0xAC00 <= ord(READ.get(ch, ch)) <= 0xD7A3)]
    question = text.rstrip().endswith('?')
    shout = '!!' in text or '?!' in text
    y = np.zeros(int((span + 0.4) * SR))
    for k, i in enumerate(spoken):
        c = ord(READ.get(text[i], text[i])) - 0xAC00
        cho, jung, jong = c // 588, (c % 588) // 28, c % 28
        prog = (k + 1) / len(spoken)
        f0 = v['f0'] * (1 - v['fall'] * prog) * (1 + v['jitter'] * rng.uniform(-1, 1))
        if shout: f0 *= 1.35
        if question and k >= len(spoken) - 2:
            f0 *= 1.22 + 0.15 * (k == len(spoken) - 1)
        f0 = 2 ** (np.round(12 * np.log2(f0 / 55)) / 12) * 55    # 반음 단위로 끊어서 기계 느낌
        L = int(max(0.06, slot * 0.95) * SR)
        s = int(i * slot * SR)
        seg = sum(syllable(cho, jung, jong, f0 * m, L, rng, v['tremble']) for m in v.get('chorus', (1.0,)))
        y[s:s + L] += seg[: len(y) - s]
    # 기계음 처리: 샘플레이트 깎기 + 비트 깎기
    y /= np.max(np.abs(y)) + 1e-6
    hold = max(1, int(SR / v['sr']))
    y = np.repeat(y[::hold], hold)[: len(y)]
    q = 2 ** (v['bits'] - 1)
    y = np.round(y * q) / q
    if v['ring']:
        tt = np.arange(len(y)) / SR
        y = y * (1 - v['ring'] + v['ring'] * np.sin(2 * np.pi * 31 * tt))
        y = butter_f(y, 2600)
    else:
        y = butter_f(y, 4500)
    active = y[np.abs(y) > 1e-4]
    rms = np.sqrt(np.mean(active ** 2)) + 1e-6 if len(active) else 1
    y = y * 10 ** ((v['gain'] + (3 if shout else 0)) / 20) / rms
    # 욕은 삐— 처리
    for i in bleep:
        s = int(i * slot * SR); L = int(slot * SR)
        tt = np.arange(L) / SR
        y[s:s + L] = np.sin(2 * np.pi * 1000 * tt) * 0.22
    return int(line['s'] * SR), y


def voice_track(lines):
    rng = np.random.default_rng(5)
    voice = np.zeros(N); duck = np.zeros(N)
    for line in lines:
        s, y = speak_line(line, rng)
        e = min(N, s + len(y))
        voice[s:e] += y[: e - s]
        duck[max(0, s - 2000):e] = 1
    k = int(0.5 * SR)
    duck = fftconvolve(duck, np.hanning(k) / np.hanning(k).sum(), mode='same')
    return voice, duck


# ---------------------------------------------------------------- music + sfx
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


def main(ep, path):
    global N
    E = load_episode(ep)
    N = int(SR * E.get('duration', 30))
    music = np.zeros(N); sfx = np.zeros(N)
    rng = np.random.default_rng(1)

    def add(buf, at, sig, gain=1.0):
        i = int(at * SR); j = min(N, i + len(sig))
        if i < N: buf[i:j] += sig[: j - i] * gain

    for i, n in enumerate([76, 72, 74, 67]):          # 딩동댕동
        add(sfx, 0.15 + i * 0.5, bell(hz(n)), 0.22)

    beat = 60 / E['bpm']
    chords = [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]]
    dark_at = E.get('darkAt', 21.0)
    t0, tend, k = 2.6, E.get('musicEnd', 27.45), 0
    while t0 < tend:
        ch = chords[k % 4]
        dark = dark_at <= t0 < 25.2
        if dark: ch = [c - 1 for c in ch]
        bar = beat * 4
        add(music, t0, pad(hz(ch[0] - 12), min(bar, tend - t0)), 0.05)
        for e in range(8):
            tt = t0 + e * beat / 2
            if tt >= tend: break
            add(music, tt, pluck(hz(ch[[0, 1, 2, 1, 2, 0, 1, 2][e]] + 12)), 0.05 if not dark else 0.035)
            if e % 2 == 0: add(music, tt, pluck(hz(ch[0] - 24), .35), 0.07)
        t0 += bar; k += 1

    for it in E['board']:                              # chalk scratches
        d = it['b'] - it['a']; tt = t_(d)
        env = (0.5 + 0.5 * np.abs(np.sin(2 * np.pi * 3.2 * tt))) * np.minimum(1, tt / .05) * np.minimum(1, (d - tt) / .05)
        add(sfx, it['a'], np.diff(rng.standard_normal(len(tt)), prepend=0) * env, 0.015)

    def whoosh(d=0.35):
        tt = t_(d)
        return np.convolve(rng.standard_normal(len(tt)), np.ones(8) / 8, 'same') * np.sin(np.pi * tt / d) ** 2

    def hit(f=60, d=0.8):
        tt = t_(d); return np.sin(2 * np.pi * f * tt * (1 + 2 * np.exp(-tt * 20))) * np.exp(-tt * 4)

    def stomps(a, b):
        out = np.zeros(int((b - a) * SR) + SR)
        tt = a
        while tt < b:
            d = t_(0.18)
            thump = np.sin(2 * np.pi * 85 * d * (1 + 3 * np.exp(-d * 40))) * np.exp(-d * 18)
            crack = butter_f(rng.standard_normal(len(d)), 1500, 'high') * np.exp(-d * 60) * 0.5
            i0 = int((tt - a) * SR); out[i0:i0 + len(d)] += thump + crack
            tt += rng.uniform(0.09, 0.2)
        return out

    def engine(a, b, pass_t):
        tt = t_(b - a); rel = tt - (pass_t - a)
        f = 95 * (1 + 0.6 * np.clip(tt / 0.4, 0, 1)) * np.where(rel < 0, 1.15, 0.85)   # rev up + doppler drop
        ph = np.cumsum(f / SR)
        saw = 2 * (ph % 1) - 1 + 0.5 * (2 * ((ph * 2) % 1) - 1)
        env = np.exp(-(rel / 0.45) ** 2) * 0.8 + 0.2
        env *= np.minimum(1, tt / 0.05) * np.minimum(1, (tt[-1] - tt) / 0.1)
        return butter_f(np.tanh(saw * 2), 1800) * env

    if 'sfx' in E:
        for ev in E['sfx']:
            k, g = ev['k'], ev['g']
            if k == 'whoosh': add(sfx, ev['t'], whoosh(), g)
            elif k == 'hit': add(sfx, ev['t'], hit(ev['f'], ev['d']), g)
            elif k == 'stomps': add(sfx, ev['a'], stomps(ev['a'], ev['b']), g)
            elif k == 'engine': add(sfx, ev['a'], engine(ev['a'], ev['b'], ev['pass']), g)
            elif k == 'crunch':
                d = t_(0.4)
                add(sfx, ev['t'], (butter_f(rng.standard_normal(len(d)), 800, 'high') * np.exp(-d * 14) + hit(50, .4)[:len(d)]), g)
            elif k == 'ting':
                d = t_(1.0); add(sfx, ev['t'], (np.sin(2 * np.pi * 2640 * d) + .5 * np.sin(2 * np.pi * 3960 * d)) * np.exp(-d * 5), g)
            elif k == 'endsting': add(sfx, ev['t'], sum(pluck(hz(n), 0.8) for n in (48, 55, 63)), g)
    else:
        add(sfx, 7.78, whoosh(), 0.15)
        add(sfx, 13.8, hit(70, .6), 0.35)
        add(sfx, dark_at, hit(45, 1.6), 0.3)
        add(sfx, 25.2, whoosh(.25), 0.18)
        tt = t_(1.0)
        add(sfx, 27.5, sum(np.sin(2 * np.pi * hz(n) * tt) for n in (71, 72, 77)) * np.exp(-tt * 3), 0.12)
        add(sfx, 27.5, hit(55, .7), 0.3)
        tt = t_(1.2)
        add(sfx, 28.58, (np.sin(2 * np.pi * 2640 * tt) + .5 * np.sin(2 * np.pi * 3960 * tt)) * np.exp(-tt * 5), 0.1)
        if E['finale'] == 'angry':
            add(sfx, 28.3, hit(40, 1.0), 0.45)            # 쾅
        add(sfx, 29.25, sum(pluck(hz(n), 0.8) for n in (48, 55, 63)), 0.2)
    if 'silence' in E:   # music cuts out (record scratch) and comes back
        a, b = E['silence']
        fade_out = E.get('silenceFade', False)
        gate = np.ones(N); ia, ib = int(a * SR), int(b * SR); r = int(0.03 * SR)
        ro = int(1.0 * SR)
        gate[ia:ib] = 0; gate[ib:ib + r] = np.linspace(0, 1, r)
        if fade_out: gate[ia:ia + ro] = np.linspace(1, 0, ro)
        else: gate[ia - r:ia] = np.linspace(1, 0, r)
        music *= gate
        if not fade_out:
            tt = t_(0.35)
            scratch = np.sin(2 * np.pi * np.cumsum(np.linspace(900, 120, len(tt))) / SR) * np.exp(-tt * 6)
            add(sfx, a - 0.05, scratch + butter_f(rng.standard_normal(len(tt)), 2000, 'high') * 0.3 * np.exp(-tt * 10), 0.25)
    if 'dip' in E:   # sound effects dim along with the picture's fade to dark
        a, m, b = E['dip']
        tt = np.arange(N) / SR
        sfx *= 1 - np.where(tt < m, np.clip((tt - a) / (m - a), 0, 1), np.clip(1 - (tt - m) / (b - m), 0, 1))

    voice, duck = voice_track(E['lines'])
    out = music * (1 - 0.55 * duck) + sfx + voice
    fade = np.ones(N); fi = int(.3 * SR); fo = int(.4 * SR); e30 = int(30 * SR)
    fade[:fi] = np.linspace(0, 1, fi); fade[e30 - fo:e30] = np.linspace(1, 0, fo); fade[e30:] = 0
    out = np.tanh(out * fade * 1.6) * 0.85
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(out, -1, 1) * 32767).astype('<i2').tobytes())


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
