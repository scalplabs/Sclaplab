# 막차 47 · HyperFrames 프로젝트 지시서

세로 숏폼 시리즈 "막차 47"(2호선 막차 데스게임, 시청자가 참가자 47번). 1080x1920, 30fps.
PART 1 결과물: `out/makcha47_part1.mp4` (44.33초, 무음).

## 폴더 구성

- `index.html` : 루트. 장면 10개 + HUD + 자막을 시간 순서로 올려놓기만 한다(하드컷).
- `compositions/s01-phone.html` ~ `s10-end.html` : 장면 하나당 파일 하나. 안에 `<canvas>` 하나가 있고,
  그림은 `assets/makcha-engine.js` 가 그린다(hosted). 화면 속 글자(문자 내용, 말풍선, 선택지, 엔딩 문구)는
  `<canvas data-...>` 속성을 고치면 바뀐다.
- `compositions/captions.html` : 자막 전체. HTML 글자라 Studio 에서 직접 고칠 수 있다.
  한 줄이 자막 한 덩어리, `data-start` 는 영상 전체 기준 초, 노란 강조는 `<span class="hl">`.
- `compositions/hud.html` : 좌상단 HUD("100명 남음" / "상금 ₩0"). HTML 글자.
- `compositions/s04-prize.html`, `s05-station.html` : 숫자판 글자(100, 상금 카운트업, 99, 역 이름)도 HTML.
- `assets/makcha-engine.js` : 졸라맨, 열차 배경, 휴대폰, 스피커, 손 클로즈업 그림 코드.
  `reference/막차47_영상엔진.html` 의 그림 코드를 그대로 옮긴 것이니 그림체를 바꾸지 말 것.
- `assets/fonts/` : Noto Sans KR, JetBrains Mono (OFL). 이 환경에는 한글 폰트가 없어서 프로젝트에 넣어 둠.
- `reference/` : 원본 엔진 html, 레퍼런스 분석/대본 가이드. 원본 mp4 는 용량 때문에 저장소에 없음
  (비교하려면 `reference/막차47_PART1_원본.mp4` 로 넣는다).
- `TRANSLATION_NOTES.md` : 원본과 달라진 점.

## PART 1 장면 시작 시간 (초)

| 장면 | 파일 | 시작 | 길이 |
|---|---|---|---|
| 1 휴대폰 문자 | s01-phone | 0.00 | 4.00 |
| 2 막차 안에서 깨어남 | s02-wake | 4.00 | 4.81 |
| 3 안내방송 스피커 | s03-speaker | 8.81 | 7.47 |
| 4 숫자판: 상금 0 → 1억 | s04-prize | 16.28 | 3.96 |
| 5 첫 번째 역: 100 → 99 | s05-station | 20.24 | 2.16 |
| 6 문, 23번 사라짐 | s06-door | 22.40 | 3.75 |
| 7 12번의 귓속말 | s07-whisper | 26.15 | 6.03 |
| 8 손 클로즈업, 피 | s08-hand | 32.18 | 4.23 |
| 9 선택지 A / B | s09-choice | 36.41 | 3.72 |
| 10 엔딩 | s10-end | 40.13 | 4.20 |

## 타이밍을 바꿀 때 (세 군데를 같이 고친다)

1. `index.html` 의 해당 장면 `data-start` / `data-duration`, 그리고 루트 `data-duration`
2. 그 장면 파일 맨 아래 `Makcha.mount(..., { start, dur })` (같은 값)
3. `compositions/captions.html` 의 자막 `data-start` / `data-duration`, `compositions/hud.html` 의 HUD 구간

자막 길이 규칙(원본 엔진과 동일): 한 덩어리 = 0.42초 + 글자 수 x 0.16초. 장면 길이 = 자막 합 + 여유(기본 0.25초).

## 스펙

- 자막: 화면 60% 높이(2번 장면 80%, 9번 장면 74%), 1~3단어씩, 굵기 900 흰 글씨 + 검은 외곽선 18px,
  강조 단어 노란색 #ffd84a, 등장할 때 1.18배 → 1배 팝(0.12초)
- HUD: 좌상단 큰 숫자 + "명 남음", 아래 모노스페이스 "상금 ₩". 4번 장면에서 상금 0 → 100,000,000,
  5번 장면에서 100 → 99 + 빨간 플래시(이 두 장면은 화면 전체가 숫자판이라 좌상단 HUD 는 숨김)
- 내레이션: `assets/narration.mp3` 를 넣고 `index.html` 아래쪽 `<audio>` 주석을 풀면 오디오 트랙이 된다.
  그다음 `npx hyperframes transcribe assets/narration.mp3 --model small --language ko` 로 말하는 시간을 뽑아
  자막 `data-start` 와 장면 길이를 녹음에 맞춘다. 파일이 없으면 무음.

## 완료 기준

- `npm run check` 오류 0.
- 각 장면 중간 프레임을 원본과 비교: `npx hyperframes diff reference/막차47_PART1_원본.mp4 . --at <초,...>`
- 렌더: `npx hyperframes render -o out/makcha47_partN.mp4 -q delivery`
- 끝나면 결과 경로와 장면별 시작 시간을 보고.

## 다음 편 규칙

- "PART N 만들어줘 + 댓글 1등 선택"을 받으면: 그 댓글 화면으로 오프닝, 이전 편 마지막 남은 인원/상금에서 시작
  (PART 1 끝: 99명, ₩100,000,000), 스타일과 구성은 PART 1 과 동일, 끝은 A/B 선택지 +
  "댓글 1등이 PART N+1을 정한다" 엔딩.
- 새 그림이 필요하면 `assets/makcha-engine.js` 의 `SCENES` 에 장면 함수를 추가하고(시간 t 만으로 그릴 것,
  난수/시계 금지) 장면 파일에서 그 이름으로 mount 한다.

---

# HyperFrames Composition Project

This folder is a [HyperFrames](https://hyperframes.heygen.com) video: HTML, CSS and seekable
animations (GSAP by default) that the `hyperframes` CLI previews in the browser and renders to
MP4.

## Skills — read these first

**Invoke the relevant skill before writing or modifying compositions.** Skills encode framework-specific patterns (e.g., `window.__timelines` registration, `data-*` attribute semantics, shader-compatible CSS rules) that generic web docs don't cover, so compositions written without them break.

**Doing anything with HyperFrames?** Start at `/hyperframes`. Make any video by asking for it; the `/hyperframes` skill carries the contract and the references (each kind of film, story, motion, look, sound, review, captions, overlays). Read it first, especially when there's no project context to orient you.

- `/hyperframes` — read first for any request to make, edit, animate or render a video, motion graphic, captions or overlays. Holds the render contract and the work loop.
- `/hyperframes-cli` — the CLI by job: scaffold, check, look at frames, edit the timeline, preview, render, publish, project history.
- `/hyperframes-registry` — ready-made blocks and components installed as editable source. Search it before hand-building any named visual.
- `/media-use` — get or make any media (music, sound effects, images, voiceover, avatar and generated video, transcripts, cutouts, colour grades) and mix placed audio.
- `/reverse-any-video` — rebuild any video file as an editable HyperFrames project and check it against the original frame by frame (HyperFrames Pro).
- `/style-sampling` — make a new episode on your topic in one of five proven styles (HyperFrames Pro).
- `/figma` — bring a Figma design, frame, logo or brand into a video.
- `/slideshow` — a presentation or pitch deck. Output is a navigable deck, not a rendered MP4.
- `/remotion-to-hyperframes` — bring existing video code or footage into HyperFrames (Remotion first; also Motion Canvas, Lottie, Three.js, canvas, or renders from other tools) and verify it frame by frame against the original.

**Changing how real footage or images look or reveal?** Load `/media-use` and read its `references/media-treatments.md` before editing, even when the request only says dark, flat, boring, retro, private, or “make the reveal cooler.” It governs how footage is treated, never whether media may be used. Use canonical media treatments and seek-safe motion; do not improvise equivalent CSS/SVG filters or overlays.

> **Tailwind v4 projects** (`hyperframes init --tailwind`): see `hyperframes-cli/references/init-and-scaffold.md` (Tailwind).

> **Using a HyperFrames plugin?** Load skills from that installed bundle and follow
> its `hyperframes/references/plugin-installation.md` execution rules. The person updates
> the plugin through its plugin manager; the standalone commands below do not apply.
>
> **Standalone skill missing or stale?** Installing and updating skills is the person's step:
> tell them which skill is missing or stale, and do not run the install yourself. For the user:
> `npx hyperframes skills update <name>` installs/refreshes that skill, and bare
> `npx hyperframes skills update` refreshes the core set plus everything already installed —
> neither pulls the full set. Newly installed skills load in a new agent session.

## Commands

```bash
npm run dev          # human-operated foreground preview (blocks until stopped)
npx hyperframes preview --background  # agent-safe persistent Studio preview
npx hyperframes preview --status      # verify the persistent preview is listening
npx hyperframes preview --stop        # stop it when review is finished
npm run check        # lint + runtime + layout + motion + contrast (one command)
npx hyperframes snapshot --at 1,3,5  # PNG frames at those seconds, to look at before rendering
npm run render       # render to MP4
npm run publish      # publish and get a shareable link
npx hyperframes lint --verbose  # include info-level findings
npx hyperframes lint --json     # machine-readable output for CI
npx hyperframes docs <topic> # reference docs in terminal
```

> **Agents must use `npx hyperframes preview --background` for Studio handoff.** Do not rely
> on a shell/tool `run_in_background` wrapper around `npm run dev`: that foreground process
> remains owned by the invoking session and can disappear while the browser stays open,
> leaving refreshes at `ERR_CONNECTION_TIMED_OUT`. Verify with `preview --status`. The desktop
> app can't edit the project while this preview runs, so `npx hyperframes open` stops it first.
> If you hand the project to the app another way, run `preview --stop` before you do. Otherwise keep it
> alive through review, and stop it explicitly with `preview --stop` afterward.

> **Back from the desktop app.** Once this project was opened in the HyperFrames desktop app, run `npx hyperframes catch-up` before your next change here: it lists what the person asked Framey in the app and which files changed since.

> **Pinned CLI version.** These scripts pin an exact `hyperframes@X.Y.Z` so this project re-renders identically over time. Weeks later that pin lags fixes shipped since. To move up: `npx hyperframes@latest upgrade --project . --check` (shows the delta), then `npx hyperframes@latest upgrade --project .` to rewrite the pins. Always unpinned — the pinned script re-runs the old version against itself.

## Documentation

**For quick reference**, use the local CLI docs command (no network required):

```bash
npx hyperframes docs <topic>
```

Topics: `data-attributes`, `gsap`, `compositions`, `rendering`, `examples`, `troubleshooting`

**For full documentation**, discover pages via the machine-readable index — do NOT guess URLs:

```
https://hyperframes.heygen.com/llms.txt
```

## Project Structure

- `index.html` — main composition (root timeline)
- `compositions/` — sub-compositions referenced via `data-composition-src`
- `meta.json` — project metadata (id, name)
- `transcript.json` — whisper word-level transcript (if generated)

## Linting — ALWAYS RUN AFTER CHANGES

After creating or editing any `.html` composition, **always** run the full check before considering the task complete:

```bash
npm run check
```

Fix all errors before presenting the result. Warnings should be reviewed before rendering.

Then look at what you changed: `npx hyperframes snapshot --at <seconds>` (or `--range START,END`, `--composition <id>`) at the moments you edited, and read the frames before you reply. A passing check does not show how it looks.

## Key Rules

1. Every timed element needs `data-start` and a duration. `data-start` is what marks it as timed; `data-track-index` is an optional Studio display lane the render never reads
2. Give timed visual elements `class="clip"`. The framework keys visibility off `data-start`, not the class, but the shared `.clip` CSS is what gives a scene its full-frame box, and `lint` warns without it
3. Register one paused root timeline per composition on `window.__timelines`:
   ```js
   window.__timelines = window.__timelines || {};
   window.__timelines["composition-id"] = gsap.timeline({ paused: true });
   ```
   Scene timelines manually added to this root must not be paused. A paused
   child does not advance when the root is seeked. The runtime activates
   registered composition siblings, not arbitrary nested scene timelines.
4. A video with sound keeps it on the `<video>` (`data-has-audio="true"`, no `muted`). Use a separate `<audio>` for music, voiceover, replacement audio, J/L cuts, or audio detached in Studio. Silent footage and b-roll: `muted`.
5. Sub-compositions use `data-composition-src="compositions/file.html"` to reference other HTML files
6. Only deterministic logic — no `Date.now()`, no `Math.random()`, no network fetches
