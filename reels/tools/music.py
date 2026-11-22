#!/usr/bin/env python3
"""Music bed (optional). python3 tools/music.py <ep> [--force]  -> audio/<ep>/music.mp3
Makes one instrumental bed from the script's `music` prompt with ElevenLabs Music (model music_v1), episode length + 3 s.
ElevenLabs Music needs a paid plan. If it is not available the episode still renders: tools/mix.py works without music.
Your own track works too: save any instrumental as audio/<ep>/music.mp3 and skip this step."""
import sys, json, pathlib, time, urllib.request, urllib.error
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from env import api_key, explain
P = pathlib.Path(__file__).resolve().parents[1]
if len(sys.argv) < 2: raise SystemExit(__doc__)
EP = sys.argv[1]; out = P / 'audio' / EP / 'music.mp3'
if not (P / 'eps' / EP / 'timing.json').exists(): raise SystemExit(f'eps/{EP}/timing.json not found. Run the voices first (python3 tools/tts.py {EP}): the bed is cut to the episode length.')
if out.exists() and '--force' not in sys.argv: print(f'{out.relative_to(P)} already exists (use --force to make a new one)'); sys.exit(0)
S = json.loads((P / 'eps' / EP / 'script.json').read_text()); T = json.loads((P / 'eps' / EP / 'timing.json').read_text())
secs = max(10.0, min(300.0, round(T['dur'] + 3, 2)))
body = {'prompt': S['music'], 'music_length_ms': int(secs * 1000), 'model_id': 'music_v1', 'force_instrumental': True}
req = lambda: urllib.request.Request('https://api.elevenlabs.io/v1/music?output_format=mp3_44100_192', data=json.dumps(body).encode(), method='POST', headers={'xi-api-key': api_key(), 'Content-Type': 'application/json'})
last = ''
for a in range(4):
    try:
        with urllib.request.urlopen(req(), timeout=600) as r: raw = r.read(); ct = r.headers.get('Content-Type', '')
        if 'json' in ct: last = raw[:300].decode(errors='replace'); break
        out.parent.mkdir(parents=True, exist_ok=True); out.write_bytes(raw); print(f'{out.relative_to(P)}  {secs:.0f} s'); sys.exit(0)
    except urllib.error.HTTPError as e:
        last = f'HTTP {e.code} ' + e.read().decode(errors='replace')[:300]
        if e.code in (429, 500, 502, 503, 504): time.sleep(6 * (a + 1)); continue
        last = (explain(e.code, last) or '') + ' (' + last + ')'; break
    except Exception as e: last = repr(e); time.sleep(6 * (a + 1))
print(f'No music bed was made: {last}\nThe episode still renders without music. To add a bed later, save an instrumental as audio/{EP}/music.mp3 and run tools/make.sh again.')
sys.exit(2)
