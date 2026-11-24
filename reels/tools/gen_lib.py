#!/usr/bin/env python3
"""Script helper. An episode is one call:  build('NN_name', 'Title', [lines], ui=..., events=..., end='cut'|'fade', music='cozy')
It writes eps/NN_name/script.json, which every other tool reads.

Line  = (who, '[emotion tag] spoken text', gap_after_seconds[, 'p'][, {overrides}])
  who       'F' = Pixel (the founder), 'C' = Claude (the robot)
  'p'       marks a punchline: Claude hops and looks pleased
  overrides f / fe (Pixel pose / face), c / ce (Claude pose / eyes), shot, split, hop, hopAt, noBeat, extra, cap, seed
Poses and faces are guessed from the emotion tag, so most lines need no overrides. Names are checked here, so a typo fails now and not in the render."""
import json, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from env import ENV
P = pathlib.Path(__file__).resolve().parents[1]
# Voice IDs are NOT stored in the script: tools/tts.py takes them from .env (PIXEL_VOICE_ID, CLAUDE_VOICE_ID).
VOICES = {"F": {"name": "Pixel", "stability": 0.38}, "C": {"name": "Claude", "stability": 0.5}}
NV = ', instrumental only, no vocals, leaves space for dialogue'
MUSIC = {
    'cozy': 'Warm late-night lo-fi underscore for a quiet comedy sketch: soft felt piano, mellow Rhodes chords, gentle upright bass, light brushed percussion, 78 bpm, cozy and wry' + NV,
    'sneaky': 'Playful sneaky comedy underscore: pizzicato strings, soft marimba and a light lo-fi beat, 92 bpm, mischievous and deadpan, sparse' + NV,
    'tense': 'Tense but funny late-night underscore: muted synth pulse, soft ticking percussion and low warm pads that resolve into gentle piano in the second half, 96 bpm' + NV,
    'tender': 'Tender minimal felt piano with warm analog pads, slow 66 bpm, intimate late-night mood, a little bittersweet, soft tape hiss, no drums' + NV,
    'bounce': 'Light bouncy lo-fi groove: plucky muted guitar, soft electric piano stabs, lazy swung drums, 86 bpm, dry and witty, warm vinyl texture' + NV,
}
F_POSES = 'idle talk listen shrug chin facepalm point phone fist slump up lean away duck'.split()
F_FACES = 'norm worry shock sad laugh smirk deadpan annoyed shut'.split()
C_POSES = 'idle talk listen lean tilt flap hunch proud away sad point'.split()
C_EYES = 'norm wide squint flat sad happy up'.split()
SHOTS = 'F Fx Fp Flow Fm C Cx Clow Cm otsF otsC two twoLow wide hi ext duck scr'.split()
KEYS = 'f fe c ce shot split hop hopAt noBeat extra cap seed shift lead emo emo_int'.split()

def infer(who, text):
    tags = ' '.join(re.findall(r'\[([^\]]*)\]', text)).lower(); d = {}
    has = lambda *k: any(x in tags for x in k)
    if who == 'F':
        if has('panic', 'alarm', 'shock', 'horrif', 'startl', 'stunned', 'outrag', 'mortif'): d.update(fe='shock', f='shrug')
        elif has('defensive', 'offended', 'annoy', 'exasper', 'frustr', 'curt', 'dismiss'): d.update(fe='annoyed', f='point')
        elif has('pleading', 'desperate'): d.update(fe='worry', f='shrug')
        elif has('laugh'): d.update(fe='laugh', f='shrug')
        elif has('quiet', 'sad', 'defeat', 'resign', 'tired', 'exhaust', 'pained', 'deflat', 'small', 'moved'): d.update(fe='sad', f='slump')
        elif has('nervous', 'anxious', 'uneasy', 'wary', 'worried', 'uncertain', 'sheepish', 'caught', 'whisper', 'alarmed', 'suspicious'): d.update(fe='worry', f='lean')
        elif has('curious', 'confus', 'puzzled', 'thinking', 'slowly', 'dawning'): d.update(fe='worry', f='chin')
        elif has('elated', 'delight', 'happy', 'pleased', 'smil', 'warm', 'relie', 'bright', 'hopeful', 'grin', 'fond'): d.update(fe='smirk', f='up')
        else: d.update(fe='norm', f='talk')
    else:
        if has('bright', 'proud', 'warm', 'pleased', 'happy', 'excited'): d.update(ce='happy', c='proud')
        elif has('surprised', 'curious', 'wide', 'alarmed'): d.update(ce='wide', c='tilt')
        elif has('soft', 'gentl', 'quiet', 'sad', 'pause'): d.update(ce='sad', c='lean')
        elif has('flat', 'formal'): d.update(ce='flat', c='tilt')
        elif has('deadpan', 'dry', 'matter', 'wry'): d.update(ce='squint', c='lean')
        else: d.update(ce='norm', c='talk')
    return d

def check(ep, lines, out, events):
    err, warn = [], []
    if not re.fullmatch(r'[A-Za-z0-9_]+', ep): err.append(f'episode name "{ep}" may only use letters, digits and _ (for example 04_coffee)')
    def names(i, d, where=''):
        for k, ok in (('f', F_POSES), ('fe', F_FACES), ('c', C_POSES), ('ce', C_EYES)):
            if d.get(k) is not None and d[k] not in ok: err.append(f'line {i}{where}: {k}="{d[k]}" is not one of: {" ".join(ok)}')
    for l in out:
        i = l['id']; t = l['text']; spoken = re.sub(r'\[[^\]]*\]', '', t).strip()
        if l['who'] not in ('F', 'C'): err.append(f'line {i}: who must be "F" (Pixel) or "C" (Claude)')
        if not re.match(r'\s*\[[^\]]+\]', t): err.append(f'line {i}: starts without an emotion tag like [deadpan]')
        if not re.search(r'[A-Za-z0-9\uac00-\ud7a3]', spoken): err.append(f'line {i}: has a tag but no spoken words')
        names(i, l)
        for s in (l['shot'] if isinstance(l.get('shot'), list) else [l['shot']] if l.get('shot') else []):
            if s not in SHOTS: err.append(f'line {i}: shot "{s}" is not one of: {" ".join(SHOTS)}')
        for e in l.get('extra', []): names(i, e, ' extra')
        for k in l:
            if k not in KEYS + ['id', 'who', 'text', 'gap']: err.append(f'line {i}: unknown setting "{k}" (known: {" ".join(KEYS)})')
        if l.get('c') == 'away': warn.append(f'line {i}: Claude pose "away" hides both eyes in a close-up; use "hunch" or c="tilt", ce="up" for sulking')
    for e in events or []:
        if 'line' in e and not 1 <= e['line'] <= len(out): err.append(f'screen event points at line {e["line"]}, but the script has {len(out)} lines')
        if not 0 <= e.get('pane', 0) <= 5: err.append('screen event pane must be 0-5')
    words = sum(len(re.sub(r'\[[^\]]*\]', '', l['text']).split()) for l in out)
    if not (90 <= words <= 135 or (55 <= words <= 110 and re.search(r'[\uac00-\ud7a3]', out[0]['text']))): warn.append(f'{words} spoken words (the style is 90-135, about 50-65 seconds)')
    if out and not re.sub(r'\[[^\]]*\]', '', out[0]['text']).strip().lower().startswith(('claude', '클로드')): warn.append('line 1 does not open with "Claude. ..." (the hook)')
    if not any(l['gap'] >= .85 for l in out[:-1]): warn.append('no silent beat: give one line a gap of 0.85 s or more before the turn')
    for w in warn: print('  note:', w)
    if err: raise SystemExit(f'{ep}: script not written\n  ' + '\n  '.join(err))
    return words

def build(ep, title, lines, ui=None, events=None, end='cut', tail=1.9, hideF=None, music='cozy', speed=1.0, tts='typecast'):
    out = {"title": title, "end": end, "tail": tail, "lead": 0.18, "music": MUSIC.get(music, music), "voices": VOICES, "speed": speed, "tts": tts, "lines": []}
    for i, ln in enumerate(lines, 1):
        who, text, gap = ln[0], ln[1], ln[2]; rest = ln[3:]
        punch = 'p' in rest; ov = next((r for r in rest if isinstance(r, dict)), {})
        d = infer(who, text)
        if punch: d.update(hop=True, ce='happy' if who == 'C' else None, c='proud' if who == 'C' else None)
        d = {k: v for k, v in d.items() if v is not None}; d.update(ov)
        out["lines"].append({"id": i, "who": who, "text": text, "gap": gap, **d})
    words = check(ep, lines, out["lines"], events)
    if ENV.get('APP_NAME'): ui = {'app': ENV['APP_NAME'], **(ui or {})}  # optional: your own app name on the laptop screen
    if ui: out["ui"] = ui
    if events: out["uiEvents"] = events
    if hideF is not None: out["hideF"] = hideF
    d = P / 'eps' / ep; d.mkdir(parents=True, exist_ok=True); (d / 'script.json').write_text(json.dumps(out, indent=1, ensure_ascii=False))
    chars = sum(len(l['text']) for l in out['lines'])
    print(f'{ep}: {len(lines)} lines, {words} spoken words, {chars} characters for TTS -> eps/{ep}/script.json')

pane = lambda t, p, lines, m='claude-sonnet-4-5': dict(title=t, prompt=p, lines=lines, model=m)
