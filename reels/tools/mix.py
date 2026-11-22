#!/usr/bin/env python3
"""Mix. python3 tools/mix.py <ep> -> audio/<ep>/mix.wav
Voices (-16 LUFS anchor) + music ducked under the voices + room tone + sound-effect cues, mastered to -14 LUFS / -1.5 dBTP.
audio/<ep>/music.mp3 is optional: without it the episode is mixed with voices, room tone and effects only."""
import json, subprocess, pathlib, sys
import numpy as np
P = pathlib.Path(__file__).resolve().parents[1]
if len(sys.argv) < 2: raise SystemExit(__doc__)
EP = sys.argv[1]; A = P / 'audio' / EP; SFX = P / 'audio' / 'sfx'
if not (A / 'vo.wav').exists(): raise SystemExit(f'audio/{EP}/vo.wav not found. Run the voices first (python3 tools/tts.py {EP}).')
T = json.loads((P / 'eps' / EP / 'timing.json').read_text()); SR = 48000; DUR = T['dur']; N = int(DUR * SR)
db = lambda x: 10 ** (x / 20)
def load(f, ch=2):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(f), '-ac', str(ch), '-ar', str(SR), '-f', 'f32le', '-'], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, ch).copy()
def fit(x, n): return x[:n] if len(x) >= n else np.concatenate([x, np.zeros((n - len(x), x.shape[1]), np.float32)])
def write(p, x): subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'f32le', '-ar', str(SR), '-ac', str(x.shape[1]), '-i', '-', '-c:a', 'pcm_s24le', str(p)], input=x.astype(np.float32).tobytes(), check=True)
def lufs(x):
    p = A / '_tmp.wav'; write(p, x)
    r = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(p), '-af', 'ebur128', '-f', 'null', '-'], capture_output=True, text=True).stderr
    return float([l for l in r.splitlines() if l.strip().startswith('I:')][-1].split()[1])

vo = fit(load(A / 'vo.wav'), N); vo *= db(-16 - lufs(vo))
def movavg(x, k):  # same result as np.convolve(x, np.ones(k) / k, 'same'), but O(N) instead of O(N*k) (was ~30 s per episode)
    c = np.concatenate([[0.0], np.cumsum(x, dtype=np.float64)]); n = len(x); i = np.arange(n)
    return (c[np.clip(i + (k - 1) // 2 + 1, 0, n)] - c[np.clip(i + (k - 1) // 2 - k + 1, 0, n)]) / k
m = np.abs(vo[:, 0]); env = movavg(m, int(.25 * SR)); env = np.clip(env / (np.percentile(env, 90) + 1e-9), 0, 1)
env = movavg(env, int(.4 * SR))
t = np.arange(N) / SR; MUSIC = (A / 'music.mp3').exists()
if MUSIC: mu = fit(load(A / 'music.mp3'), N); mu *= db(-26 - lufs(mu[: int(min(40, DUR) * SR)]))
else: mu = np.zeros((N, 2), np.float32); print(f'note: no audio/{EP}/music.mp3, mixing without a music bed')
mu *= (1 - .55 * env)[:, None]
mu *= np.interp(t, [0, 1.0, DUR - 3.0, DUR], [db(-5), 1, 1, db(-40)])[:, None]
am = load(SFX / 'amb.wav'); am = np.tile(am, (int(np.ceil(N / len(am))) + 1, 1))[:N]; am *= db(-37 - lufs(am[: 10 * SR]))
am *= np.interp(t, [0, .6, DUR - 1.2, DUR], [0, 1, 1, 0])[:, None]
# cues: Clawd hops → soft pop; typed screen events → typing; scene pops
LN = {l['id']: l for l in T['lines']}
cues = []
for l in T['lines']:
    if l.get('hop'): cues.append(('pop', l['s'] + l.get('hopAt', 0), -17))
    if l.get('c') == 'flap': cues.append(('chirp_up', l['s'], -15))
for e in T.get('uiEvents', []):
    at = e['t'] if 'line' not in e else LN[e['line']]['s'] + e.get('dt', 0)  # the engine also accepts events placed by absolute time `t`
    if e.get('typed'): cues.append(('typing', at, -13))
if T.get('hideF'): cues.append(('whoosh', LN[T['hideF']]['e'] + .1, -20))
fx = np.zeros((N, 2), np.float32)
for name, at, g in cues:
    x = load(SFX / f'{name}.wav'); x = x / (np.abs(x).max() + 1e-9) * db(g)
    if name == 'typing': x = x[: int(1.6 * SR)] * np.linspace(1, .2, min(len(x), int(1.6 * SR)))[:, None]
    i = int(max(0, at) * SR); n = min(len(x), N - i)
    if n > 0: fx[i:i + n] += x[:n]
mix = vo + mu + am + fx
write(A / 'premaster.wav', mix)
r = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(A / 'premaster.wav'), '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'], capture_output=True, text=True).stderr
js = json.loads(r[r.rindex('{'):r.rindex('}') + 1])
af = f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={js['input_i']}:measured_TP={js['input_tp']}:measured_LRA={js['input_lra']}:measured_thresh={js['input_thresh']}:offset={js['target_offset']}:linear=true"
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(A / 'premaster.wav'), '-af', af, '-ar', '48000', '-c:a', 'pcm_s24le', str(A / 'mix.wav')], check=True)
(A / '_tmp.wav').unlink(missing_ok=True)
r = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(A / 'mix.wav'), '-af', 'ebur128=peak=true', '-f', 'null', '-'], capture_output=True, text=True).stderr
print(EP, ' | '.join(l.strip() for l in r.splitlines()[-12:] if l.strip().startswith(('I:', 'Peak:'))), '| cues', len(cues))
