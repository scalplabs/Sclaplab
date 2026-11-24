#!/usr/bin/env python3
"""Settings for every tool: reads `.env` in the kit folder (real environment variables win).
Run `python3 tools/env.py` to check your setup without spending any credits."""
import os, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULTS = {
    'ELEVENLABS_MODEL_ID': 'eleven_v4',
    'PIXEL_VOICE_ID': 'hp3u3xWyyDK3Zr5h8Ltt',   # 김대리
    'CLAUDE_VOICE_ID': '8zHuDw1bbkbkL93Inv5N',  # 클로드
    'TYPECAST_F_VOICE': 'tc_68257f68bc6e3c161ab5078d',  # 김대리 = 필재 (Typecast)
    'TYPECAST_C_VOICE': 'tc_69f2e455ea79fd197aa0476f',  # 클로드 = 서현 (Typecast)
    'TYPECAST_MODEL': 'ssfm-v31',
}
# Homebrew / python.org Pythons on macOS often ship without a CA bundle: point them at the system one.
if not os.environ.get('SSL_CERT_FILE') and os.path.exists('/etc/ssl/cert.pem'): os.environ['SSL_CERT_FILE'] = '/etc/ssl/cert.pem'

def load():
    env = dict(DEFAULTS); f = ROOT / '.env'
    if f.exists():
        for l in f.read_text().splitlines():
            l = l.strip()
            if not l or l.startswith('#') or '=' not in l: continue
            k, v = l.split('=', 1); v = v.strip().strip('"').strip("'")
            if v: env[k.strip()] = v
    for k in list(DEFAULTS) + ['ELEVENLABS_API_KEY', 'TYPECAST_API_KEY', 'APP_NAME', 'CHROME_PATH']:
        if os.environ.get(k): env[k] = os.environ[k]
    return env

ENV = load()

def api_key():
    k = ENV.get('ELEVENLABS_API_KEY', '')
    if not k:
        raise SystemExit('No ElevenLabs API key found.\n  1. Copy .env.example to .env   (cp .env.example .env)\n  2. Put your key after ELEVENLABS_API_KEY=   (elevenlabs.io > Developers > API keys)')
    return k

def voice_id(who): return ENV['PIXEL_VOICE_ID' if who == 'F' else 'CLAUDE_VOICE_ID']

def explain(code, msg):
    """One plain sentence for the ElevenLabs errors a new user actually hits. Returns None for anything else."""
    m = msg.lower()
    if code == 401 or 'invalid_api_key' in m: return 'ElevenLabs rejected the API key. Check ELEVENLABS_API_KEY in .env (no quotes, no spaces) and that the key has Text to Speech access.'
    if 'missing_permissions' in m: return 'This API key is restricted. In ElevenLabs > Developers > API keys, give it Text to Speech, Speech to Text and Music access.'
    if 'quota' in m or 'credits' in m: return 'Your ElevenLabs account is out of credits for this request.'
    if 'voice_not_found' in m or (code == 404 and 'voice' in m): return 'ElevenLabs does not know this voice ID. Check PIXEL_VOICE_ID / CLAUDE_VOICE_ID in .env, or add the voice to "My Voices" in ElevenLabs first.'
    if 'free_users_not_allowed' in m or 'library voices' in m or code == 402 or 'payment_required' in m or 'paid_plan' in m or 'subscription' in m: return 'Your ElevenLabs plan does not allow this (library voices and music need a paid plan). Upgrade, or set your own voice IDs in .env.'
    if 'model' in m and ('not found' in m or 'does not exist' in m or 'not_found' in m or 'access' in m): return 'Your account cannot use this voice model. Set ELEVENLABS_MODEL_ID in .env to a model you have (for example eleven_v3).'
    return None

if __name__ == '__main__':
    import shutil, subprocess
    ok = True
    def row(name, good, note=''):
        global ok; ok = ok and good; print(('  ok   ' if good else '  FAIL ') + name + ('  ' + note if note else ''))
    row('.env file', (ROOT / '.env').exists(), '' if (ROOT / '.env').exists() else 'cp .env.example .env')
    row('ELEVENLABS_API_KEY', bool(ENV.get('ELEVENLABS_API_KEY')), 'set' if ENV.get('ELEVENLABS_API_KEY') else 'empty: voices cannot be generated yet')
    print('       Pixel voice ', ENV['PIXEL_VOICE_ID']); print('       Claude voice', ENV['CLAUDE_VOICE_ID']); print('       voice model ', ENV['ELEVENLABS_MODEL_ID'])
    for tool in ('ffmpeg', 'ffprobe', 'node'): row(tool, bool(shutil.which(tool)), '' if shutil.which(tool) else 'not installed')
    try: import numpy; row('numpy', True, numpy.__version__)
    except Exception: row('numpy', False, 'python3 -m pip install numpy')
    row('node_modules', (ROOT / 'node_modules' / 'playwright-core').exists(), '' if (ROOT / 'node_modules' / 'playwright-core').exists() else 'run: npm install')
    chrome = ENV.get('CHROME_PATH') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    row('Google Chrome', os.path.exists(chrome) or sys.platform != 'darwin', chrome if os.path.exists(chrome) else 'not at the default path: set CHROME_PATH in .env')
    row('sound effects', (ROOT / 'audio' / 'sfx' / 'amb.wav').exists())
    print('ready' if ok else 'fix the FAIL rows above, then run this again'); sys.exit(0 if ok else 1)
