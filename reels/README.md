# Claude and Pixel kit

Make your own "Claude and Pixel" videos: 45-70 second vertical comedy skits (1080x1920, 30 fps) where Pixel, a tired low-poly founder, talks at night to Claude, a small red block robot, on a laptop keyboard.

Everything is made in code. three.js draws the scene, ElevenLabs speaks the lines, ffmpeg joins picture and sound. There is no AI video and no editing app. **You write a script (or ask Claude Code to write it), run four commands, and get an MP4.**

Watch the three videos in `examples/` first. That is exactly what this kit produces.

## What you need

| | |
|---|---|
| Computer | A Mac with Apple silicon (M1 or newer) is what this was built and tested on. Linux and Windows (through WSL) should work but are untested. |
| Google Chrome | The normal desktop app. It renders the frames. |
| Node.js | Version 18 or newer. `node --version` |
| Python | Version 3.9 or newer, with numpy. `python3 --version` |
| ffmpeg | `brew install ffmpeg` on a Mac. `ffmpeg -version` |
| ElevenLabs | An account and an API key. The default voices (Mark and River) are library voices: using them through the API, and making music, needs a paid ElevenLabs plan. |
| Claude Code | Optional but it is the easy way: open this folder in Claude Code and ask for an episode. |

One episode uses about **800-900 ElevenLabs characters** for the voices (the three samples are 797, 762 and 854), plus about one minute of speech-to-text for the voice check and about one minute of music. Both of those are optional.

## Quick start (5 minutes)

Open a terminal in this folder.

```bash
npm install                      # installs the one dependency (playwright-core)
python3 -m pip install numpy     # if you do not have numpy yet
cp .env.example .env             # then open .env and paste your ElevenLabs API key
python3 tools/env.py             # checks the whole setup, spends nothing
```

Every row should say `ok`. Now make the first sample episode with your own key:

```bash
./tools/prep.sh 01_right         # voices + voice check + music     (about 1 minute)
node tools/render.mjs shots --ep 01_right --qa qa/01_right --sheet   # shot check -> qa/01_right/sheet.jpg  (a few seconds)
./tools/make.sh 01_right         # render + mix                     (about 2-4 minutes)
```

Your video is `out/01_right.mp4`. Compare it with `examples/01_right.mp4`.

Want to see a frame before spending any credits? The three samples ship with their timing, so the shot check line above works straight after `npm install`, without a key.

## Make a new episode

### With Claude Code (the intended way)

Open this folder in Claude Code and say, for example:

> make me a new episode about Pixel asking Claude to estimate how long a feature will take

`CLAUDE.md` in this folder teaches Claude the style rules, the script format, the commands and the checks. It writes `scripts/04_....py`, makes the voices, looks at the shot check, renders, and tells you where the MP4 is.

### By hand

1. Copy `scripts/01_right.py` to `scripts/04_myidea.py`, change the episode name in `build('04_myidea', ...)`, and write your lines. The format is explained at the top of `tools/gen_lib.py` and in `CLAUDE.md`.
2. `python3 scripts/04_myidea.py` writes `eps/04_myidea/script.json` (and tells you if a pose or shot name is wrong).
3. `./tools/prep.sh 04_myidea` makes voices, voice check and music.
4. `node tools/render.mjs shots --ep 04_myidea --qa qa/04_myidea --sheet` and look at `qa/04_myidea/sheet.jpg`.
5. `./tools/make.sh 04_myidea` writes `out/04_myidea.mp4`.

### Many at once

Write the scripts, run each one (step 2), then:

```bash
caffeinate -dimsu ./tools/batch.sh 04_myidea 05_other 06_third
```

It does the sound prep and the render for each episode in turn and keeps a log per episode in `out/`.

### Live preview

`npm run preview` prints a link per episode. Open it in Chrome, press play, drag the slider. Picture only, no sound.

## What every file is for

```
claude-and-pixel-kit/
  README.md            this file
  CLAUDE.md            instructions for Claude Code: style rules, script format, commands, checks
  .env.example         copy to .env; your API key and the two voice IDs go there
  package.json         the one Node dependency, plus "npm run doctor" and "npm run preview"
  requirements.txt     the one Python dependency (numpy)
  LICENSES.md          licences of three.js and the fonts
  index.html           the page Chrome renders (also used by the live preview)
  .claude/settings.json  stops Claude Code from reading your .env
  scripts/             one file per episode: this is what you write
    01_right.py          sample "Absolutely Right"
    02_magic.py          sample "react-magic-fix"
    03_bill.py           sample "The Bill"
  eps/<episode>/       made by the tools
    script.json          the script as data (from scripts/<episode>.py)
    timing.json          when every line and word is spoken (from tools/tts.py)
    vo/                  one cached voice file per line
  audio/
    sfx/                 nine shared sounds: room tone, typing, pop, whoosh, robot chirps
    <episode>/           vo.wav, music.mp3, mix.wav for that episode
  tools/
    gen_lib.py           script helper: build() and pane(), checks names, writes script.json
    env.py               reads .env; "python3 tools/env.py" checks your setup
    tts.py               voices (ElevenLabs, one request per line, cached)
    vo_check.py          voice check: did the voice say what the script says?
    music.py             music bed from the script's music prompt (optional)
    prep.sh              tts + vo_check + music for one episode
    render.mjs           renderer: shots, stills, info, video, serve
    mix.py               voices + music + room tone + effects, mastered to -14 LUFS
    make.sh              render + mix + join -> out/<episode>.mp4
    batch.sh             prep + make for many episodes, one after another
  engine/              the scene, in three.js
    main.js              timeline, poses, camera and shot planner, captions
    chars.js             Pixel and Claude
    set.js               keyboard, laptop, lamp, duck, window, lights
    ui.js                the app on the laptop screen
  lib/                 three.js r164 (only the parts the engine uses)
  fonts/               Inter and JetBrains Mono
  examples/            three finished videos (smaller files than a fresh render, same picture)
  out/                 your finished videos (created on first render)
  qa/                  shot-check images (created on first check)
```

## Change the voices

Open `.env` and replace the IDs:

```
PIXEL_VOICE_ID=...     # the founder
CLAUDE_VOICE_ID=...    # the robot
```

A voice ID is the code you get from "Copy voice ID" on any voice in your ElevenLabs account (a library voice has to be added to "My Voices" first; your own cloned voice works too). Then run `./tools/prep.sh <episode>` again. A changed voice is a new voice file, so those lines are generated and billed again.

Other settings in `.env`:

- `ELEVENLABS_MODEL_ID`: the voice model. `eleven_v4` acts the `[emotion tags]` in the scripts. If your account does not have it, try `eleven_v3`.
- `APP_NAME`: the app name on the laptop screen (default `Morphy`). Run the script again (`python3 scripts/<episode>.py`) after changing it.
- `CHROME_PATH`: full path to Chrome if it is not in the normal place.

How steady or lively each voice is can be tuned in `tools/gen_lib.py` (`VOICES`, `stability`: lower is more expressive).

One line sounds wrong? `python3 tools/tts.py <episode> --force 7` makes line 7 again. For a different take, add `{'seed': 1}` to that line in the script, run the script, then `python3 tools/tts.py <episode>`.

## Music

`tools/music.py` asks ElevenLabs Music for one instrumental bed per episode from the script's `music=` setting (`cozy`, `sneaky`, `tense`, `tender`, `bounce`, or your own description). This needs a paid ElevenLabs plan.

Music is optional. If the step fails or you skip it, the video is mixed with voices, room tone and sound effects only. To use your own track, save any instrumental as `audio/<episode>/music.mp3` before `./tools/make.sh`. It is turned down under the voices automatically.

## Troubleshooting

| You see | Do this |
|---|---|
| `No ElevenLabs API key found` | `cp .env.example .env`, paste your key after `ELEVENLABS_API_KEY=`, no quotes. |
| `ElevenLabs rejected the API key` | The key is wrong, or restricted. Give it Text to Speech (and Speech to Text, Music) access in ElevenLabs. |
| `Your ElevenLabs plan does not allow this` | Library voices over the API and music need a paid plan. Use your own voice IDs, skip the music. |
| `Your account cannot use this voice model` | Set `ELEVENLABS_MODEL_ID` in `.env` to a model you have. |
| `SSL: CERTIFICATE_VERIFY_FAILED` | Your Python has no certificates. On a Mac the tools already point to the system ones. Otherwise `python3 -m pip install certifi` and `export SSL_CERT_FILE=$(python3 -m certifi)`. |
| `ModuleNotFoundError: No module named 'numpy'` | `python3 -m pip install numpy` (add `--break-system-packages` on Homebrew Python if pip refuses). |
| `Cannot find package 'playwright-core'` | Run `npm install` in this folder. |
| `Could not start Google Chrome` | Install Chrome, or set `CHROME_PATH=` in `.env` to its full path. |
| `permission denied: ./tools/make.sh` | `chmod +x tools/*.sh` |
| `eps/<ep>/timing.json not found` | The voices are not made yet: `./tools/prep.sh <ep>`. |
| Render is very slow (more than 1 s per frame) | Chrome is not using the graphics chip. Close other heavy apps, plug in the laptop, and do not run two renders at once. |
| The video is silent or the render stopped | Run `./tools/make.sh <ep>` again. Voices and music are kept, only the render repeats. |
| A word is mispronounced | Write it the way it sounds in the spoken text and put the correct spelling in `cap` (see `scripts/02_magic.py`). |
| Voice check lists a line | Numbers heard as digits and spelling differences are fine. A missing or wrong word: make that line again with `--force`. |

Still stuck? Run `python3 tools/env.py` and read the rows that say `FAIL`.
