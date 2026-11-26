"""Grapheme-to-phoneme for Korean (rule based, Hangul jamo) and English (CMUdict + fallback).

Output phones are IPA strings chosen to exist in the wav2vec2-xlsr-53-espeak vocabulary (or map to
a short token list there). Each phone carries the index of the source character/syllable so the
provider's character timestamps can constrain alignment.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

CMU_PATH = os.environ.get("DH_CMUDICT", "/home/user/work/models/cmudict.dict")


@dataclass
class Phone:
    ipa: str
    char_index: int      # index into the original text (syllable / letter)
    word_index: int
    stress: int = 0      # 0 none, 1 secondary, 2 primary
    lang: str = "ko"


# ------------------------------------------------------------------ Korean
_L = ["k", "k͈", "n", "t", "t͈", "ɾ", "m", "p", "p͈", "s", "s͈", "", "tɕ", "tɕ͈", "tɕʰ", "kʰ", "tʰ", "pʰ", "h"]
_V = ["a", "ɛ", "ja", "jɛ", "ʌ", "e", "jʌ", "je", "o", "wa", "wɛ", "we", "jo", "u", "wʌ", "we", "wi", "ju", "ɯ", "ɯi", "i"]
# final consonant: (neutralised coda, consonant used when it links to a following vowel)
_T = [None, ("k", "k"), ("k", "k͈"), ("k", "s"), ("n", "n"), ("n", "tɕ"), ("n", "h"), ("t", "t"), ("l", "ɾ"),
      ("k", "k"), ("m", "m"), ("l", "p"), ("l", "s"), ("l", "tʰ"), ("p", "pʰ"), ("l", "h"), ("m", "m"), ("p", "p"),
      ("p", "s"), ("t", "s"), ("t", "s͈"), ("ŋ", "ŋ"), ("t", "tɕ"), ("t", "tɕʰ"), ("k", "kʰ"), ("t", "tʰ"), ("p", "pʰ"),
      ("t", "h")]
_ASPIRATE = {"k": "kʰ", "t": "tʰ", "p": "pʰ", "tɕ": "tɕʰ"}
_NASAL = {"k": "ŋ", "t": "n", "p": "m"}


def _syll(ch):
    c = ord(ch) - 0xAC00
    if 0 <= c < 11172:
        return c // 588, (c % 588) // 28, c % 28
    return None


def g2p_korean(text: str) -> list[Phone]:
    out: list[Phone] = []
    sylls = []  # (char_index, word_index, L, V, T)
    wi = 0
    prev_space = True
    for i, ch in enumerate(text):
        s = _syll(ch)
        if s:
            if prev_space and sylls:
                wi += 1
            sylls.append([i, wi, *s])
            prev_space = False
        elif ch.isspace() or ch in ".,!?…~":
            prev_space = True
            if ch in ".,!?…" and sylls:
                sylls.append([i, wi, None, None, None])  # pause marker
    for k, sy in enumerate(sylls):
        i, w, L, V, T = sy[:5]
        if L is None:
            out.append(Phone("|", i, w, lang="ko"))
            continue
        nxt = sylls[k + 1] if k + 1 < len(sylls) and sylls[k + 1][2] is not None else None
        onset = _L[L]
        # onset modified by previous coda (handled when processing previous syllable via sy flags)
        if sy[2] is not None and len(sy) > 5:
            onset = sy[-1]
        if onset:
            out.append(Phone(onset, i, w, lang="ko"))
        out.append(Phone(_V[V], i, w, lang="ko"))
        if T:
            coda, link = _T[T]
            if nxt is not None:
                nL = nxt[2]
                nonset = _L[nL]
                if nonset == "" and link not in ("ŋ", "h"):           # liaison (연음)
                    nxt.append(link if link != "ɾ" else "ɾ")
                    continue
                if link == "h" or T in (6, 15):                       # ㅎ coda: aspirate next
                    if nonset in _ASPIRATE:
                        nxt.append(_ASPIRATE[nonset])
                        if coda != "t":
                            out.append(Phone(coda, i, w, lang="ko"))
                        continue
                    if nonset == "":
                        continue
                if nonset == "h" and coda in _ASPIRATE:               # coda + ㅎ -> aspirated
                    nxt.append(_ASPIRATE[coda])
                    continue
                if nonset in ("n", "m") and coda in _NASAL:           # nasalisation
                    coda = _NASAL[coda]
                if nonset == "ɾ":
                    if coda in ("n", "l"):
                        coda = "l"
                        nxt.append("l")
                    elif coda in ("m", "ŋ"):
                        nxt.append("n")
                    elif coda in _NASAL:
                        coda = _NASAL[coda]
                        nxt.append("n")
                if coda == "n" and nonset == "ɾ":
                    coda = "l"
            out.append(Phone(coda, i, w, lang="ko"))
    return out


# ------------------------------------------------------------------ English
_ARPA = {"AA": "ɑ", "AE": "æ", "AH": "ʌ", "AO": "ɔ", "AW": "aʊ", "AY": "aɪ", "B": "b", "CH": "tʃ", "D": "d",
         "DH": "ð", "EH": "ɛ", "ER": "ɚ", "EY": "eɪ", "F": "f", "G": "ɡ", "HH": "h", "IH": "ɪ", "IY": "i",
         "JH": "dʒ", "K": "k", "L": "l", "M": "m", "N": "n", "NG": "ŋ", "OW": "oʊ", "OY": "ɔɪ", "P": "p",
         "R": "ɹ", "S": "s", "SH": "ʃ", "T": "t", "TH": "θ", "UH": "ʊ", "UW": "u", "V": "v", "W": "w",
         "Y": "j", "Z": "z", "ZH": "ʒ"}
_CMU = None


def _cmu():
    global _CMU
    if _CMU is None:
        _CMU = {}
        if os.path.exists(CMU_PATH):
            for line in open(CMU_PATH, encoding="utf-8", errors="ignore"):
                p = line.split("#")[0].split()
                if len(p) < 2:
                    continue
                w = re.sub(r"\(\d+\)$", "", p[0]).lower()
                _CMU.setdefault(w, p[1:])
    return _CMU


_LTS = [("tion", ["ʃ", "ʌ", "n"]), ("ch", ["tʃ"]), ("sh", ["ʃ"]), ("th", ["θ"]), ("ph", ["f"]), ("ng", ["ŋ"]),
        ("ee", ["i"]), ("oo", ["u"]), ("ou", ["aʊ"]), ("ea", ["i"]), ("ai", ["eɪ"]), ("ay", ["eɪ"]),
        ("a", ["æ"]), ("e", ["ɛ"]), ("i", ["ɪ"]), ("o", ["ɑ"]), ("u", ["ʌ"]), ("y", ["i"]), ("b", ["b"]),
        ("c", ["k"]), ("d", ["d"]), ("f", ["f"]), ("g", ["ɡ"]), ("h", ["h"]), ("j", ["dʒ"]), ("k", ["k"]),
        ("l", ["l"]), ("m", ["m"]), ("n", ["n"]), ("p", ["p"]), ("q", ["k"]), ("r", ["ɹ"]), ("s", ["s"]),
        ("t", ["t"]), ("v", ["v"]), ("w", ["w"]), ("x", ["k", "s"]), ("z", ["z"])]


def _letters_to_sound(w):
    out, i = [], 0
    while i < len(w):
        for g, ph in _LTS:
            if w.startswith(g, i):
                out += [(p, 0) for p in ph]
                i += len(g)
                break
        else:
            i += 1
    return out


def g2p_english(text: str) -> list[Phone]:
    out: list[Phone] = []
    d = _cmu()
    wi = -1
    for m in re.finditer(r"[A-Za-z']+|[.,!?;:]", text):
        tok = m.group(0)
        if tok not in ".,!?;:":
            wi += 1
        if tok in ".,!?;:":
            out.append(Phone("|", m.start(), wi, lang="en"))
            continue
        w = tok.lower()
        if w in d:
            phs = []
            for a in d[w]:
                st = int(a[-1]) if a[-1].isdigit() else 0
                base = a.rstrip("012")
                ipa = _ARPA[base]
                if base == "AH" and st == 0:
                    ipa = "ə"
                phs.append((ipa, {0: 0, 1: 2, 2: 1}[st]))
        else:
            phs = _letters_to_sound(w)
        n = len(phs)
        for k, (ipa, st) in enumerate(phs):
            ci = m.start() + int(k * len(tok) / max(n, 1))
            out.append(Phone(ipa, ci, wi, st, "en"))
    return out


def g2p(text: str, lang: str) -> list[Phone]:
    if lang.startswith("ko"):
        return g2p_korean(text)
    return g2p_english(text)


def detect_lang(text: str) -> str:
    hangul = sum(1 for c in text if 0xAC00 <= ord(c) <= 0xD7A3)
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    return "ko" if hangul * 2.5 >= latin else "en"     # a Hangul syllable ~ 2-3 Latin letters of speech


# ------------------------------------------------------------------ visemes
# 15-class viseme set (compatible with common viseme standards); the runtime maps each
# to a weighted ARKit pose and applies coarticulation.
VISEME_OF = {}
for v, phones in {
    "PP": "p b m p͈ pʰ", "FF": "f v", "TH": "θ ð", "DD": "t d t͈ tʰ", "kk": "k ɡ k͈ kʰ ŋ h x",
    "CH": "tʃ dʒ ʃ ʒ tɕ tɕ͈ tɕʰ dʑ ɕ", "SS": "s z s͈", "nn": "n l ɫ", "RR": "ɹ ɾ r",
    "aa": "a ɑ æ ʌ aɪ aʊ ja wa jʌ wʌ", "E": "e ɛ eɪ je jɛ we wɛ ɚ ə", "I": "i ɪ j ɯ ɯi wi", "O": "o ɔ oʊ ɔɪ jo",
    "U": "u ʊ w ju",
}.items():
    for p in phones.split():
        VISEME_OF[p] = v
VISEME_OF["|"] = "sil"


def viseme_of(ipa: str) -> str:
    if ipa in VISEME_OF:
        return VISEME_OF[ipa]
    if ipa and ipa[0] in "aeiouɑæʌɛɪɔʊəɯ":
        return VISEME_OF.get(ipa[0], "aa")
    return "DD"
