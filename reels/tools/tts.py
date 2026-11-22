#!/usr/bin/env python3
"""Voices. One ElevenLabs request per line -> eps/<ep>/vo/*.mp3, eps/<ep>/timing.json and audio/<ep>/vo.wav.
usage: python3 tools/tts.py <ep> [--force 3,7]
Each line is cached by (text, voice, seed), so a second run only pays for the lines you changed.
The API key, the two voice IDs and the model come from .env (see tools/env.py)."""
import sys, json, re, base64, hashlib, subprocess, pathlib, urllib.request, urllib.error, time
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from env import ENV, api_key, voice_id, explain
P = pathlib.Path(__file__).resolve().parents[1]
if len(sys.argv) < 2: raise SystemExit(__doc__)
EP = sys.argv[1]; D = P / 'eps' / EP
if not (D / 'script.json').exists(): raise SystemExit(f'eps/{EP}/script.json not found. Write the script first (python3 scripts/{EP}.py).')
KEY, MODEL = api_key(), ENV['ELEVENLABS_MODEL_ID']; BILLED = [0]
STAB = {'F': 0.38, 'C': 0.5}; A = P / 'audio' / EP; (D / 'vo').mkdir(exist_ok=True, parents=True); A.mkdir(exist_ok=True, parents=True)
S = json.loads((D / 'script.json').read_text())
force = set(sys.argv[sys.argv.index('--force') + 1].split(',')) if '--force' in sys.argv else set()
SR = 48000; FPS = 30
strip = lambda t: re.sub(r'\s+', ' ', re.sub(r'\[[^\]]*\]', '', t)).strip()

def tts(line, prev, nxt):
    v = {'voice_id': voice_id(line['who']), 'stability': S.get('voices', {}).get(line['who'], {}).get('stability', STAB[line['who']])}
    body = {'text': line['text'], 'model_id': MODEL, 'voice_settings': {'stability': v['stability'], 'similarity_boost': 0.8, 'use_speaker_boost': True}, 'seed': 2000 + line['id'] + line.get('seed', 0)}
    if prev: body['previous_text'] = prev
    if nxt: body['next_text'] = nxt
    h = hashlib.sha1(json.dumps([body, v['voice_id']]).encode()).hexdigest()[:10]
    out = D / 'vo' / f"L{line['id']:02d}_{h}.mp3"
    if out.exists() and str(line['id']) not in force: return out
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{v['voice_id']}/with-timestamps?output_format=mp3_44100_192"
    for a in range(5):
        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode(), method='POST', headers={'xi-api-key': KEY, 'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=300) as r: d = json.loads(r.read())
            BILLED[0] += len(body['text']); out.write_bytes(base64.b64decode(d['audio_base64'])); (out.parent / (out.name + '.align.json')).write_text(json.dumps(d.get('alignment')))
            return out
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors='replace')[:300]
            if 'previous_text' in msg or 'next_text' in msg: body.pop('previous_text', None); body.pop('next_text', None); continue
            why = explain(e.code, msg)
            if why: raise SystemExit(f'Voice for line {line["id"]} failed: {why}\n  (ElevenLabs said: HTTP {e.code} {msg})')
            print('HTTP', e.code, msg); time.sleep(5 * (a + 1))
        except Exception as e: print('ERR', e); time.sleep(5 * (a + 1))
    raise SystemExit('tts failed ' + str(line['id']))

SPEED = float(S.get('speed', 1.0))  # playback speed of every line (atempo, no new API call)
def load(mp3):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(mp3)] + (['-af', f'atempo={SPEED}'] if SPEED != 1.0 else []) + ['-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()

lines = S['lines']; clips = []
for i, l in enumerate(lines):
    prev = strip(lines[i - 1]['text']) if i else None; nxt = strip(lines[i + 1]['text']) if i + 1 < len(lines) else None
    mp3 = tts(l, prev, nxt); x = load(mp3)
    al = json.loads((mp3.parent / (mp3.name + '.align.json')).read_text() or 'null')
    env = np.convolve(np.abs(x), np.ones(480) / 480, 'same'); thr = max(1e-3, env.max() * 0.02)
    idx = np.where(env > thr)[0]; a = max(0, idx[0] - int(.03 * SR)); b = min(len(x), idx[-1] + int(.07 * SR))
    clips.append(dict(l=l, x=x[a:b], off=a / SR, al=al))
    print(f"L{l['id']:02d} {l['who']} {len(x[a:b]) / SR:5.2f}s  {strip(l['text'])}")

t = S.get('lead', 0.18); tl = []
for c in clips:
    l = c['l']; s = t + l.get('shift', 0); e = s + len(c['x']) / SR; words = []; al = c['al']
    if al:
        chars, st, en = al['characters'], [x / SPEED for x in al['character_start_times_seconds']], [x / SPEED for x in al['character_end_times_seconds']]; intag = False; cur = None
        for k, ch in enumerate(chars):
            if ch == '[': intag = True
            if intag:
                if ch == ']': intag = False
                if cur: words.append(cur); cur = None
                continue
            if ch.isspace():
                if cur: words.append(cur); cur = None
                continue
            if cur is None: cur = dict(w='', s=st[k] - c['off'] + s, e=en[k] - c['off'] + s)
            cur['w'] += ch; cur['e'] = en[k] - c['off'] + s
        if cur: words.append(cur)
    item = {k: v for k, v in l.items() if k not in ('text',)}
    item.update(text=strip(l['text']), s=round(s, 3), e=round(e, 3), words=words)
    tl.append(item); t = e + l.get('gap', .35)
dur = t + S.get('tail', 1.0)
N = int(dur * SR) + SR; stems = {k: np.zeros(N, np.float32) for k in ('F', 'C')}
for c, L in zip(clips, tl):
    i0 = int(L['s'] * SR); stems[L['who']][i0:i0 + len(c['x'])] += c['x']
mouth = {}
for k, y in stems.items():
    hop = SR // FPS; n = int(dur * FPS) + 2; r = np.zeros(n)
    for f in range(n):
        seg = y[f * hop: f * hop + hop]; r[f] = np.sqrt(np.mean(seg ** 2)) if len(seg) else 0
    r = r / (np.percentile(r[r > 1e-4], 95) if (r > 1e-4).any() else 1)
    mouth[k] = [round(float(min(1.2, v)), 3) for v in r]
mix = sum(stems.values())[:int(dur * SR)]
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'f32le', '-ar', str(SR), '-ac', '1', '-i', '-', '-c:a', 'pcm_s16le', str(A / 'vo.wav')], input=mix.tobytes(), check=True)
T = {k: v for k, v in S.items() if k not in ('lines', 'voices')}
T.update(dur=round(dur, 3), fps=FPS, lines=tl, mouth=mouth)
(D / 'timing.json').write_text(json.dumps(T))
total = sum(len(l['text']) for l in lines)
(D / 'tts_usage.json').write_text(json.dumps({'script_characters': total, 'characters_sent_this_run': BILLED[0], 'model': MODEL}))
print(f'{EP}: dur {dur:.2f}s  lines {len(tl)}  words {sum(len(l["text"].split()) for l in tl)}  characters {total} (sent to ElevenLabs this run: {BILLED[0]})')
