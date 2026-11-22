// Laptop screen: dark multi-agent canvas app ("Morphy"), drawn with Canvas2D each frame → CanvasTexture.
import * as THREE from 'three';
import { rng } from './chars.js';

const W = 1600, H = 1000;
const cv = document.createElement('canvas'); cv.width = W; cv.height = H;
const g = cv.getContext('2d');
export const screenTex = new THREE.CanvasTexture(cv); screenTex.colorSpace = THREE.SRGBColorSpace; screenTex.anisotropy = 8;

const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
function rr(x, y, w, h, r) { g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r); g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath(); }
const F = (wt, px, fam = 'Inter') => `${wt} ${px}px ${fam}, Pretendard`;

const DEFAULT = {
  app: '칼퇴', status: '작업 중', sidebar: ['홈', '오늘 할 일', '클로드 · 업무 비서', '보고서 (3)', '메일 (12)', '회의록', '엑셀', '개인 폴더'],
  panes: [
    { title: '클로드 · 메일', model: 'claude-sonnet-4-5', prompt: '안 읽은 메일 정리해줘', lines: ['안 읽은 메일 96통 확인', '중요: 부장님 3통', '답장 초안 12개 작성', '보내기 전에 확인받기'] },
    { title: '클로드 · 엑셀', model: 'claude-opus-4-5', prompt: '매출 시트 합쳐줘', lines: ['시트 7개 불러오는 중', '중복 행 214개 제거', '월별 합계 계산 완료'] },
    { title: '클로드 · 회의록', model: 'claude-haiku-4-5', prompt: '회의 결론만 뽑아줘', lines: ['녹음 62분 분석', '결정사항: 0개', '다음 회의 날짜: 정함'] },
    { title: '클로드 · 발표', model: 'claude-haiku-4-5', prompt: '내일 발표자료 초안', lines: ['개요 5장 작성', '그래프 3개 생성', '글꼴: 궁서체 제거'] },
    { title: '클로드 · 일정', model: 'claude-haiku-4-5', prompt: '이번 주 일정 정리', lines: ['회의 11개', '야근 예정 4일', '칼퇴 가능: 금요일'] },
    { title: '클로드 · 검토', model: 'claude-sonnet-4-5', prompt: '보고서 오탈자 검사', lines: ['오탈자 7개 수정', '숫자 불일치 2곳', '검토 완료'] },
  ],
};
let CFG = DEFAULT, EV = [];
export function setUI(ui, events) { CFG = { ...DEFAULT, ...(ui || {}) }; if (ui && ui.panes) { const cu = ui.panes.map((p, i) => ({ ...DEFAULT.panes[i % 6], ...p })); CFG.panes = cu.concat(DEFAULT.panes.slice(cu.length)); } EV = events || [];
  if (CFG.app !== DEFAULT.app) { const nm = (s) => s.replace(/Morphy/g, CFG.app); CFG.sidebar = CFG.sidebar.map(nm); CFG.panes = CFG.panes.map((p) => ({ ...p, title: nm(p.title) })); } }  // your own app name: ui.app in the script, or APP_NAME in .env

// st = { t, freeze: bool (agents hold still), focus: pane index or -1 }
export function drawUI(st) {
  const t = st.t, tt = st.freeze ? st.freezeT : t;
  g.fillStyle = '#14141b'; g.fillRect(0, 0, W, H);
  // top bar
  g.fillStyle = '#191921'; g.fillRect(0, 0, W, 50);
  ['#ff5f57', '#febc2e', '#28c840'].forEach((c, i) => { g.fillStyle = c; g.beginPath(); g.arc(26 + i * 22, 25, 6.5, 0, 7); g.fill(); });
  g.fillStyle = '#23232e'; rr(420, 11, 760, 28, 14); g.fill();
  g.fillStyle = '#8b8ba0'; g.font = F(500, 14); g.textAlign = 'center'; g.fillText(`Main canvas  ·  ${CFG.panes.length} agents running`, 800, 30); g.textAlign = 'left';
  // sidebar
  g.fillStyle = '#17171f'; g.fillRect(0, 50, 236, H - 50);
  g.fillStyle = '#e45a4a'; rr(20, 70, 34, 34, 9); g.fill(); g.fillStyle = '#fff'; g.font = F(800, 20); g.textAlign = 'center'; g.fillText((CFG.app[0] || 'M').toUpperCase(), 37, 94); g.textAlign = 'left';
  g.fillStyle = '#f1eff8'; g.font = F(700, 21); g.fillText(CFG.app, 66, 94);
  CFG.sidebar.forEach((s, i) => { const y = 150 + i * 42; if (i === 1) { g.fillStyle = '#262634'; rr(10, y - 25, 216, 36, 9); g.fill(); } g.fillStyle = i === 1 ? '#fff' : '#8d8ca3'; g.font = F(500, 16); g.fillText(s, 30, y); });
  g.fillStyle = '#5f5f76'; g.font = F(400, 13); g.fillText(`3 projects · 10 canvases · ${CFG.panes.length + 3} agents`, 20, H - 28);
  // panes (3x2)
  const gx = 252, gy = 66, pw = 436, ph = 436, gap = 14, N = CFG.panes.length;
  CFG.panes.forEach((p0, i) => {
    const cx = i % 3, cy = (i / 3) | 0, x = gx + cx * (pw + gap), y = gy + cy * (ph + gap);
    // live content: last event for this pane
    let ev = null; for (const e of EV) if (e.pane === i && e.t <= tt && (!ev || e.t >= ev.t)) ev = e;
    const p = ev ? { ...p0, ...ev.set } : p0;
    g.fillStyle = '#1e1e28'; rr(x, y, pw, ph, 14); g.fill();
    g.strokeStyle = st.focus === i ? 'rgba(255,255,255,.55)' : '#31313f'; g.lineWidth = st.focus === i ? 2.5 : 1.5; rr(x + .5, y + .5, pw - 1, ph - 1, 14); g.stroke();
    g.fillStyle = '#242431'; rr(x + 6, y + 6, pw - 12, 32, 10); g.fill();
    const pulse = .5 + .5 * Math.sin(tt * 4.5 + i * 1.7);
    g.fillStyle = `rgba(110,235,160,${.5 + .5 * pulse})`; g.beginPath(); g.arc(x + 24, y + 22, 4.5, 0, 7); g.fill();
    g.fillStyle = '#d9d7ea'; g.font = F(600, 15); g.fillText(p.title, x + 38, y + 27);
    g.fillStyle = '#6e6e86'; g.font = F(500, 13); g.fillText('···', x + pw - 36, y + 27);
    // user bubble
    g.font = F(500, 14); const bw = Math.min(pw - 56, g.measureText(p.prompt).width + 28);
    g.fillStyle = '#31313f'; rr(x + pw - bw - 16, y + 52, bw, 32, 10); g.fill();
    g.fillStyle = '#e6e4f4'; g.fillText(p.prompt, x + pw - bw - 2, y + 73);
    // log lines (cycle) or typed text
    g.font = F(500, 14.5, 'JetBrains Mono');
    let lines;
    if (ev && ev.typed) { const n = Math.floor(clamp((tt - ev.t) * (ev.cps || 28) / Math.max(1, ev.lines.join('\n').length)) * ev.lines.join('\n').length); lines = ev.lines.join('\n').slice(0, n).split('\n'); }
    else if (ev && ev.lines) lines = ev.lines;
    else { const r = rng(i * 99 + 7), sp = 1.1 + r() * 1.1, k = Math.floor(tt * sp + r() * 6) % (p.lines.length + 3); lines = p.lines.slice(0, Math.min(p.lines.length, k + 1)); }
    lines.forEach((ln, j) => {
      const yy = y + 118 + j * 29; if (yy > y + ph - 100) return;
      const last = j === lines.length - 1; g.fillStyle = last ? '#f4f2ff' : '#8f8ea6'; g.fillText((ev && ev.typed ? '' : '› ') + ln, x + 20, yy);
    });
    if (ev && ev.typed && (tt - ev.t) * (ev.cps || 28) < ev.lines.join('\n').length && Math.floor(tt * 3) % 2 === 0) {
      const last = lines[lines.length - 1] || ''; g.fillStyle = '#fff'; g.fillRect(x + 20 + g.measureText(last).width + 3, y + 118 + (lines.length - 1) * 29 - 14, 9, 17);
    }
    g.fillStyle = '#5b5b73'; g.font = F(500, 13); g.fillText(`${CFG.status} · ${Math.floor(tt / 60 + 2 + i)}:${String(Math.floor((tt * 7 + i * 13) % 60)).padStart(2, '0')}`, x + 20, y + ph - 98);
    // input
    g.fillStyle = '#16161e'; rr(x + 12, y + ph - 78, pw - 24, 64, 12); g.fill(); g.strokeStyle = '#2c2c3a'; g.lineWidth = 1; rr(x + 12.5, y + ph - 77.5, pw - 25, 63, 12); g.stroke();
    g.fillStyle = '#6a6a82'; g.font = F(500, 14); g.fillText(p.title.startsWith('Codex') ? 'Ask Codex…' : '클로드에게 물어보기…', x + 26, y + ph - 50);
    g.fillStyle = '#242431'; rr(x + 26, y + ph - 40, 118, 20, 10); g.fill(); g.fillStyle = '#9a99b3'; g.font = F(500, 11); g.fillText(p.model, x + 36, y + ph - 26);
    g.fillStyle = '#e5484d'; g.beginPath(); g.arc(x + pw - 36, y + ph - 32, 13, 0, 7); g.fill();
  });
  screenTex.needsUpdate = true;
}
