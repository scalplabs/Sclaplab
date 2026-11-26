"""Acoustic forced alignment of a known phone sequence to audio.

Model: facebook/wav2vec2-xlsr-53-espeak-cv-ft (Apache-2.0), multilingual IPA phone CTC, 20 ms frames.
Method: CTC Viterbi over the expected token sequence (with blanks) -> per-token frame spans ->
per-phone [start,end]. Provider character timestamps (Typecast) are used as a sanity constraint:
if a phone lands outside its syllable window by > TOL, it is redistributed inside that window.
"""
from __future__ import annotations

import json
import os
import threading

import numpy as np

MODEL_DIR = os.environ.get("DH_W2V_DIR", "/home/user/work/models/w2v")
FRAME = 0.02
TOL = 0.08

_lock = threading.Lock()
_model = None
_vocab = None

# phones not in the model vocab -> token sequence in vocab
FALLBACK = {"k͈": ["k"], "t͈": ["t"], "p͈": ["p"], "s͈": ["s"], "tɕ͈": ["tɕ"], "tɕʰ": ["tɕh"], "ɾ": ["ɾ"],
            "jʌ": ["j", "ʌ"], "jɛ": ["j", "ɛ"], "je": ["j", "e"], "jo": ["j", "o"], "wa": ["w", "a"],
            "wɛ": ["w", "ɛ"], "we": ["w", "e"], "wi": ["w", "i"], "wʌ": ["w", "ʌ"], "ɯi": ["ɯ", "i"],
            "ɚ": ["ɚ"], "dʑ": ["dʑ"], "ɡ": ["ɡ"]}


def _load():
    global _model, _vocab
    if _model is None:
        import torch
        from transformers import Wav2Vec2ForCTC
        torch.set_num_threads(max(1, os.cpu_count() - 1))
        _model = Wav2Vec2ForCTC.from_pretrained(MODEL_DIR).eval()
        _vocab = json.load(open(os.path.join(MODEL_DIR, "vocab.json")))
    return _model, _vocab


def tokens_for(ipa: str, vocab: dict) -> list[int]:
    if ipa in vocab:
        return [vocab[ipa]]
    seq = FALLBACK.get(ipa)
    if seq is None:
        # greedy longest-match decomposition
        seq, i = [], 0
        while i < len(ipa):
            for L in (3, 2, 1):
                if ipa[i:i + L] in vocab:
                    seq.append(ipa[i:i + L])
                    i += L
                    break
            else:
                i += 1
    return [vocab[t] for t in seq if t in vocab]


def emissions(wav16: np.ndarray) -> np.ndarray:
    import torch
    model, _ = _load()
    x = (wav16 - wav16.mean()) / (wav16.std() + 1e-7)
    with _lock, torch.inference_mode():
        logits = model(torch.from_numpy(x.astype(np.float32))[None]).logits[0]
        lp = torch.log_softmax(logits, -1).numpy()
    return lp


def ctc_viterbi(lp: np.ndarray, tokens: list[int], blank: int) -> list[tuple[int, int]]:
    """returns (start_frame, end_frame_exclusive) per token"""
    T = lp.shape[0]
    S = 2 * len(tokens) + 1
    ext = [blank] * S
    for i, t in enumerate(tokens):
        ext[2 * i + 1] = t
    ext = np.array(ext)
    NEG = -1e30
    dp = np.full((T, S), NEG, np.float32)
    bp = np.zeros((T, S), np.int8)
    dp[0, 0] = lp[0, ext[0]]
    if S > 1:
        dp[0, 1] = lp[0, ext[1]]
    skip_ok = np.zeros(S, bool)
    for s in range(2, S):
        skip_ok[s] = ext[s] != blank and ext[s] != ext[s - 2]
    for t in range(1, T):
        prev = dp[t - 1]
        c0 = prev
        c1 = np.concatenate([[NEG], prev[:-1]])
        c2 = np.concatenate([[NEG, NEG], prev[:-2]])
        c2 = np.where(skip_ok, c2, NEG)
        stack = np.stack([c0, c1, c2])
        arg = stack.argmax(0)
        dp[t] = stack[arg, np.arange(S)] + lp[t, ext]
        bp[t] = arg
    s = S - 1 if S == 1 or dp[T - 1, S - 1] >= dp[T - 1, S - 2] else S - 2
    path = np.zeros(T, np.int64)
    for t in range(T - 1, -1, -1):
        path[t] = s
        s -= bp[t, s]
    spans = []
    for i in range(len(tokens)):
        fr = np.nonzero(path == 2 * i + 1)[0]
        spans.append((int(fr[0]), int(fr[-1]) + 1) if len(fr) else (-1, -1))
    # fill tokens that got no frames (shouldn't happen in CTC, safety)
    for i, (a, b) in enumerate(spans):
        if a < 0:
            pa = spans[i - 1][1] if i else 0
            spans[i] = (pa, pa + 1)
    return spans


def resample(wav: np.ndarray, sr: int, target=16000) -> np.ndarray:
    if sr == target:
        return wav
    from math import gcd
    from scipy.signal import resample_poly
    g = gcd(sr, target)
    return resample_poly(wav, target // g, sr // g).astype(np.float32)


def align(wav: np.ndarray, sr: int, phones, char_times: list | None = None) -> dict:
    """phones: list[g2p.Phone]; char_times: list of (char_index, start, end) from the TTS provider.
    returns {phones:[{p,start,end,viseme,stress,word}], method, frames}"""
    from .g2p import viseme_of
    w16 = resample(wav.astype(np.float32), sr)
    lp = emissions(w16)
    _, vocab = _load()
    blank = vocab.get("<pad>", 0)
    toks, owner = [], []
    for pi, ph in enumerate(phones):
        if ph.ipa == "|":
            continue
        for t in tokens_for(ph.ipa, vocab):
            toks.append(t)
            owner.append(pi)
    spans = ctc_viterbi(lp, toks, blank) if toks else []
    pstart, pend = {}, {}
    for (a, b), pi in zip(spans, owner):
        pstart[pi] = min(pstart.get(pi, 1e9), a * FRAME)
        pend[pi] = max(pend.get(pi, 0), b * FRAME)
    # CTC emits a phone's spike early and short: extend each phone to the next phone's onset
    order = [pi for pi in range(len(phones)) if pi in pstart]
    for k, pi in enumerate(order):
        if k + 1 < len(order):
            nxt = pstart[order[k + 1]]
            if nxt - pend[pi] < 0.25:          # no long pause: contiguous
                pend[pi] = max(pend[pi], nxt)
    method = "ctc_forced_alignment"
    fixed = 0
    if char_times:
        cwin = {ci: (s, e) for ci, s, e in char_times}
        en = phones and phones[0].lang == "en"
        groups, win = {}, {}
        for pi in order:
            key = phones[pi].word_index if en else phones[pi].char_index
            groups.setdefault(key, []).append(pi)
        if en:
            # word window = span of the provider times of the word's characters
            wchars = {}
            for pi in range(len(phones)):
                if phones[pi].ipa != "|":
                    wchars.setdefault(phones[pi].word_index, set()).add(phones[pi].char_index)
            for w, cis in wchars.items():
                lo, hi = min(cis), max(cis)
                ts = [(s, e) for ci, (s, e) in cwin.items() if lo <= ci <= hi + 3]
                if ts:
                    win[w] = (min(t[0] for t in ts), max(t[1] for t in ts))
        else:
            win = cwin
        for key, pis in groups.items():
            if key not in win:
                continue
            s, e = win[key]
            bad = any(pstart[p] < s - TOL or pend[p] > e + TOL for p in pis)
            if bad:
                fixed += 1
                n = len(pis)
                for j, p in enumerate(pis):
                    pstart[p] = s + (e - s) * j / n
                    pend[p] = s + (e - s) * (j + 1) / n
        if fixed:
            method += f"+provider_window_fix({fixed}/{len(groups)})"
    out = []
    for pi in order:
        ph = phones[pi]
        out.append({"p": ph.ipa, "start": round(pstart[pi], 3), "end": round(pend[pi], 3),
                    "viseme": viseme_of(ph.ipa), "stress": ph.stress, "word": ph.word_index, "char": ph.char_index})
    return {"phones": out, "method": method, "frames": int(lp.shape[0]),
            "confidence": float(np.mean([lp[a:b, t].max() for (a, b), t in zip(spans, toks)])) if toks else 0.0}


def proportional(phones, char_times: list | None, duration: float) -> dict:
    """Fallback without acoustic model: distribute phones inside provider char windows
    (or uniformly over the duration when no timestamps exist). Marked approximate."""
    from .g2p import viseme_of
    out = []
    if char_times:
        win = {ci: (s, e) for ci, s, e in char_times}
        groups = {}
        for pi, ph in enumerate(phones):
            if ph.ipa != "|":
                groups.setdefault(ph.char_index, []).append(pi)
        for ci, pis in groups.items():
            s, e = win.get(ci, (None, None))
            if s is None:
                continue
            for j, p in enumerate(pis):
                out.append({"p": phones[p].ipa, "start": s + (e - s) * j / len(pis), "end": s + (e - s) * (j + 1) / len(pis),
                            "viseme": viseme_of(phones[p].ipa), "stress": phones[p].stress, "word": phones[p].word_index,
                            "char": ci})
        out.sort(key=lambda x: x["start"])
        return {"phones": out, "method": "provider_char_timestamps_proportional (approximate)"}
    real = [p for p in phones if p.ipa != "|"]
    n = max(len(real), 1)
    for j, ph in enumerate(real):
        out.append({"p": ph.ipa, "start": duration * j / n, "end": duration * (j + 1) / n, "viseme": viseme_of(ph.ipa),
                    "stress": ph.stress, "word": ph.word_index, "char": ph.char_index})
    return {"phones": out, "method": "uniform_estimate (approximate, no timing source)"}
