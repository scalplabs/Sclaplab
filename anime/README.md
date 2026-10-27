# 제1화 「완벽한 범죄」 — 30초 학원 애니

Canvas 코드로 직접 그린 30초 애니메이션. 법과학 수업 시간, 선생님이 "완벽한 범죄는 존재할까?"를 가르치고 학생들이 질문한다.

- `classroom_anime.mp4` — 완성 영상 (1280×720, 30fps, 30초, 사운드 포함)
- `index.html` — 애니메이션 원본. 브라우저로 열고 ▶ 재생
- `tools/render.js` — 프레임 렌더 (`node tools/render.js <outDir>`)
- `tools/soundtrack.py` — 종소리·BGM·대사음·효과음 합성 (`python3 tools/soundtrack.py out.wav`)
- `fonts/` — Jua, Black Han Sans (SIL OFL)

다시 만들기:
```
node anime/tools/render.js /tmp/frames
python3 anime/tools/soundtrack.py /tmp/audio.wav
ffmpeg -framerate 30 -i /tmp/frames/%04d.jpg -i /tmp/audio.wav -c:v libx264 -crf 19 -pix_fmt yuv420p -c:a aac -shortest anime/classroom_anime.mp4
```
