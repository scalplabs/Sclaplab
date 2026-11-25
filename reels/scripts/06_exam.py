#!/usr/bin/env python3
"""EP03 "시험": 김대리 + 클로드. 수능 AI 부정행위 뉴스를 계기로, AI로 시험을 '보는' 대신 '준비하는' 법 3가지.
Run:  python3 scripts/06_exam.py   -> eps/06_exam/script.json"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))
from gen_lib import build, pane

build('06_exam', '시험', [
    ('F', '[hopeful] 클로드. 다음 주 승진시험, 너 안경에 넣어 가도 돼?', .45),
    ('C', '[flat] 안 돼요.', .35, {'shot': 'Cx'}),
    ('F', '[defensive] 왜! 너 똑똑하잖아.', .3),
    ('C', '[matter-of-fact] 이번 수능에서 그거 하다 걸린 뉴스 보셨잖아요.', .35),
    ('C', '[dry] 형사고발까지 갔어요.', .4, 'p', {'shot': 'Cx'}),
    ('F', '[defensive] 승진시험은 수능이 아니잖아.', .3),
    ('C', '[deadpan] 감독관이 부장님이세요.', .45, 'p', {'shot': 'Cx'}),
    ('F', '[alarmed] ...부장님이 내 안경을 왜 봐.', .3, {'shot': 'Fx'}),
    ('C', '[deadpan] 그 뉴스, 단톡방에 세 번 올리셨어요.', .4),
    ('F', '[defeated, quiet] ...그럼 나 어떡해.', 1.2, {'f': 'listen', 'fe': 'sad'}),
    ('C', '[gently] 시험장엔 못 가요. 대신 오늘 밤, 세 가지만 해요.', .4, {'shot': 'Cx', 'noBeat': True}),
    ('C', '[calm] 하나. 기출 주고, "같은 유형으로 모의고사 만들어 줘."', .35),
    ('F', '[small] ...응.', .3, {'shot': 'Fx', 'f': 'listen', 'fe': 'worry'}),
    ('C', '[calm] 둘. 틀린 건 "왜 틀렸는지, 뭘 다시 볼지 알려 줘."', .35),
    ('C', '[matter-of-fact] 셋. 다 풀면 "내가 자주 틀리는 유형만 정리해 줘."', .4),
    ('F', '[hopeful] 그럼 진짜 붙어?', .35, {'shot': 'Fx', 'f': 'lean'}),
    ('C', '[dry] 약점 하나는 벌써 나왔어요.', .35),
    ('F', '[wary] 뭔데.', .3, {'shot': 'Fx'}),
    ('C', '[deadpan] 모르면 삼번만 고르시는 거요.', .5, 'p', {'shot': 'Cx', 'cap': '모르면 3번만 고르시는 거요.'}),
    ('F', '[warm] ...고마워, 클로드.', .5, {'shot': 'Fx'}),
    ('C', '[deadpan, softly] 안경은 그냥 쓰고 가세요. 도수만 있는 걸로요.', 0, 'p', {'shot': ['Cx', 'twoLow'], 'split': .6}),
], ui=dict(panes=[
    pane('클로드 · 뉴스', '수능 AI 부정행위', ['스마트안경 적발', '형사고발', '신고센터 운영 중']),
    pane('부장님 · 단톡방', '공유한 링크', ['[뉴스] 수능 AI 부정행위', '[뉴스] 수능 AI 부정행위', '[뉴스] 수능 AI 부정행위']),
    pane('클로드 · 승진시험', '공부 계획', ['기출: ?', '오답: ?', '약점: ?']),
]), events=[
    dict(line=12, dt=.2, pane=0, typed=True, cps=22, lines=['1. 기출 → 같은 유형 모의고사', '2. 오답 → 왜 틀렸나, 뭘 다시 볼까', '3. 약점 → 자주 틀리는 유형 정리']),
    dict(line=19, dt=.3, pane=0, typed=True, cps=26, lines=['약점 진단', '모르는 문제: 3번 선택 92%', '추천: 오답노트']),
], end='cut', music='sneaky', speed=1.0)
