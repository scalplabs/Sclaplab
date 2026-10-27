# 학원물 30초 애니 시리즈

Canvas 코드로 직접 그린 30초 애니메이션. 선생님이 수업하고, 학생들이 질문하고, 마지막에 반전이 터진다.

| 화 | 제목 | 영상 |
|---|---|---|
| 1 | 완벽한 범죄 (법과학) | `ep1_perfect_crime.mp4` |
| 2 | 라면은 과학이다 (병맛) | `ep2_ramen_science.mp4` |

- `episodes.js`: 화별 대사, 칠판 내용, 소품, 타이틀. **새 화는 여기에 항목 하나만 추가하면 된다.**
- `index.html`: 그림 코드. `index.html?ep=2`로 열고 ▶ 재생을 누르면 된다.
- `tools/render.js`: 프레임 렌더 (`EP=2 node tools/render.js <outDir>`)
- `tools/soundtrack.py`: 종소리, BGM, 기계음 목소리, 효과음 합성 (`python3 tools/soundtrack.py 2 out.wav`)
- `fonts/`: Jua, Black Han Sans (SIL OFL)

## 기계음 목소리 (외부 API 없음)
`neyasno_anim`과 같은 방식이다. 한글 음절을 초성, 중성, 종성으로 쪼개고, 톱니파 성대음에 모음별 포먼트를 건다. 음높이는 반음 단위로 끊고, 샘플레이트와 비트를 깎아서 기계 느낌을 낸다.
- 음절 하나하나가 자막 글자가 나오는 순간에 맞춰 배치되고, 입 모양도 같은 타이밍으로 움직인다.
- 선생님 118Hz(낮고 차분), 하나 262Hz(높고 통통), 민준 196Hz(덜덜 떨림), 태오 140Hz(졸린 링모듈레이션).
- `?`로 끝나면 끝음을 올리고, `!!`가 있으면 높고 크게 소리친다. 대사에 `(삐-)`를 쓰면 그 자리가 1kHz 삐 소리로 처리된다.

## 다시 만들기
```
pip install numpy scipy   # ffmpeg, node(playwright)도 필요
python3 anime/tools/soundtrack.py 2 /tmp/ep2.wav
EP=2 node anime/tools/render.js /tmp/f2
ffmpeg -framerate 30 -i /tmp/f2/%04d.jpg -i /tmp/ep2.wav -c:v libx264 -crf 19 -pix_fmt yuv420p -c:a aac -shortest anime/ep2_ramen_science.mp4
```
