"""Speech & server tests. Requires the server running on :8765 (live TTS = Typecast).

/home/user/work/speechvenv/bin/python tests/test_speech.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from server.speech import g2p  # noqa: E402

BASE = os.environ.get("DH_SERVER", "http://localhost:8765")
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), str(detail)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def post(path, body, timeout=120):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def ipa(text, lang):
    return " ".join(p.ipa for p in g2p.g2p(text, lang) if p.ipa != "|")


# ---------------------------------------------------------------- G2P (Korean phonological rules)
cases = {"국물": "k u ŋ m u l",          # nasalisation ㄱ+ㅁ -> ŋ
         "좋다": "tɕ o tʰ a",            # ㅎ aspiration
         "신라": "s i l l a",            # lateralisation ㄴ+ㄹ -> ll
         "음악": "ɯ m a k",              # liaison
         "입니다": "i m n i t a",        # nasalisation ㅂ+ㄴ -> m
         "안녕": "a n n jʌ ŋ"}
for t, exp in cases.items():
    got = ipa(t, "ko")
    check(f"g2p ko '{t}'", got == exp, f"{got} (expected {exp})")
got = ipa("Hello world", "en")
check("g2p en CMUdict 'Hello world'", got == "h ə l oʊ w ɝ l d" or got.startswith("h ə l oʊ w"), got)
check("g2p en OOV letter-to-sound fallback", len(ipa("Minjun", "en").split()) >= 4, ipa("Minjun", "en"))
check("lang detect", g2p.detect_lang("안녕 hello") == "ko" and g2p.detect_lang("hello there") == "en")
vis = {g2p.viseme_of(p.ipa) for p in g2p.g2p("빠르게 말하는 사람과 천천히 걷는 사람", "ko") + g2p.g2p("The quick brown fox jumps over the lazy dog", "en")}
check("viseme coverage (>= 12 of 15 classes on pangrams)", len(vis) >= 12, sorted(vis))

# ---------------------------------------------------------------- server
try:
    with urllib.request.urlopen(BASE + "/api/health", timeout=10) as r:
        h = json.load(r)
    check("server health", h.get("ok"), h)
except Exception as e:  # noqa: BLE001
    check("server health", False, e)
    h = {}

for lang, text in (("ko", "오늘 날씨가 정말 좋네요. 같이 산책할까요?"), ("en", "Peter picked a pepper, and we walked home together.")):
    st, r = post("/api/tts", {"text": text, "lang": lang, "emotion": "joy", "intensity": 0.5})
    ok = st == 200 and r.get("phones")
    check(f"tts+align {lang}: 200 with phones", ok, f"status {st} {r.get('error', '')} {r.get('detail', '')[:120] if isinstance(r.get('detail'), str) else ''}")
    if not ok:
        continue
    ph = r["phones"]
    mono = all(a["start"] <= b["start"] + 1e-6 for a, b in zip(ph, ph[1:])) and all(p["end"] >= p["start"] for p in ph)
    check(f"{lang}: phone times monotonic & non-negative durations", mono)
    check(f"{lang}: phones inside audio duration", ph[-1]["end"] <= r["duration"] + 0.05 and ph[0]["start"] >= 0, f"last end {ph[-1]['end']} / {r['duration']}")
    check(f"{lang}: acoustic forced alignment used (not approximate)", r["method"].startswith("ctc_forced_alignment"), r["method"])
    # agreement with provider character windows: share of phones whose centre lies in their character's window +-80 ms
    win = {c[0]: (c[1], c[2]) for c in r.get("char_times", [])}
    if lang == "ko":
        inside = [win[p["char"]][0] - 0.08 <= (p["start"] + p["end"]) / 2 <= win[p["char"]][1] + 0.08 for p in ph if p["char"] in win]
        check("ko: phones agree with Typecast syllable timestamps (>=90%)", sum(inside) / len(inside) >= 0.9, f"{sum(inside)}/{len(inside)}")
    bil = [p for p in ph if p["viseme"] == "PP"]
    check(f"{lang}: bilabials detected and mapped to PP", len(bil) >= 1, [p["p"] for p in bil])
    check(f"{lang}: energy envelope 50 Hz", abs(len(r["energy"]) - r["duration"] * 50) < 3, len(r["energy"]))
    check(f"{lang}: audio served", urllib.request.urlopen(BASE + r["audio_url"], timeout=20).status == 200)
    print(f"   timing: {r['timing_ms']}  duration {r['duration']}s  phones {len(ph)}")

st, r = post("/api/tts", {"text": ""})
check("tts rejects empty text (400)", st == 400, r)
st, r = post("/api/tts", {"text": "가" * 700})
check("tts rejects > 600 chars (400)", st == 400, r)
st, r = post("/api/chat", {"text": "안녕하세요! 의자에 앉아 주세요", "context": {}})
keys = {"reply", "language", "emotion", "intensity", "gesture", "action", "action_target", "remember"}
check("chat returns full intent schema", st == 200 and keys <= set(r), r)
check("chat: language detected ko", r.get("language") == "ko", r.get("language"))
print("   chat source:", r.get("source"), r.get("llm_error", ""))

n_fail = sum(1 for x in results if not x[1])
print(f"\n{len(results) - n_fail}/{len(results)} passed")
json.dump([{"test": n, "pass": p, "detail": d} for n, p, d in results], open(os.path.join(os.path.dirname(__file__), "results_speech.json"), "w"), indent=1, ensure_ascii=False)
sys.exit(1 if n_fail else 0)
