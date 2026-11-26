"""Digital-human backend (aiohttp).

  python -m server.app [--port 8765]           (run from digital-human/)

Endpoints
  GET  /                      dev interface (web/index.html) + static assets
  GET  /api/health            provider / model availability
  POST /api/tts               {text, lang?, emotion?, intensity?, provider?, voice_id?, speed?}
                              -> {id, audio_url, duration, lang, phones[], words[], energy[], method, provider}
  POST /api/chat              {text, context}  -> intent JSON (reply, emotion, gesture, action, ...)
  POST /api/say               chat + tts in one call (what the runtime uses for conversations)
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import soundfile as sf
from aiohttp import web

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from server import brain  # noqa: E402
from server.speech import align, g2p, tts  # noqa: E402

CACHE = os.environ.get("DH_TTS_CACHE", os.path.join(ROOT, "server", "_cache"))
os.makedirs(CACHE, exist_ok=True)
POOL = ThreadPoolExecutor(max_workers=2)


def energy_envelope(wav, sr, hz=50):
    hop = sr // hz
    n = len(wav) // hop
    e = np.sqrt(np.mean(wav[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    e = e / (e.max() + 1e-9)
    return [round(float(x), 3) for x in e]


def words_from(text, phones, lang):
    words = {}
    for p in phones:
        w = words.setdefault(p["word"], {"i": p["word"], "start": p["start"], "end": p["end"], "stress": 0})
        w["start"] = min(w["start"], p["start"])
        w["end"] = max(w["end"], p["end"])
        w["stress"] = max(w["stress"], p.get("stress", 0))
    toks = text.split() if lang == "ko" else [t for t in __import__("re").findall(r"[A-Za-z']+", text)]
    out = []
    for k in sorted(words):
        w = words[k]
        w["text"] = toks[k] if k < len(toks) else ""
        out.append(w)
    return out


def synth_and_align(req: dict) -> dict:
    text = req["text"].strip()
    lang = req.get("lang") or g2p.detect_lang(text)
    key = hashlib.sha1(json.dumps({**req, "lang": lang, "v": 3}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    jpath = os.path.join(CACHE, key + ".json")
    if os.path.exists(jpath):
        return json.load(open(jpath))
    t0 = time.time()
    wav, sr, char_times, meta = tts.synth(text, lang, provider=req.get("provider", "typecast"),
                                          emotion=req.get("emotion", "neutral"), intensity=float(req.get("intensity", 0.5)),
                                          voice_id=req.get("voice_id"), speed=float(req.get("speed", 1.0)))
    t1 = time.time()
    phones = g2p.g2p(text, lang)
    try:
        res = align.align(wav, sr, phones, char_times)
    except Exception as e:  # acoustic model unavailable -> provider-window proportional (approximate)
        res = align.proportional(phones, char_times, len(wav) / sr)
        res["align_error"] = str(e)[:200]
    t2 = time.time()
    sf.write(os.path.join(CACHE, key + ".wav"), wav, sr, subtype="PCM_16")
    out = {"id": key, "audio_url": f"/audio/{key}.wav", "duration": round(len(wav) / sr, 3), "lang": lang,
           "text": text, "phones": res["phones"], "method": res["method"], "confidence": res.get("confidence"),
           "words": words_from(text, res["phones"], lang), "energy": energy_envelope(wav, sr),
           "char_times": char_times, **meta, "timing_ms": {"tts": int((t1 - t0) * 1000), "align": int((t2 - t1) * 1000)}}
    json.dump(out, open(jpath, "w"), ensure_ascii=False)
    return out


async def h_tts(request):
    req = await request.json()
    if not req.get("text", "").strip():
        return web.json_response({"error": "text required"}, status=400)
    if len(req["text"]) > 600:
        return web.json_response({"error": "text too long (max 600 chars per utterance)"}, status=400)
    try:
        out = await asyncio.get_running_loop().run_in_executor(POOL, synth_and_align, req)
    except tts.TTSError as e:
        return web.json_response({"error": "tts_failed", "detail": str(e)}, status=502)
    return web.json_response(out)


async def h_chat(request):
    req = await request.json()
    out = await brain.think(req.get("text", ""), req.get("context", {}))
    return web.json_response(out)


async def h_say(request):
    req = await request.json()
    intent = await brain.think(req.get("text", ""), req.get("context", {}))
    speech = None
    try:
        speech = await asyncio.get_running_loop().run_in_executor(
            POOL, synth_and_align, {"text": intent["reply"], "lang": intent["language"], "emotion": intent["emotion"],
                                    "intensity": intent["intensity"]})
    except tts.TTSError as e:
        intent["tts_error"] = str(e)
    return web.json_response({"intent": intent, "speech": speech})


# ---------------------------------------------------------------- external control bridge
PAGES: set = set()
PENDING: dict = {}


async def h_ws(request):
    """the browser runtime connects here and executes forwarded API commands"""
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    PAGES.add(ws)
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                data = json.loads(msg.data)
                fut = PENDING.pop(data.get("id"), None)
                if fut and not fut.done():
                    fut.set_result(data)
    finally:
        PAGES.discard(ws)
    return ws


async def h_control(request):
    """External programs: POST {"cmd": "walkTo", "args": [{"x":1,"z":2}], "timeout": 30}
    -> forwarded to the live runtime; returns {"ok", "result"| "error","message"}"""
    req = await request.json()
    if not PAGES:
        return web.json_response({"ok": False, "error": "NO_RUNTIME", "message": "no browser runtime connected"}, status=503)
    cid = hashlib.sha1(f"{time.time()}{id(req)}".encode()).hexdigest()[:12]
    fut = asyncio.get_running_loop().create_future()
    PENDING[cid] = fut
    ws = next(iter(PAGES))
    await ws.send_str(json.dumps({"id": cid, "cmd": req.get("cmd"), "args": req.get("args", [])}))
    try:
        res = await asyncio.wait_for(fut, timeout=float(req.get("timeout", 60)))
    except asyncio.TimeoutError:
        PENDING.pop(cid, None)
        return web.json_response({"ok": False, "error": "TIMEOUT"}, status=504)
    return web.json_response(res, status=200 if res.get("ok") else 400)


async def h_health(request):
    w2v = os.path.exists(os.path.join(align.MODEL_DIR, "pytorch_model.bin"))
    return web.json_response({"ok": True, "tts": list(tts.PROVIDERS), "forced_alignment_model": w2v,
                              "llm": "claude-opus-5-5" if brain._claude_available() else "rule_based_fallback",
                              "runtimes_connected": len(PAGES)})


async def h_audio(request):
    name = os.path.basename(request.match_info["name"])
    p = os.path.join(CACHE, name)
    if not os.path.exists(p):
        raise web.HTTPNotFound()
    return web.FileResponse(p, headers={"Cache-Control": "max-age=86400"})


@web.middleware
async def nocache_html(request, handler):
    resp = await handler(request)
    if request.path.endswith((".js", ".html")) or request.path == "/":
        resp.headers["Cache-Control"] = "no-cache"
    return resp


def make_app():
    app = web.Application(middlewares=[nocache_html], client_max_size=4 * 1024 * 1024)
    app.router.add_get("/api/health", h_health)
    app.router.add_post("/api/tts", h_tts)
    app.router.add_post("/api/chat", h_chat)
    app.router.add_post("/api/say", h_say)
    app.router.add_get("/audio/{name}", h_audio)
    app.router.add_get("/ws", h_ws)
    app.router.add_post("/api/control", h_control)
    web_dir = os.path.join(ROOT, "web")
    app.router.add_get("/", lambda r: web.FileResponse(os.path.join(web_dir, "index.html")))
    app.router.add_static("/assets/", os.path.join(ROOT, "assets"), show_index=False)
    app.router.add_static("/", web_dir, show_index=False)
    return app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--preload", action="store_true", help="load the alignment model at start")
    a = ap.parse_args()
    if a.preload:
        align._load()
    web.run_app(make_app(), port=a.port)
