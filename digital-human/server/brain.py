"""High-level cognition: dialogue + behaviour intent.

The LLM is used ONLY for high-level judgement (what to say, emotion, intent, what to remember).
Real-time motion is handled in the browser runtime. The LLM returns a strict JSON "intent" that the
behaviour system validates and executes.

Claude (claude-opus-5-5) is used when credentials are available (ANTHROPIC_API_KEY / ant profile);
otherwise a deterministic rule-based responder keeps the system fully functional offline.
"""
from __future__ import annotations

import json
import os
import random
import re

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "language": {"type": "string", "enum": ["ko", "en"]},
        "emotion": {"type": "string", "enum": ["neutral", "joy", "sadness", "anger", "fear", "surprise", "disgust",
                                               "embarrassment", "tension", "boredom", "focus", "doubt", "fatigue"]},
        "intensity": {"type": "number"},
        "gesture": {"type": "string", "enum": ["none", "nod", "shake", "wave", "point", "shrug", "open_palms",
                                              "think", "beat"]},
        "action": {"type": "string", "enum": ["none", "walk_to", "sit", "stand", "wave", "look_at", "pick_up",
                                             "handshake", "open_door"]},
        "action_target": {"type": "string"},
        "remember": {"type": "string"},
    },
    "required": ["reply", "language", "emotion", "intensity", "gesture", "action", "action_target", "remember"],
    "additionalProperties": False,
}

SYSTEM = """You are the mind of a digital human named {name}, {age} years old.
Personality (Big Five 0-1): {personality}. Current mood/state: {state}.
You speak naturally and briefly (1-3 sentences), in the user's language (Korean or English).
Choose an emotion and intensity (0-1) that a real person would feel, a co-speech gesture, and an
optional physical action from the allowed list using objects in the scene: {objects}.
If the user tells you something worth remembering about them, put a short fact in "remember", else "".
Relevant memories: {memories}"""


def _claude_available():
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    return os.path.exists(os.path.expanduser("~/.config/anthropic"))


async def think(user_text: str, ctx: dict) -> dict:
    if _claude_available():
        try:
            return await _claude(user_text, ctx)
        except Exception as e:  # fall back but report why
            r = rule_based(user_text, ctx)
            r["llm_error"] = f"{type(e).__name__}: {e}"[:300]
            return r
    return rule_based(user_text, ctx)


async def _claude(user_text: str, ctx: dict) -> dict:
    import anthropic
    client = anthropic.AsyncAnthropic()
    sys_prompt = SYSTEM.format(name=ctx.get("name", "Min-jun"), age=ctx.get("age", 30),
                               personality=json.dumps(ctx.get("personality", {})),
                               state=json.dumps(ctx.get("state", {}), ensure_ascii=False),
                               objects=", ".join(ctx.get("objects", [])) or "none",
                               memories="; ".join(ctx.get("memories", [])) or "none")
    msgs = []
    for h in ctx.get("history", [])[-12:]:
        if h.get("role") in ("user", "assistant") and h.get("text"):
            msgs.append({"role": h["role"], "content": h["text"]})
    msgs.append({"role": "user", "content": user_text})
    # merge consecutive same-role turns (API requires alternation)
    merged = []
    for m in msgs:
        if merged and merged[-1]["role"] == m["role"]:
            merged[-1]["content"] += "\n" + m["content"]
        else:
            merged.append(m)
    if merged[0]["role"] != "user":
        merged = merged[1:]
    resp = await client.beta.messages.create(
        model="claude-opus-5-5",
        max_tokens=2000,
        system=sys_prompt,
        messages=merged,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": INTENT_SCHEMA}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if resp.stop_reason == "refusal":
        r = rule_based(user_text, ctx)
        r["llm_error"] = "refusal"
        return r
    text = next(b.text for b in resp.content if b.type == "text")
    out = json.loads(text)
    out["source"] = f"claude:{resp.model}"
    return out


# ------------------------------------------------------------------ offline fallback
_RULES = [
    (r"안녕|반가|hello|hi\b|hey", {"ko": ["안녕하세요! 만나서 반가워요.", "반가워요, 오늘 어떻게 지내세요?"],
                                   "en": ["Hi! Nice to meet you.", "Hello there, how are you today?"]},
     "joy", 0.6, "wave", "none"),
    (r"이름|name", {"ko": ["저는 김민준이에요."], "en": ["I'm Min-jun."]}, "neutral", 0.3, "open_palms", "none"),
    (r"앉|sit", {"ko": ["네, 잠깐 앉을게요."], "en": ["Sure, let me sit down."]}, "neutral", 0.3, "nod", "sit"),
    (r"일어|stand", {"ko": ["네, 일어날게요."], "en": ["Okay, standing up."]}, "neutral", 0.3, "nod", "stand"),
    (r"걸어|와|이리|come|walk", {"ko": ["지금 갈게요."], "en": ["I'm coming."]}, "neutral", 0.4, "nod", "walk_to"),
    (r"악수|shake", {"ko": ["반갑습니다."], "en": ["Good to meet you."]}, "joy", 0.5, "none", "handshake"),
    (r"슬프|우울|sad", {"ko": ["그랬군요... 많이 힘드셨겠어요."], "en": ["I'm sorry to hear that. That sounds hard."]},
     "sadness", 0.6, "none", "none"),
    (r"화나|짜증|angry", {"ko": ["그건 정말 화날 만하네요."], "en": ["That would make anyone angry."]}, "anger", 0.4, "shake", "none"),
    (r"농담|웃|joke|funny", {"ko": ["하하, 그거 재밌네요!"], "en": ["Ha, that's funny!"]}, "joy", 0.8, "beat", "none"),
    (r"왜|어떻게|why|how", {"ko": ["음... 좋은 질문이에요. 잠깐 생각해볼게요."], "en": ["Hmm... good question. Let me think."]},
     "focus", 0.5, "think", "none"),
]


def rule_based(user_text: str, ctx: dict) -> dict:
    lang = "ko" if re.search(r"[가-힣]", user_text) else "en"
    for pat, replies, emo, inten, gest, act in _RULES:
        if re.search(pat, user_text, re.I):
            target = ""
            if act == "walk_to":
                target = "user"
            return {"reply": random.choice(replies[lang]), "language": lang, "emotion": emo, "intensity": inten,
                    "gesture": gest, "action": act, "action_target": target, "remember": "", "source": "rule_based"}
    m = re.search(r"(?:제 이름은|나는|저는)\s*([가-힣A-Za-z]+)|my name is (\w+)", user_text)
    remember = ""
    if m:
        remember = f"user name: {m.group(1) or m.group(2)}"
    return {"reply": "그렇군요. 더 이야기해 주세요." if lang == "ko" else "I see. Tell me more.", "language": lang,
            "emotion": "neutral", "intensity": 0.3, "gesture": "nod", "action": "none", "action_target": "",
            "remember": remember, "source": "rule_based"}
