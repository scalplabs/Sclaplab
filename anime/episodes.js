// Episode data shared by index.html (drawing) and tools/soundtrack.py (audio).
// Every episode follows the same 8-shot structure, so the line timings below line up with the cuts.
// A line's syllables are revealed (and spoken) over `speak` × its duration; "(삐-)" is bleeped.
const EPISODES = {
  1: {
    period: '제1화 · 1교시 법과학',
    title: '완벽한 범죄',
    next: '「선생님의 알리바이」',
    bpm: 104,
    poster: ['법과학 동아리', '신입 부원 모집!', '🔍 진실은 하나'],
    doodle: 'fingerprint',
    minjunProp: 'hair',
    taeoProp: 'none',
    finale: 'smug',
    lines: [
      { s: 2.8,  e: 7.7,  who: '선생님', text: '자, 오늘의 주제는… 「완벽한 범죄는 존재할까?」' },
      { s: 7.95, e: 11.7, who: '하나',   text: '선생님! 장갑 끼면 지문 안 남잖아요?' },
      { s: 11.95,e: 16.9, who: '선생님', text: '로카르의 교환 법칙. 모든 접촉은 반드시 흔적을 남긴다.' },
      { s: 17.1, e: 20.9, who: '민준',   text: '그, 그럼… 머리카락 한 올도요?' },
      { s: 21.1, e: 25.0, who: '선생님', text: '피부세포 몇 개면 DNA가 나와. 너희는 이미 증거투성이야.' },
      { s: 25.3, e: 27.5, who: '태오',   text: '…근데 쌤은 해보셨어요?' },
      { s: 28.35,e: 30.0, who: '선생님', text: '……그건 시험에 안 나온다.' },
    ],
    board: [
      { text: '오늘의 주제', x: 22, y: 38, size: 22, a: 3.0, b: 3.6, color: '#bfe6c8' },
      { text: '완벽한 범죄는 존재할까?', x: 22, y: 86, size: 40, a: 3.6, b: 6.4 },
      { text: '① 로카르의 교환 법칙 (1910)', x: 22, y: 132, size: 25, a: 12.3, b: 13.6, color: '#bfe6c8' },
      { text: '"모든 접촉은 흔적을 남긴다"', x: 40, y: 172, size: 30, a: 13.8, b: 15.4, color: '#ffd98a', underline: true },
      { text: '② DNA · 섬유 · 흙 · 피부세포', x: 22, y: 216, size: 25, a: 21.6, b: 23.4, color: '#bfe6c8' },
    ],
  },
  2: {
    period: '제2화 · 3교시 라면공학',
    title: '라면은 과학이다',
    next: '「쌤 컵라면 도난 사건」',
    bpm: 118,
    poster: ['라면부', '신입 부원 모집!', '🍜 물은 550ml'],
    doodle: 'ramen',
    minjunProp: 'soup',
    taeoProp: 'cupramen',
    finale: 'angry',
    lines: [
      { s: 2.8,  e: 7.7,  who: '선생님', text: '오늘은 인류 최대의 난제. 라면 물 조절이다.' },
      { s: 7.95, e: 11.7, who: '하나',   text: '쌤, 그냥 대충 넣으면 되잖아요?' },
      { s: 11.95,e: 16.9, who: '선생님', text: '대충?! 아 씨, 550ml. 1ml 틀리면 인생 (삐-)된다.' },
      { s: 17.1, e: 20.9, who: '민준',   text: '그, 그럼… 스프 먼저예요, 면 먼저예요?' },
      { s: 21.1, e: 25.0, who: '선생님', text: '그 질문 때문에 전쟁이 세 번 났다. 다시는 묻지 마라.' },
      { s: 25.3, e: 27.5, who: '태오',   text: '…쌤, 근데 저 지금 컵라면 먹는데요?' },
      { s: 28.3, e: 30.0, who: '선생님', text: '야 이 (삐-)야! 그거 내 거잖아!!', speak: 0.72 },
    ],
    board: [
      { text: '오늘의 주제', x: 22, y: 38, size: 22, a: 3.0, b: 3.6, color: '#bfe6c8' },
      { text: '라면 물 조절 = 인생', x: 22, y: 86, size: 40, a: 3.6, b: 6.4 },
      { text: '① 물 550ml (오차 ±0)', x: 22, y: 132, size: 25, a: 12.3, b: 13.6, color: '#bfe6c8' },
      { text: '"1ml 틀리면 인생 끝"', x: 40, y: 172, size: 30, a: 13.8, b: 15.4, color: '#ffd98a', underline: true },
      { text: '② 면 먼저파 = 이단 (질문 금지)', x: 22, y: 216, size: 25, a: 21.6, b: 23.4, color: '#ff9d9d' },
    ],
  },
};
const SPEAKER_COLORS = { '선생님': '#ffb36b', '하나': '#ff8fc0', '민준': '#8fcfff', '태오': '#c4f28a' };
if (typeof module !== 'undefined') module.exports = { EPISODES, SPEAKER_COLORS };
