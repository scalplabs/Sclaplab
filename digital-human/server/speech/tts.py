"""TTS providers. Each returns (wav_float32, sample_rate, char_times[(char_index,start,end)] or None, meta).

typecast   : https://api.typecast.ai/v1/text-to-speech/with-timestamps  (X-API-KEY; in the cloud dev
             environment the egress proxy injects the key). Verified working.
elevenlabs : https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps (xi-api-key from
             ELEVENLABS_API_KEY). Implemented to the public API; NOT verified here (no key available).
"""
from __future__ import annotations

import base64
import io
import json
import os
import urllib.request

import numpy as np
import soundfile as sf

TYPECAST_URL = os.environ.get("TYPECAST_URL", "https://api.typecast.ai")
DEFAULT_VOICE = {"typecast": os.environ.get("TYPECAST_VOICE", "tc_6af54d77f4d336c400d1370d"),   # "Jinheon", young adult male
                 "elevenlabs": os.environ.get("ELEVENLABS_VOICE", "")}
EMO_TYPECAST = {"neutral": "normal", "joy": "happy", "happy": "happy", "sadness": "sad", "sad": "sad",
                "anger": "angry", "angry": "angry", "surprise": "toneup", "fear": "tonedown", "tension": "tonedown",
                "embarrassment": "tonedown", "boredom": "tonedown", "fatigue": "tonedown", "focus": "normal",
                "doubt": "tonedown", "disgust": "angry", "whisper": "whisper"}


class TTSError(Exception):
    pass


def _post(url, body, headers, timeout=90):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers})
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise TTSError(f"{url} -> HTTP {e.code}: {e.read()[:300]!r}") from e
    except urllib.error.URLError as e:
        raise TTSError(f"{url} unreachable: {e}") from e


def _char_map(text, chars):
    out, pos = [], 0
    for c in chars:
        t = c.get("text") or c.get("character") or ""
        if not t.strip():
            continue
        i = text.find(t, pos)
        if i >= 0:
            out.append((i, float(c["start"]), float(c["end"])))
            pos = i + len(t)
    return out


def typecast(text, lang, emotion="neutral", intensity=1.0, voice_id=None, speed=1.0):
    body = {"voice_id": voice_id or DEFAULT_VOICE["typecast"], "text": text, "model": "ssfm-v30",
            "language": "kor" if lang.startswith("ko") else "eng",
            "prompt": {"emotion_preset": EMO_TYPECAST.get(emotion, "normal"),
                       "emotion_intensity": float(max(0.0, min(2.0, intensity * 1.2)))},
            "output": {"audio_format": "wav", "audio_tempo": float(speed)}}
    key = os.environ.get("TYPECAST_API_KEY", "proxy-injected")
    r = json.load(_post(f"{TYPECAST_URL}/v1/text-to-speech/with-timestamps", body, {"X-API-KEY": key}))
    wav, sr = sf.read(io.BytesIO(base64.b64decode(r["audio"])), dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(1)
    return wav, sr, _char_map(text, r.get("characters") or []), {"provider": "typecast", "voice_id": body["voice_id"],
                                                                 "emotion_preset": body["prompt"]["emotion_preset"]}


def elevenlabs(text, lang, emotion="neutral", intensity=1.0, voice_id=None, speed=1.0):
    key = os.environ.get("ELEVENLABS_API_KEY")
    vid = voice_id or DEFAULT_VOICE["elevenlabs"]
    if not key or not vid:
        raise TTSError("ElevenLabs needs ELEVENLABS_API_KEY and ELEVENLABS_VOICE")
    style = {"joy": 0.6, "anger": 0.7, "sadness": 0.5}.get(emotion, 0.2) * intensity
    body = {"text": text, "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": style, "speed": speed}}
    r = json.load(_post(f"https://api.elevenlabs.io/v1/text-to-speech/{vid}/with-timestamps?output_format=pcm_44100",
                        body, {"xi-api-key": key}))
    pcm = np.frombuffer(base64.b64decode(r["audio_base64"]), dtype="<i2").astype(np.float32) / 32768
    al = r.get("alignment") or {}
    chars = [{"text": c, "start": s, "end": e} for c, s, e in zip(al.get("characters", []),
                                                                  al.get("character_start_times_seconds", []),
                                                                  al.get("character_end_times_seconds", []))]
    return pcm, 44100, _char_map(text, chars), {"provider": "elevenlabs", "voice_id": vid}


PROVIDERS = {"typecast": typecast, "elevenlabs": elevenlabs}


def synth(text, lang, provider="typecast", **kw):
    order = [provider] + [p for p in PROVIDERS if p != provider]
    errs = []
    for p in order:
        try:
            return PROVIDERS[p](text, lang, **kw)
        except TTSError as e:
            errs.append(str(e))
    raise TTSError("; ".join(errs))
