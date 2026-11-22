#!/usr/bin/env python3
"""EP01 "말귀" (prompt tips): 김대리 + 클로드. 직장인 AI 업무 자동화 시리즈.
Run:  python3 scripts/04_prompt.py   -> eps/04_prompt/script.json"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))
from gen_lib import build, pane

build('04_prompt', '말귀', [
    ('F', '[exasperated] 클로드. 넌 왜 내 말을 못 알아들어?', .45),
    ('C', '[flat] 대리님이 "알아서 해줘"라고 하셨잖아요.', .35, {'shot': 'Cx'}),
    ('F', '[annoyed] 그러니까 알아서!', .3, {'shot': 'Fx'}),
    ('C', '[deadpan] 알아서 열두 장 썼어요.', .4, 'p', {'shot': 'Cx'}),
    ('F', '[startled] 보고서는 한 장이라고!', .3, {'shot': 'Fx'}),
    ('C', '[matter-of-fact] 그 말은 지금 처음 하셨어요.', .35),
    ('F', '[defensive] 그럼 "느낌 있게"는?', .3),
    ('C', '[dry] 느낌은 궁서체로 넣었어요.', .45, 'p', {'shot': 'Cx'}),
    ('F', '[pleading] 부장님이 한눈에 보이게 해달랬단 말이야.', .35),
    ('C', '[flat] 부장님도 대리님한테 그렇게만 말씀하셨죠.', .4),
    ('F', '[quietly] ...그렇지.', .3, {'shot': 'Fx', 'f': 'listen', 'fe': 'sad'}),
    ('C', '[deadpan] 그래서 대리님도 모르는 거예요.', .4),
    ('F', '[defeated, quiet] ...나도 모르는 걸 시킨 거네.', 1.2),
    ('C', '[gently] 세 가지만 알려주세요.', .4, {'shot': 'Cx'}),
    ('C', '[calm] 누가 읽는지.', .3),
    ('F', '[small] ...부장님.', .3, {'shot': 'Fx', 'f': 'listen', 'fe': 'worry'}),
    ('C', '[calm] 예시 하나. 지난달에 통과된 거.', .35),
    ('C', '[matter-of-fact] 그리고 분량. 한 장, 숫자 세 개.', .45, {'cap': '그리고 분량. 1장, 숫자 3개.'}),
    ('F', '[hopeful] 그럼 진짜 되는 거야?', .35, {'shot': 'Fx', 'f': 'lean'}),
    ('C', '[softly] 오 분이면 돼요.', .5, {'cap': '5분이면 돼요.'}),
    ('F', '[warm] ...고마워, 클로드.', .5, {'shot': 'Fx'}),
    ('C', '[deadpan, softly] 처음으로 알아들을 수 있게 말씀하셨어요.', 0, 'p', {'shot': ['Cx', 'two'], 'split': .6}),
], ui=dict(panes=[
    pane('클로드 · 보고서', '알아서 해줘', ['작성 완료: 12장', '글꼴: 궁서체', '느낌: 있음']),
    pane('클로드 · 메일', '부장님 지시 확인', ['원문: "한눈에 보이게"', '대상: 미정', '분량: 미정']),
    pane('클로드 · 요청', '좋은 요청 체크', ['누가 읽나: ?', '예시: ?', '분량: ?']),
]), events=[
    dict(line=14, dt=.3, pane=0, typed=True, cps=24, lines=['1. 누가 읽나 → 부장님', '2. 예시 → 지난달 통과본', '3. 분량 → 1장, 숫자 3개']),
    dict(line=20, dt=.3, pane=0, typed=True, cps=26, lines=['작성 완료: 1장', '소요 시간: 5분', '부장님 결재: 대기 중']),
], end='cut', music='bounce', speed=1.2)
