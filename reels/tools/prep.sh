#!/bin/bash
# Sound prep.  ./tools/prep.sh <ep>  ->  voices (tts.py), voice check (vo_check.py), music bed (music.py)
# Only the voices are required. A failed voice check or a missing music bed is reported and the episode still works.
cd "$(dirname "$0")/.." || exit 1
EP=$1; [ -z "$EP" ] && { echo "usage: ./tools/prep.sh <ep>   (for example ./tools/prep.sh 01_right)"; exit 1; }
[ -f "eps/$EP/script.json" ] || { echo "eps/$EP/script.json not found. Write the script first: python3 scripts/$EP.py"; exit 1; }
mkdir -p "audio/$EP"
python3 tools/tts.py "$EP" > "eps/$EP/tts.log" 2>&1 || { echo "$EP: VOICES FAILED"; tail -4 "eps/$EP/tts.log"; exit 1; }
echo "$EP voices: $(tail -1 "eps/$EP/tts.log")"
python3 tools/vo_check.py "$EP" > "eps/$EP/vo_check.txt" 2>&1; echo "$EP voice check: $(tail -1 "eps/$EP/vo_check.txt")"
[ "$(grep -c '^L' "eps/$EP/vo_check.txt")" -gt 0 ] && grep '^L' "eps/$EP/vo_check.txt"
python3 tools/music.py "$EP" > "audio/$EP/music.log" 2>&1 && echo "$EP music: $(tail -1 "audio/$EP/music.log")" || { echo "$EP music: none (optional)"; head -2 "audio/$EP/music.log"; }
exit 0
