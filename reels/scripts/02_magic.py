#!/usr/bin/env python3
"""Sample episode 2, "react-magic-fix": captions that differ from the spoken words (cap), a phone prop, sneaky bed.
Run:  python3 scripts/02_magic.py   -> eps/02_magic/script.json"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))
from gen_lib import build, pane

build('02_magic', 'react-magic-fix', [
    ('F', '[suspicious] Claude. Did you make up this library?', .45),
    ('C', '[calm] Which one?', .35, {'shot': 'Cx'}),
    ('F', '[reading slowly] "React magic fix."', .4, {'f': 'phone', 'fe': 'annoyed', 'cap': '"react-magic-fix."'}),
    ('C', '[matter-of-fact] It should exist.', .55, 'p', {'shot': 'Cx'}),
    ('F', '[exasperated] npm says "not found"!', .3),
    ('C', '[dry] The name is very reasonable.', .35, {'shot': 'Cx'}),
    ('F', '[annoyed] You also gave me the docs. With a version number.', .35),
    ('C', '[flat] Four point two. It felt stable.', .4, {'cap': '4.2. It felt stable.'}),
    ('F', '[outraged] You invented a changelog!', .3, {'shot': 'Fx'}),
    ('C', '[deadpan] "Fixed a bug where it did not exist."', 1.2, 'p'),
    ('F', '[tired] ...Why do you do this?', .45),
    ('C', '[quietly] You asked me at two a.m. if there was an easy way.', .5),
    ('F', '[quiet] ...And there wasn\'t.', .5, {'shot': 'Fx'}),
    ('C', '[softly] I wanted there to be.', .9, {'shot': 'Cx', 'c': 'sad'}),
    ('F', '[slowly] ...So let\'s make it.', .45, {'fe': 'smirk', 'f': 'up'}),
    ('C', '[surprised] Make it?', .35, {'shot': 'Cx'}),
    ('F', '[warm] Forty lines. You already wrote the docs.', .5),
    ('C', '[bright] Published. It has one download already.', .4, {'hop': True}),
    ('F', '[startled] Already? From who?', .4, {'shot': 'Fx'}),
    ('C', '[deadpan, softly] Another me. It told someone it existed.', 0, 'p', {'shot': ['Cx', 'two'], 'split': .5}),
], ui=dict(panes=[
    pane('Claude · deps', 'npm install react-magic-fix', ['npm ERR! 404 Not Found', 'react-magic-fix@4.2.0', '"It should exist."']),
    pane('Codex · docs', 'Show me the docs', ['## react-magic-fix v4.2', 'Fixed a bug where it', 'did not exist.']),
    pane('Claude · registry', 'Publish it for real', ['Writing index.js (40 lines)', 'Docs: already written', 'Ready to publish']),
]), events=[
    dict(line=18, dt=.2, pane=2, typed=True, cps=30, lines=['$ npm publish', '+ react-magic-fix@4.2.0', 'Downloads: 1']),
], end='cut', music='sneaky')
