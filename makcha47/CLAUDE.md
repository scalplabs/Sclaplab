# 막차 47 PART 1 · HyperFrames 지시서 (v2: AI 일러스트 버전)

결과: out/makcha47_part1.mp4 (1080x1920, 30fps, 약 45초)

## 중요: 지난번 실패 원인
이전 렌더는 캔버스를 hosted 방식으로 옮기면서 HyperFrames 시간(seek)에 연결이 안 돼서 44초 내내 첫 프레임만 찍혔다.
이번엔 캔버스 코드를 쓰지 말고 **네이티브 방식(HTML <img> + GSAP 타임라인)**으로 만든다. requestAnimationFrame, 타이머 사용 금지.

## 파일
- scenes/ : 장면 일러스트 (정사각 1024px). 화면을 꽉 채우게 object-fit: cover 로 세로 크롭해서 쓴다.
- reference/막차47_PART1_v2_완성본.mp4 : 목표 결과물(무음). 장면 순서, 카메라 움직임, 자막, HUD 전부 이걸 그대로 재현한다.
- reference/막차47_영상엔진_v2.html : 위 영상을 만든 코드. 장면별 이미지, 줌 값(z0→z1), 초점(fx, fy), 자막 덩어리, HUD 값, 플래시 효과가 S 배열에 다 있다. 수치는 여기서 가져올 것.
- narration.txt : 내레이션 대본

## 0단계: 내레이션 (ElevenLabs API, .env 키 사용)
1. 보이스 목록에서 이름이 "my voice"인 voice_id를 찾는다.
2. narration.txt 를 text-to-speech with-timestamps 로 생성한다. 모델 eleven_multilingual_v2, stability 0.6, similarity_boost 0.8, style 0.15, speed 0.95.
   → narration_raw.mp3 + narration_alignment.json
3. ffmpeg로 먹먹한 버전 3개를 만들어 사용자가 고르게 한다:
   A(추천): highpass=f=90,lowpass=f=5500,lowpass=f=6500,equalizer=f=220:t=q:w=1:g=2,equalizer=f=3000:t=q:w=1.2:g=-3,acompressor=threshold=-18dB:ratio=3:attack=10:release=120,aecho=0.8:0.5:25:0.12,loudnorm=I=-16:TP=-1.5
   B: A에서 lowpass 3800 / 4500
   C(안내방송): highpass=f=300,lowpass=f=3400,acrusher=bits=10:mix=0.25,acompressor=threshold=-20dB:ratio=4,loudnorm=I=-16:TP=-1.5
4. 선택한 걸 narration.mp3 로. 자막 덩어리(1~3단어)의 시간과 장면 길이를 alignment 기준으로 맞춘다. 엔딩 장면은 내레이션 없이 4초.

## 장면 (reference html의 S 배열과 동일)
1 s01_phone: 휴대폰 문자 타이핑 오버레이 "축하합니다, 참가자 47번. / 당신은 선택되었습니다." HUD 없음
2 s02_wake: 검은 화면에서 페이드인, 줌아웃 1.25→1.05. HUD 100 / ₩0
3 s03_speaker: 줌인 1.0→1.3, 빨간 맥동 오버레이
4 s04_money: 상금 0 → 100,000,000 카운트업, "+ ₩100,000,000 / 1명"
5 s05_99: 0.9초에 HUD 100→99, 빨간 플래시 + 화면 흔들림, "✕ 참가자 23 탈락"
6 s06_door: 2초 후 흰 플래시
7 s02_wake 재사용: 왼쪽(12번) 1.6→1.85 확대, 어둡게, 말풍선 "나가는 법 알아"
8 s08_hand: 줌인 1.0→1.35
9 s09_choice: A/B 선택 카드 슬라이드인 (A 12번을 따라간다 / B 혼자 움직인다), 자막 80% 높이
10 s10_tunnel: "너라면 뭐 할래?" + 댓글창 타이핑 + "댓글 1등이 PART 2를 정한다" → 로고 "99 / 막차 47 / PART 1 · 네가 정해"

## 공통 스타일
- 자막: 62% 높이, 1~3단어, 굵기 900 흰 글씨 + 두꺼운 검은 외곽선, *별표* 단어는 #ffd84a, 등장 시 팝
- HUD: 좌상단 큰 숫자 + "명 남음", 아래 모노스페이스 "상금 ₩"
- 비네트 + 상단 어둡게 + 필름 그레인, 장면 전환은 하드컷

## 완료 기준
- 렌더 전에 npx hyperframes diff reference/막차47_PART1_v2_완성본.mp4 . 로 장면마다 비교. 특히 "모든 프레임이 같은 그림"이 아닌지 반드시 확인.
- 렌더 후 out 경로와 장면별 시작 시간 보고.
