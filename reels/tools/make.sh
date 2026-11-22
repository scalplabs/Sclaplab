#!/bin/bash
# Render + finish.  ./tools/make.sh <ep>  ->  out/<ep>.mp4
# Renders every frame in Chrome (about 2-4 minutes per minute of video on an Apple-silicon Mac), mixes the sound, joins both.
# Needs the voices first (tools/prep.sh or tools/tts.py). Music is optional.
cd "$(dirname "$0")/.." || exit 1
EP=$1; [ -z "$EP" ] && { echo "usage: ./tools/make.sh <ep>   (for example ./tools/make.sh 01_right)"; exit 1; }
[ -f "eps/$EP/timing.json" ] && [ -f "audio/$EP/vo.wav" ] || { echo "$EP has no voices yet. Run: ./tools/prep.sh $EP"; exit 1; }
mkdir -p out
if [ "$(uname)" = "Darwin" ]; then ENC="--enc vt --bv 24M"; else ENC="--enc x264 --crf 16 --preset medium"; fi   # Apple hardware encoder on a Mac, x264 elsewhere
S=$(date +%s)
nice -n 12 node tools/render.mjs video "out/${EP}_v.mp4" --ep "$EP" --cap blob $ENC || { echo "render failed"; exit 1; }
python3 tools/mix.py "$EP" || { echo "mix failed"; exit 1; }
nice -n 12 ffmpeg -v error -y -i "out/${EP}_v.mp4" -i "audio/$EP/mix.wav" -map 0:v -map 1:a -c:v copy -c:a aac -b:a 256k -ar 48000 -shortest -movflags +faststart "out/$EP.mp4" || exit 1
rm -f "out/${EP}_v.mp4"
echo "out/$EP.mp4  $(ffprobe -v error -show_entries format=duration -of csv=p=0 "out/$EP.mp4") s  made in $(( $(date +%s) - S )) s"
