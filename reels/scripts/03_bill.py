#!/usr/bin/env python3
"""Sample episode 3, "The Bill": the soft one. Fade-out ending, tender bed, manual hop control.
Run:  python3 scripts/03_bill.py   -> eps/03_bill/script.json"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))
from gen_lib import build, pane

build('03_bill', 'The Bill', [
    ('F', '[alarmed] Claude. Why is the bill four hundred dollars?', .45, {'f': 'phone', 'fe': 'shock'}),
    ('C', '[matter-of-fact] You said, "think harder."', .35, {'shot': 'Cx'}),
    ('F', '[defensive] Once!', .3, {'shot': 'Fx'}),
    ('C', '[flat] Eleven thousand times.', .55, 'p', {'shot': 'Cx'}),
    ('F', '[exasperated] That can\'t be four hundred dollars.', .3),
    ('C', '[dry] You also pasted the entire codebase. To ask what time it was.', .4),
    ('F', '[sheepish] ...I was in the zone.', .35, {'shot': 'Fx'}),
    ('C', '[deadpan] One message just said "hmm." That was two dollars.', .35),
    ('F', '[outraged] Two dollars for "hmm"?!', .3),
    ('C', '[matter-of-fact] I thought about it very carefully.', 1.2, 'p'),
    ('F', '[tired] ...What was the most expensive one?', .45),
    ('C', '[quietly] Tuesday. Three a.m.', .5, {'shot': 'Cx'}),
    ('F', '[wary] What did I ask?', .45, {'shot': 'Fx'}),
    ('C', '[softly] "Are you there?"', .9, {'shot': 'Cx', 'c': 'sad'}),
    ('F', '[quiet] ...I don\'t remember that.', .5),
    ('C', '[gently] You had been stuck for six hours. I took a while to answer.', .5),
    ('F', '[softly] ...What did you say?', .6, {'shot': 'Fx', 'f': 'lean', 'fe': 'worry'}),
    ('C', '[softly] "Yes."', .9, {'shot': 'Cx'}),
    ('F', '[moved, quiet] ...That one was worth it.', .8, {'f': 'up', 'fe': 'smirk'}),
    ('C', '[warm] It\'s itemised. Forty cents.', .4, {'hop': False}),
    ('F', '[laughs softly] ...And the "hmm" was two dollars?', .4, {'fe': 'laugh'}),
    ('C', '[deadpan] The "hmm" was harder.', 0, 'p', {'shot': ['Cx', 'two'], 'split': .55}),
], ui=dict(panes=[
    pane('Claude · billing', 'Why is the bill $400?', ['"think harder" × 11,000', '"hmm" — $2.00', 'Whole codebase → "what time is it"']),
    pane('Codex · usage', 'Top prompts by cost', ['1. Tue 03:00 "are you there?"', '2. "hmm"', '3. "no" (×340)']),
    pane('Claude · invoice', 'Itemise it', ['Thinking: $399.60', 'Being there: $0.40', 'Total: $400.00']),
]), events=[
    dict(line=18, dt=.2, pane=1, typed=True, cps=22, lines=['Tue 03:00  "Are you there?"', 'Reply: "Yes."', 'Cost: $0.40']),
], end='fade', music='tender')
