# 김대리 & 클로드 릴스

"야근하는 김대리를 클로드가 칼퇴시키는" 직장인 AI 업무 자동화 숏폼 시리즈.
claude-and-pixel-kit을 기반으로 한국어 버전으로 고쳤어요. 형식은 1080x1920, 30fps, 45~60초예요.

## 완성본
- `releases/EP01_말귀.mp4`: EP01 「말귀」, 요청을 잘하는 법 3가지 (51.6초)
- `releases/pfp_claude.jpg`, `releases/pfp_two.jpg`: 프로필 사진 후보

## 고정 설정
| 항목 | 값 |
|---|---|
| 목소리 엔진 | **타입캐스트** `ssfm-v31`, 스마트 감정 모드(앞뒤 대사 문맥) |
| 김대리 목소리 | 필재 `tc_68257f68bc6e3c161ab5078d` |
| 클로드 목소리 | 서현 `tc_69f2e455ea79fd197aa0476f` |
| 말하기 속도 | 1.0배 (`build(..., speed=1.0)`) |
| 자막, 화면 폰트 | Pretendard (`fonts/`) |
| 뒤 화면 앱 | "칼퇴" (`engine/ui.js`의 DEFAULT) |

- 타입캐스트 키는 클라우드 환경의 네트워크 시크릿으로 `api.typecast.ai` 요청에 자동으로 붙어요. 로컬에서 돌릴 때는 `.env`에 `TYPECAST_API_KEY=`를 넣으세요.
- 특정 대사만 감정을 직접 지정하려면 그 줄에 `{'emo': 'angry', 'emo_int': 1.2}`처럼 넣으세요(normal happy sad angry whisper toneup tonedown).
- EP01, EP02는 ElevenLabs(eleven_v4, 1.2배속)로 만든 버전이에요. 그 대본은 `script.json`에 `tts`가 없어서 계속 ElevenLabs 캐시를 써요.

## 원본 키트에서 바꾼 것
- `index.html`, `engine/main.js`, `engine/ui.js`: Pretendard 한글 폰트 추가, 화면 패널 한국어화
- `engine/chars.js`: 김대리 정장 색을 회색 계열로 변경
- `tools/gen_lib.py`: 한글 대사 검사, 훅 "클로드."로 시작, `speed` 옵션
- `tools/tts.py`: `speed`를 적용(atempo)하고 단어 타이밍도 그만큼 보정
- `tools/vo_check.py`: 음성 검사 언어를 한국어(`ko`)로 변경
- `tools/env.py`, `.env.example`: 기본 목소리 ID를 위 두 개로 변경

## 새 에피소드 만들기
```bash
npm install
python3 scripts/05_xxx.py          # 대본 -> eps/05_xxx/script.json
./tools/prep.sh 05_xxx             # 목소리(+음성 검사, 음악)
node tools/render.mjs shots --ep 05_xxx --qa qa/05_xxx --sheet   # 샷 점검
./tools/make.sh 05_xxx             # 렌더 + 믹스 -> out/05_xxx.mp4
```
- 대본 형식과 작성 규칙은 `CLAUDE.md`와 `scripts/04_prompt.py`를 참고하세요.
- `eps/<ep>/vo/`에 목소리 캐시를 커밋해 두면, 다시 렌더할 때 크레딧이 들지 않아요.
- Linux(GPU 없음)에서는 프레임당 약 2초라 50초 영상에 약 1시간 걸려요. `CHROME_PATH`에 Chromium 경로를 지정해야 해요.

## 알려진 문제
- ElevenLabs API 키(Dominant Swordfish)는 현재 Text to Speech 권한만 반영돼 있어요. 그래서 `vo_check.py`(Speech to Text)와 `music.py`(Music)는 실패해요.
  - EP01 음악은 ElevenLabs 커넥터(eleven_music_v2_5)로 만들어 `audio/04_prompt/music.mp3`에 넣었어요.
- 원본 캐릭터(빨간 로봇 클로드)는 아직 원본 키트 디자인 그대로예요.
