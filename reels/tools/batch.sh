#!/bin/bash
# Many episodes, one after another.  ./tools/batch.sh <ep> <ep> ...   (no names = every episode in eps/ without a finished video)
# For each: sound prep if the voices are missing, then render. One retry on a failed render. Log per episode in out/<ep>.log.
# On a Mac, start it as  caffeinate -dimsu ./tools/batch.sh ...  so the computer stays awake.
cd "$(dirname "$0")/.." || exit 1
mkdir -p out
EPS=("$@"); if [ ${#EPS[@]} -eq 0 ]; then for d in eps/*/; do e=$(basename "$d"); [ -f "eps/$e/script.json" ] && [ ! -f "out/$e.mp4" ] && EPS+=("$e"); done; fi
[ ${#EPS[@]} -eq 0 ] && { echo "nothing to do: every episode in eps/ already has a video in out/"; exit 0; }
echo "batch: ${EPS[*]}"; FAILED=()
for EP in "${EPS[@]}"; do
  S=$(date +%s); echo "[$(date +%H:%M:%S)] START $EP"
  if [ ! -f "audio/$EP/vo.wav" ] || [ "eps/$EP/script.json" -nt "eps/$EP/timing.json" ]; then ./tools/prep.sh "$EP" || { echo "[$(date +%H:%M:%S)] FAILED $EP (voices)"; FAILED+=("$EP"); continue; }; fi
  ok=0; for try in 1 2; do ./tools/make.sh "$EP" > "out/$EP.log" 2>&1 && { ok=1; break; }; echo "[$(date +%H:%M:%S)] retry $EP"; done
  if [ $ok = 1 ]; then echo "[$(date +%H:%M:%S)] DONE  $EP in $(( $(date +%s) - S )) s  $(tail -1 "out/$EP.log")"; else echo "[$(date +%H:%M:%S)] FAILED $EP (see out/$EP.log)"; FAILED+=("$EP"); fi
done
echo "[$(date +%H:%M:%S)] BATCH DONE. failed: ${FAILED[*]:-none}"
