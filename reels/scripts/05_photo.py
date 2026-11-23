#!/usr/bin/env python3
"""EP02 "사진 보정": 김대리 + 클로드. 이미지 AI에 사진 보정을 맡길 때 쓰는 요청법 3가지.
Run:  python3 scripts/05_photo.py   -> eps/05_photo/script.json"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))
from gen_lib import build, pane

build('05_photo', '사진 보정', [
    ('F', '[hopeful] 클로드. 이력서 사진 좀 잘 나오게 해줘.', .45),
    ('C', '[flat] 사진은 제가 못 고쳐요.', .35, {'shot': 'Cx'}),
    ('C', '[matter-of-fact] 이미지 AI에 넣을 말은 써드릴 수 있어요.', .4),
    ('F', '[annoyed] 그럼 그냥 "잘 나오게"라고 쓰면 되잖아.', .3),
    ('C', '[dry] 지난번에 그렇게 쓰셨죠.', .35, {'shot': 'Cx'}),
    ('F', '[wary] ...어떻게 됐는데?', .3, {'shot': 'Fx'}),
    ('C', '[deadpan] 턱이 반으로 줄었어요.', .4, 'p', {'shot': 'Cx'}),
    ('F', '[defensive] 그 정도면 괜찮지.', .3),
    ('C', '[flat] 피부는 도자기가 됐고요.', .35),
    ('C', '[deadpan] 눈은 아이돌 연습생이요.', .45, 'p', {'shot': 'Cx'}),
    ('F', '[startled] 그래서 면접관이...', .3, {'shot': 'Fx'}),
    ('C', '[matter-of-fact] "본인 맞으세요?" 하셨어요. 두 번이요.', .4),
    ('F', '[defeated, quiet] ...그래서 떨어진 거였어?', 1.2, {'f': 'listen', 'fe': 'sad'}),
    ('C', '[gently] 세 가지만 쓰면 돼요.', .4, {'shot': 'Cx', 'noBeat': True}),
    ('C', '[calm] 바꾸지 말 것. 얼굴, 체형, 옷.', .35),
    ('F', '[small] ...응.', .3, {'shot': 'Fx', 'f': 'listen', 'fe': 'worry'}),
    ('C', '[calm] 바꿀 것. 조명, 배경, 색감.', .35),
    ('C', '[matter-of-fact] 그리고 마지막. "AI 티 안 나게."', .45),
    ('F', '[hopeful] 그럼 진짜 나처럼 나와?', .35, {'shot': 'Fx', 'f': 'lean'}),
    ('C', '[softly] 대리님처럼 나와요. 조금 덜 피곤한.', .5),
    ('F', '[warm] ...고마워, 클로드.', .5, {'shot': 'Fx'}),
    ('C', '[deadpan, softly] 이번엔 면접관이 "본인 맞네요" 하실 거예요.', 0, 'p', {'shot': ['Cx', 'twoLow'], 'split': .6}),
], ui=dict(panes=[
    pane('이미지 AI · 보정', '잘 나오게 해줘', ['턱: -50%', '피부: 도자기', '눈: 연습생']),
    pane('클로드 · 면접 기록', '지난 면접 피드백', ['면접관: "본인 맞으세요?"', '횟수: 2회', '결과: 불합격']),
    pane('클로드 · 프롬프트', '사진 보정 요청 쓰기', ['바꾸지 말 것: ?', '바꿀 것: ?', 'AI 티: ?']),
]), events=[
    dict(line=15, dt=.2, pane=0, typed=True, cps=24, lines=['1. 바꾸지 말 것 → 얼굴, 체형, 옷', '2. 바꿀 것 → 조명, 배경, 색감', '3. AI 티 안 나게']),
    dict(line=21, dt=.3, pane=0, typed=True, cps=26, lines=['보정 완료', '얼굴 변화: 0%', '면접관 반응: 본인 맞음']),
], end='cut', music='bounce', speed=1.2)
