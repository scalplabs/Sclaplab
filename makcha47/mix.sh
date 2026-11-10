#!/usr/bin/env bash
# Mix narration + BGM + subway ambience + elimination hit into audio/mix.mp3.
# Run after `node build.mjs` (it writes audio/timing.json).
set -euo pipefail
cd "$(dirname "$0")"

TOTAL=$(node -p "require('./audio/timing.json').total")
HIT_MS=$(node -p "Math.round(require('./audio/timing.json').hit*1000)")
FADE_ST=$(node -p "(require('./audio/timing.json').total-2).toFixed(3)")

# Levels (dB): voice on top, music and train under it and ducked further while the voice speaks.
BGM_DB=${BGM_DB:--7}
SUBWAY_DB=${SUBWAY_DB:--13}
HIT_DB=${HIT_DB:--2}

ffmpeg -v error -y \
  -i narration.mp3 \
  -i audio/bgm/bgm1.mp3 \
  -stream_loop -1 -i audio/bgm/subway1.mp3 \
  -i audio/bgm/hit1.mp3 \
  -filter_complex "
    [0:a]aresample=44100,apad,atrim=0:${TOTAL},asplit=2[voice][sc];
    [1:a]aresample=44100,atrim=0:${TOTAL},volume=${BGM_DB}dB[bgm];
    [2:a]aresample=44100,atrim=0:${TOTAL},volume=${SUBWAY_DB}dB[sub];
    [bgm][sub]amix=inputs=2:normalize=0[bed];
    [bed][sc]sidechaincompress=threshold=0.03:ratio=4:attack=20:release=400:makeup=1[ducked];
    [3:a]aresample=44100,volume=${HIT_DB}dB,adelay=${HIT_MS}|${HIT_MS}[hit];
    [voice][ducked][hit]amix=inputs=3:normalize=0:duration=first,
      afade=t=out:st=${FADE_ST}:d=2,loudnorm=I=-14:TP=-1.5:LRA=11[out]" \
  -map "[out]" -t "${TOTAL}" -ar 44100 -b:a 192k audio/mix.mp3

echo "audio/mix.mp3 (${TOTAL}s, hit at ${HIT_MS}ms)"
