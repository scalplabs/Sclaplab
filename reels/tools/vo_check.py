#!/usr/bin/env python3
"""Voice check (optional). python3 tools/vo_check.py <ep>
Sends audio/<ep>/vo.wav to ElevenLabs speech-to-text and prints every line whose heard words differ from the script.
Numbers heard as digits, "a.m." and spelling differences are noise: judge by eye. Fix a real miss with
python3 tools/tts.py <ep> --force <line id>  (or add 'seed': 1 to that line to re-roll it). Writes audio/<ep>/scribe.json."""
import sys, json, re, subprocess, pathlib, urllib.request, uuid, difflib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from env import api_key
P = pathlib.Path(__file__).resolve().parents[1]
if len(sys.argv) < 2: raise SystemExit(__doc__)
EP = sys.argv[1]
if not (P / 'audio' / EP / 'vo.wav').exists(): raise SystemExit(f'audio/{EP}/vo.wav not found. Run the voices first (python3 tools/tts.py {EP}).')
KEY = api_key(); A = P / 'audio' / EP; T = json.loads((P / 'eps' / EP / 'timing.json').read_text())
mp3 = A / 'vo_check.mp3'
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(A / 'vo.wav'), '-ac', '1', '-b:a', '96k', str(mp3)], check=True)
b = uuid.uuid4().hex
part = lambda k, v: f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
body = part('model_id', 'scribe_v1') + part('language_code', 'ko') + part('tag_audio_events', 'false') + part('timestamps_granularity', 'word')
body += f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="vo.mp3"\r\nContent-Type: audio/mpeg\r\n\r\n'.encode() + mp3.read_bytes() + f'\r\n--{b}--\r\n'.encode()
req = urllib.request.Request('https://api.elevenlabs.io/v1/speech-to-text', data=body, method='POST', headers={'xi-api-key': KEY, 'Content-Type': f'multipart/form-data; boundary={b}'})
try: d = json.loads(urllib.request.urlopen(req, timeout=300).read())
except Exception as e:
    msg = e.read().decode(errors='replace')[:300] if hasattr(e, 'read') else str(e)
    raise SystemExit(f'voice check skipped (the episode still works without it): {msg}')
(A / 'scribe.json').write_text(json.dumps(d))
norm = lambda s: re.sub(r"[^a-z0-9'\uac00-\ud7a3 ]+", ' ', s.lower().replace('’', "'")).split()
L = T['lines']; heard = {l['id']: [] for l in L}
for w in d.get('words', []):
    if w.get('type', 'word') != 'word': continue
    m = (w['start'] + w['end']) / 2
    l = min(L, key=lambda l: 0 if l['s'] - .1 <= m <= l['e'] + .1 else min(abs(m - l['s']), abs(m - l['e'])))
    heard[l['id']].append(w['text'])
bad = 0
for l in L:
    a, h = norm(l['text']), norm(' '.join(heard[l['id']])); r = difflib.SequenceMatcher(None, a, h).ratio()
    if r < 0.9:
        bad += 1; print(f"L{l['id']:02d} {l['who']} {r:.2f} | want: {' '.join(a)} | heard: {' '.join(h)}")
print(f'{EP}: {len(L)} lines, {bad} differ')
