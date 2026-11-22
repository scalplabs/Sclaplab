# Claude and Pixel kit: instructions for Claude Code

This folder makes "Claude and Pixel" videos: 45-70 second vertical comedy skits (1080x1920, 30 fps) rendered entirely in code. three.js draws the scene, ElevenLabs speaks the lines, ffmpeg joins it. Nothing is AI video. The look is fixed by the engine. **A new video is only a new script.**

When the user says "make me a new episode about X", do the six steps below from start to finish and hand back `out/<ep>.mp4`. Do not ask for anything that this file already answers.

## Ground rules

- Work only inside this folder. Never edit `engine/`, `lib/`, `fonts/` or `audio/sfx/` unless the user asks for a change to the look itself.
- Never open, print or copy `.env`. If a tool says the key is missing or rejected, tell the user what to put in `.env` and stop.
- Voices and music cost the user ElevenLabs credits. Lines are cached, so re-running is cheap, but do not regenerate voices for fun (`--force`, `seed`) without a reason.
- One render at a time. A render takes 2-5 minutes: run `./tools/make.sh` with a 10 minute timeout or in the background, and wait for it.
- Run every command from the kit folder (the folder this file is in).

## The six steps

Pick the next free number and a short name: `NN_name`, letters, digits and `_` only (look at `eps/` and `scripts/`; the samples use 01-03, so the first new one is `04_...`).

1. **Write the script** as `scripts/NN_name.py` (copy the shape of `scripts/01_right.py`), then run it:
   `python3 scripts/NN_name.py` -> `eps/NN_name/script.json`
   The helper checks every pose, face and shot name and stops on a mistake. Lines that start with `note:` are style warnings: fix them unless the joke needs it.
2. **Sound**: `./tools/prep.sh NN_name` -> voices, voice check, music bed (about 1 minute).
   Read what it prints. Voice-check lines look like `L07 C 0.71 | want: ... | heard: ...`. Digits for numbers, "a.m." and spelling differences are noise. A real miss (wrong or missing word) is fixed with `python3 tools/tts.py NN_name --force 7`, or by adding `'seed': 1` to that line and running step 1 and `python3 tools/tts.py NN_name` again. "music: none" is fine: the video renders without a bed.
3. **Shot check**: `node tools/render.mjs shots --ep NN_name --qa qa/NN_name --sheet` -> `qa/NN_name/sheet.jpg`. **Open the image and look at it.** One tile per shot, in order. Check: a face is in every tile, Claude's eyes are visible, no shot is an empty wall, the caption does not sit on a face. Fix by changing `shot` on that line and re-running step 1, then `python3 tools/tts.py NN_name` (free, everything is cached) and this step.
4. **Render and finish**: `./tools/make.sh NN_name` -> `out/NN_name.mp4`.
5. **Verify**: `ffprobe -v error -show_entries format=duration -of csv=p=0 out/NN_name.mp4` and pull one or two full-size frames with `node tools/render.mjs stills 3,20 --ep NN_name` (-> `qa/t3.00.jpg`) if anything looked doubtful in step 3.
6. **Report**: the path of the MP4, its length, the character count from step 1, and anything the voice check flagged.

Several episodes: write all the scripts, run step 1 for each, then `./tools/batch.sh NN_a NN_b ...` (prep + render one after another, log in `out/<ep>.log`).

After changing only the wording of a few lines: run step 1, then steps 2-4 again. Only the changed lines are sent to ElevenLabs.

## Script format

```python
#!/usr/bin/env python3
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))
from gen_lib import build, pane

build('04_coffee', 'The Coffee Budget', [
    ('F', '[tired] Claude. How much did I spend on coffee this month?', .45),
    ('C', '[flat] More than on servers.', .4, {'shot': 'Cx'}),
    ('C', '[deadpan] The servers are also tired.', 1.1, 'p'),
    # ...
], ui=dict(panes=[
    pane('Claude · finance', 'Sum the coffee receipts', ['Receipts found: 61', 'Total: $412', 'Servers: $38']),
]), events=[
    dict(line=2, dt=.3, pane=0, typed=True, cps=30, lines=['Coffee: $412', 'Servers: $38']),
], end='cut', music='cozy')
```

A line is `(who, '[tag] spoken text', gap_after_seconds, 'p'?, {overrides}?)`.

- `who`: `'F'` = Pixel (the founder, human), `'C'` = Claude (the robot).
- **Every line starts with one emotion tag in square brackets.** The voice model acts it, and the helper picks pose and face from it. Useful tags: `[deadpan] [flat] [dry] [matter-of-fact] [calm] [softly] [gently] [quietly] [warm] [bright] [tired] [annoyed] [exasperated] [defensive] [panicked whisper] [alarmed] [startled] [horrified] [pleading] [desperate] [hopeful] [relieved] [curious] [confused] [wary] [small] [defeated, quiet] [moved, quiet] [laughs softly]`. Two words in one tag are fine (`[deadpan, softly]`). Never a line that is only a tag.
- `gap`: silence after the line, in seconds. Normal back-and-forth is 0.3-0.5. The last line uses 0.
- `'p'`: punchline. Claude hops, eyes go happy. Use it two to four times per episode.
- Overrides (all optional, the automatic choice is usually right):
  - `f` Pixel pose: `idle talk listen shrug chin facepalm point phone fist slump up lean away duck`
  - `fe` Pixel face: `norm worry shock sad laugh smirk deadpan annoyed shut`
  - `c` Claude pose: `idle talk listen lean tilt flap hunch proud away sad point`
  - `ce` Claude eyes: `norm wide squint flat sad happy up`
  - `shot`: one camera template or `[first, second]`; `split` (0-1) is where the second one cuts in.
    Templates: `F Fx Fp Flow Fm` (Pixel: normal, tight, profile, low, medium), `C Cx Clow Cm` (Claude), `otsF otsC` (over the shoulder), `two twoLow wide hi` (both), `scr` (the screen), `duck` (the rubber duck), `ext` (pull-out, used automatically as the last shot).
  - `hop: True/False`, `hopAt` (seconds into the line), `noBeat: True` (no automatic two-shot in the silence before this line)
  - `cap`: caption text when it should differ from the spoken text. Spoken "nine hundred console logs", shown `900 console.logs`.
  - `seed`: change it (1, 2, ...) to re-roll the voice of that one line.
  - `extra`: mid-line changes, `[{'t': 1.2, 'fe': 'shock'}]` (t = seconds into the line; keys f, fe, c, ce, hop).
- `ui=dict(panes=[...])`: text on the laptop screen behind the characters, up to six `pane(title, prompt, [lines])`. Panes 0-2 are the top row and mostly out of frame; pane 4 (bottom middle) is the one seen behind the characters in two-shots.
- `events=[dict(line=ID, dt=0.3, pane=i, typed=True, cps=30, lines=[...])]`: at line ID (1-based) plus `dt` seconds, pane `i` types new text, with a typing sound. One or two per episode, on the reveal.
- `end`: `'cut'` (hard cut, for a punchline ending) or `'fade'` (soft ending).
- `music`: `'cozy'`, `'sneaky'`, `'tense'`, `'tender'`, `'bounce'`, or your own prompt for an instrumental bed.
- `hideF=<line id>`: Pixel disappears after that line (a lonely ending). Rare.

## Writing rules (this is the style, keep to it)

- **90-135 spoken words, 18-26 lines**, which lands at 50-65 seconds.
- **Line 1 is Pixel and starts with "Claude."** followed by a provocative or absurd line. It is on screen from frame 0 and is the hook.
- Deadpan developer and AI in-jokes. Pixel is a tired indie founder at night; Claude is calm, literal, dry, and secretly kind.
- Escalate with **specific numbers and names** ("nine hundred users", "a folder called backup"), never vague exaggeration.
- Short lines. Most are under 12 words. One idea per line. Let the two interrupt each other.
- **One silent beat**: one line with a gap of 0.85-1.3 s, right after the worst moment and before the turn. The camera cuts to a two-shot there on its own.
- After the beat, a **soft emotional turn**: Claude did something quietly good, or says something true.
- **Last line is a callback or a flip** of something from the first third, said by Claude, tagged `[deadpan, softly]`, with `'p'` and `{'shot': ['Cx', 'two'], 'split': .6}`.
- No call to action, no "follow for more", no on-screen titles. Brand names in jokes: Claude, Codex, GPT only.
- Numbers that must sound right are written as words ("two thousand, one hundred and six") with a `cap` that shows digits.
- Claude has no mouth and never "smiles"; it reacts with eyes, tilt and hops. Do not use Claude pose `away` in a close-up (both eyes vanish): for sulking use `c: 'hunch'` or `c: 'tilt', ce: 'up'`.
- When both characters and the caption must read at once, use `twoLow` instead of `two`.

## The look (fixed by the engine, described here so you can judge the shot check)

- **Pixel**: low-poly founder, faceted pink face, orange triangle nose, dot eyes, black spiky hair, indigo suit, cream block shoes. Sits on the laptop keys, one knee up.
- **Claude**: coral-red block robot, two black vertical slit eyes, small arm blocks, four stub legs, no mouth.
- **World**: the laptop keyboard is the floor, a dark multi-agent app on the laptop screen is the back wall, lamp top left, rubber duck, night window. Violet screen light and a warm lamp, strong vignette, film grain, shallow depth of field, bloom.
- **Camera**: slow push-in on every shot, hard cuts only, about 2.3-2.9 s per shot.
- **Captions**: small off-white sentence at 37% of the height, one sentence at a time, drawn by the engine. Do not add any other text.

## Files

| Path | What it is |
|---|---|
| `scripts/NN_name.py` | One episode script each. The only thing you normally write. |
| `tools/gen_lib.py` | `build()` and `pane()`: checks a script and writes `eps/<ep>/script.json`. |
| `tools/tts.py` | Voices: one cached ElevenLabs request per line -> `eps/<ep>/vo/`, `eps/<ep>/timing.json`, `audio/<ep>/vo.wav`. |
| `tools/vo_check.py` | Voice check: speech-to-text of the voices compared with the script. |
| `tools/music.py` | Music bed from the script's `music` prompt -> `audio/<ep>/music.mp3`. Optional. |
| `tools/prep.sh` | tts + vo_check + music for one episode. |
| `tools/render.mjs` | Renderer: `shots`, `stills`, `info`, `video`, `serve`. |
| `tools/mix.py` | Voices + ducked music + room tone + effects, mastered to -14 LUFS -> `audio/<ep>/mix.wav`. |
| `tools/make.sh` | Render + mix + join -> `out/<ep>.mp4`. |
| `tools/batch.sh` | prep + make for many episodes in turn. |
| `tools/env.py` | Reads `.env`. `python3 tools/env.py` checks the whole setup. |
| `engine/` | The scene: `main.js` (camera, poses, captions), `chars.js`, `set.js`, `ui.js` (laptop screen). |
| `examples/` | Three finished videos: the target. `eps/01_right`, `02_magic`, `03_bill` are their scripts. |

## When something fails

- `No ElevenLabs API key found` / `rejected the API key`: the user must fix `.env`. Stop and say so.
- `Your ElevenLabs plan does not allow this`: library voices over the API and music need a paid plan. Voices: the user sets their own `PIXEL_VOICE_ID` / `CLAUDE_VOICE_ID`. Music: skip it.
- `eps/<ep>/timing.json not found`: the voices have not been made. Run `./tools/prep.sh <ep>`.
- `Could not start Google Chrome`: install Chrome or set `CHROME_PATH` in `.env`.
- `ModuleNotFoundError: numpy`: `python3 -m pip install numpy`.
- `Cannot find package 'playwright-core'`: `npm install`.
- A render that stops midway: run `./tools/make.sh <ep>` again. Voices and music are kept.
- First check for any setup doubt: `python3 tools/env.py`.
