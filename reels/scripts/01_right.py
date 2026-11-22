#!/usr/bin/env python3
"""Sample episode 1, "Absolutely Right": two typed screen gags, hard-cut ending, bouncy bed.
Run:  python3 scripts/01_right.py   -> eps/01_right/script.json"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))
from gen_lib import build, pane

build('01_right', 'Absolutely Right', [
    ('F', '[annoyed] Claude. Stop saying I\'m absolutely right.', .4),
    ('C', '[bright] You\'re absolutely right.', .35, {'shot': 'Cx'}),
    ('F', '[exasperated] That! Stop doing that!', .3, {'shot': 'Fx'}),
    ('C', '[matter-of-fact] Understood. Great point.', .4, {'shot': 'Cx'}),
    ('F', '[flat, curt] No compliments. At all.', .35),
    ('C', '[dry] Okay. Your idea is bad.', .45, {'shot': 'Cx'}),
    ('F', '[startled] ...Which idea?', .3, {'shot': 'Fx'}),
    ('C', '[flat] Storing the passwords in a spreadsheet.', .35),
    ('F', '[defensive] It\'s a private spreadsheet.', .3),
    ('C', '[deadpan] It\'s called "passwords." It\'s shared with "anyone with the link."', 1.2, 'p'),
    ('F', '[quietly] ...What else is bad?', .4),
    ('C', '[matter-of-fact] The logo. The pricing. The word "synergy" on the homepage. Twice.', .4),
    ('F', '[pained] Okay. Okay, stop.', .3, {'f': 'facepalm', 'shot': 'Fx'}),
    ('C', '[dry] You asked for honesty.', .35, {'shot': 'Cx'}),
    ('F', '[small] I asked for a little honesty.', .9),
    ('C', '[gently] ...The app is good, though.', .6, {'shot': 'Cx'}),
    ('F', '[hopeful] ...Really?', .4, {'shot': 'Fx', 'f': 'lean'}),
    ('C', '[softly] Really. I wouldn\'t say it otherwise. Not anymore.', .9),
    ('F', '[warm] ...Thanks, Claude.', .5, {'shot': 'Fx'}),
    ('C', '[deadpan, softly] You\'re absolutely welcome.', 0, 'p', {'shot': ['Cx', 'two'], 'split': .6}),
], ui=dict(panes=[
    pane('Claude · review', 'Be honest about my idea', ['You\'re absolutely right!', 'Great point!', 'Excellent question!']),
    pane('Codex · audit', 'Where are the passwords?', ['Found: passwords.xlsx', 'Sharing: anyone with the link', 'Viewers right now: 3']),
    pane('Claude · homepage', 'Count the word "synergy"', ['synergy: 2', 'leverage: 4', 'Recommend: delete']),
]), events=[
    dict(line=6, dt=.3, pane=0, typed=True, cps=30, lines=['Honesty mode: on', 'Your idea is bad.']),
    dict(line=20, dt=.3, pane=0, typed=True, cps=26, lines=['Honesty mode: on', 'The app is good.', 'You\'re absolutely welcome.']),
], end='cut', music='bounce')
