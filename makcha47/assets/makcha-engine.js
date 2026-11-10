/*
 * 막차 47 · 캔버스 그림 엔진 (hosted)
 *
 * reference/막차47_영상엔진.html 의 그림 코드(졸라맨, 열차 배경, 휴대폰, 스피커, 손 클로즈업 등)를
 * 그대로 옮긴 것. 달라진 점은 세 가지뿐이다.
 *   1. 시간은 HyperFrames 가 준다. 각 장면 파일이 GSAP 타임라인으로 "장면 안에서 몇 초인지"를 넘겨주면
 *      그 시점의 프레임을 그린다(자체 시계, requestAnimationFrame, 난수 없음).
 *   2. 자막과 좌상단 HUD, 4·5번 장면의 숫자판 글자는 여기서 그리지 않는다. HTML 요소로 분리되어 있다.
 *   3. 화면에 박히는 글자(문자 내용, 말풍선, 선택지, 엔딩 문구)는 <canvas data-...> 속성에서 읽는다.
 *
 * 사용법 (장면 파일 안에서):
 *   Makcha.ready.then(function () {
 *     Makcha.mount(canvas, "train-wake", tl, { start: 4.01, dur: 4.79 });
 *     window.__timelines["s02-wake"] = tl;
 *   });
 */
(function () {
  if (window.Makcha) return;

  var W = 1080, H = 1920, FPS = 30;
  var F = '"Noto Sans KR","Apple SD Gothic Neo",sans-serif';
  var MONO = '"JetBrains Mono","Noto Sans KR",monospace';
  var g = null; // 지금 그리고 있는 캔버스의 2D 컨텍스트

  var clamp = function (x, a, b) { if (a === undefined) a = 0; if (b === undefined) b = 1; return Math.max(a, Math.min(b, x)); };
  var lerp = function (a, b, k) { return a + (b - a) * k; };
  var ease = function (x) { x = clamp(x); return x < 0.5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2; };
  var eout = function (x) { return 1 - Math.pow(1 - clamp(x), 3); };

  // ---------- 폰트 (캔버스는 글자를 그리기 전에 폰트가 로드되어 있어야 한다) ----------
  function loadFonts() {
    if (!window.FontFace || !document.fonts) return Promise.resolve();
    var LATIN = "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+20AC,U+2122,U+2212,U+2215";
    var faces = [];
    [600, 700, 800, 900].forEach(function (w) {
      faces.push(new FontFace("Noto Sans KR", "url(assets/fonts/noto-sans-kr-korean-" + w + "-normal.woff2)", { weight: String(w) }));
      faces.push(new FontFace("Noto Sans KR", "url(assets/fonts/noto-sans-kr-latin-" + w + "-normal.woff2)", { weight: String(w), unicodeRange: LATIN }));
    });
    [600, 700, 800].forEach(function (w) {
      faces.push(new FontFace("JetBrains Mono", "url(assets/fonts/jetbrains-mono-latin-" + w + "-normal.woff2)", { weight: String(w), unicodeRange: LATIN }));
    });
    return Promise.all(faces.map(function (f) {
      document.fonts.add(f);
      return f.load().catch(function () { return null; });
    }));
  }

  // ---------- 졸라맨 ----------
  var SKIN = "#ead6ad", LINE = "#2a2119";
  function limb(x1, y1, x2, y2, w) {
    g.lineCap = "round"; g.strokeStyle = LINE; g.lineWidth = w + 10; g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke();
    g.strokeStyle = SKIN; g.lineWidth = w; g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke();
  }
  function seg(x, y, len, ang) { return [x + Math.sin(ang) * len, y + Math.cos(ang) * len]; }
  // 포즈: 똑바로 아래를 0으로 한 라디안 각도. aL/aR 팔, eL/eR 팔꿈치, lL/lR 다리, kL/kR 무릎
  function stick(x, y, s, o) {
    var p = Object.assign({ aL: 0.25, aR: -0.25, eL: 0, eR: 0, lL: 0.12, lR: -0.12, kL: 0, kR: 0, lean: 0, face: "n", num: null, hair: null, sit: false, look: 0, blood: false, alpha: 1 }, o || {});
    g.save(); g.globalAlpha = p.alpha; g.translate(x, y); g.scale(s, s); g.rotate(p.lean);
    var w = 26;
    var leg = function (a, k) { var kn = seg(0, 0, 85, a); var ft = seg(kn[0], kn[1], 85, a + k); limb(0, 0, kn[0], kn[1], w); limb(kn[0], kn[1], ft[0], ft[1], w); };
    if (p.sit) { leg(-1.45, 1.45); leg(-1.35, 1.4); } else { leg(p.lL, p.kL); leg(p.lR, p.kR); }
    // 몸통
    limb(0, 0, 0, -150, w + 14);
    if (p.num != null) {
      g.fillStyle = "#f4f1ea"; g.strokeStyle = LINE; g.lineWidth = 5; g.beginPath(); g.roundRect(-26, -112, 52, 44, 6); g.fill(); g.stroke();
      g.fillStyle = "#1d1d1d"; g.font = "900 30px " + F; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(p.num, 0, -89);
    }
    if (p.blood) { g.fillStyle = "rgba(170,20,20,.9)"; g.beginPath(); g.ellipse(6, -40, 16, 26, 0.2, 0, 7); g.fill(); }
    var arm = function (a, e) { var el = seg(0, -140, 72, a); var hd = seg(el[0], el[1], 72, a + e); limb(0, -140, el[0], el[1], w - 4); limb(el[0], el[1], hd[0], hd[1], w - 4); return hd; };
    var hL = arm(p.aL, p.eL), hR = arm(p.aR, p.eR);
    // 머리
    g.save(); g.translate(0, -205); g.rotate(p.look);
    g.fillStyle = SKIN; g.strokeStyle = LINE; g.lineWidth = 7; g.beginPath(); g.arc(0, 0, 52, 0, 7); g.fill(); g.stroke();
    if (p.hair) { g.fillStyle = p.hair; g.beginPath(); g.arc(0, -6, 56, Math.PI * 0.95, Math.PI * 2.05); g.lineTo(54, 40); g.lineTo(40, 40); g.lineTo(38, -8); g.lineTo(-38, -8); g.lineTo(-40, 40); g.lineTo(-54, 40); g.closePath(); g.fill(); }
    g.strokeStyle = LINE; g.fillStyle = LINE; g.lineWidth = 6; g.lineCap = "round";
    var f = p.face;
    if (f === "sleep") { g.beginPath(); g.moveTo(-26, 4); g.quadraticCurveTo(-17, 10, -8, 4); g.moveTo(8, 4); g.quadraticCurveTo(17, 10, 26, 4); g.stroke(); }
    else if (f === "wide") { g.beginPath(); g.arc(-17, 0, 7, 0, 7); g.arc(17, 0, 7, 0, 7); g.fill(); g.beginPath(); g.ellipse(0, 26, 8, 11, 0, 0, 7); g.stroke(); }
    else if (f === "worry") { g.beginPath(); g.arc(-17, 4, 6, 0, 7); g.arc(17, 4, 6, 0, 7); g.fill(); g.beginPath(); g.moveTo(-28, -14); g.lineTo(-8, -8); g.moveTo(28, -14); g.lineTo(8, -8); g.moveTo(-10, 28); g.quadraticCurveTo(0, 22, 10, 28); g.stroke(); }
    else if (f === "smirk") { g.beginPath(); g.moveTo(-26, 0); g.lineTo(-10, 2); g.moveTo(10, 2); g.lineTo(26, 0); g.moveTo(-8, 26); g.quadraticCurveTo(6, 32, 16, 22); g.stroke(); }
    else { g.beginPath(); g.arc(-17, 2, 6, 0, 7); g.arc(17, 2, 6, 0, 7); g.fill(); g.beginPath(); g.moveTo(-8, 26); g.lineTo(8, 26); g.stroke(); }
    g.restore(); g.restore(); return { hL: hL, hR: hR };
  }

  // ---------- 배경 ----------
  function vignette(a) {
    if (a === undefined) a = 0.55;
    var r = g.createRadialGradient(W / 2, H * 0.48, H * 0.25, W / 2, H * 0.5, H * 0.8);
    r.addColorStop(0, "rgba(0,0,0,0)"); r.addColorStop(1, "rgba(0,0,0," + a + ")"); g.fillStyle = r; g.fillRect(0, 0, W, H);
  }
  function trainBG(t, o) {
    o = o || {}; var dark = o.dark || 0, red = o.red || 0, i, k, x;
    g.fillStyle = "#1b2a33"; g.fillRect(0, 0, W, H);
    // 천장
    g.fillStyle = "#22353f"; g.fillRect(0, 0, W, 520); for (i = 0; i < 4; i++) { g.fillStyle = "rgba(230,245,255,.9)"; g.fillRect(60 + i * 270, 330, 170, 22); }
    // 창문 + 터널 불빛
    for (i = 0; i < 3; i++) {
      x = 70 + i * 340; var y = 600, w = 260, h = 380; g.fillStyle = "#0a0f14"; g.beginPath(); g.roundRect(x, y, w, h, 24); g.fill();
      g.save(); g.beginPath(); g.roundRect(x, y, w, h, 24); g.clip(); for (k = 0; k < 5; k++) { var sx = ((k * 170 - t * 2600) % 900 + 900) % 900 - 200 + x; g.fillStyle = "rgba(255,210,140,.55)"; g.fillRect(sx, y + 80 + k * 60, 140, 6); } g.restore();
      g.strokeStyle = "#5d7380"; g.lineWidth = 12; g.beginPath(); g.roundRect(x, y, w, h, 24); g.stroke();
    }
    // 2호선 초록 띠
    g.fillStyle = "#2fa25f"; g.fillRect(0, 1010, W, 22);
    // 손잡이
    g.strokeStyle = "#8fa3ad"; g.lineWidth = 8; g.beginPath(); g.moveTo(0, 470); g.lineTo(W, 470); g.stroke();
    for (i = 0; i < 8; i++) { x = 70 + i * 135 + Math.sin(t * 2 + i) * 4; g.beginPath(); g.moveTo(x, 470); g.lineTo(x, 540); g.stroke(); g.beginPath(); g.ellipse(x, 560, 20, 24, 0, 0, 7); g.stroke(); }
    // 좌석
    g.fillStyle = "#2c6e9e"; g.beginPath(); g.roundRect(30, 1240, W - 60, 90, 20); g.fill(); g.fillStyle = "#255d86"; g.fillRect(30, 1320, W - 60, 130);
    // 바닥
    g.fillStyle = "#3d4a50"; g.fillRect(0, 1450, W, H - 1450); g.fillStyle = "#4a585e"; for (i = 0; i < 12; i++) g.fillRect(0, 1500 + i * 40, W, 3);
    // 봉
    g.fillStyle = "#b8c6cc"; [300, 780].forEach(function (px) { g.fillRect(px, 470, 18, 1000); });
    if (red) { g.fillStyle = "rgba(200,20,30," + red + ")"; g.fillRect(0, 0, W, H); }
    if (dark) { g.fillStyle = "rgba(0,0,0," + dark + ")"; g.fillRect(0, 0, W, H); }
  }

  // ---------- 장면 (t = 장면 안에서의 초, d = 장면 길이, o = <canvas data-...> 값) ----------
  var SCENES = {
    // 1. 휴대폰 문자
    "phone": function (t, d, o) {
      g.fillStyle = "#07090c"; g.fillRect(0, 0, W, H); var z = 1 + 0.05 * t / d; g.save(); g.translate(W / 2, H / 2); g.scale(z, z); g.rotate(-0.04); g.translate(-W / 2, -H / 2);
      g.fillStyle = "#111418"; g.strokeStyle = "#2c3138"; g.lineWidth = 14; g.beginPath(); g.roundRect(150, 180, 780, 1560, 90); g.fill(); g.stroke();
      g.fillStyle = "#e8eaee"; g.font = "700 40px " + F; g.textAlign = "left"; g.fillText(o.clock || "2:04", 230, 280);
      g.fillStyle = "#2a2f36"; g.beginPath(); g.arc(540, 400, 46, 0, 7); g.fill(); g.fillStyle = "#fff"; g.font = "900 50px " + F; g.textAlign = "center"; g.fillText("?", 540, 418); g.font = "600 34px " + F; g.fillText(o.sender || "알 수 없음", 540, 490);
      var msg = (o.message || "축하합니다,|참가자 47번.|당신은 선택되었습니다.").split("|"); var shown = Math.floor(clamp((t - 0.3) / 1.4) * msg.join("").length); var cnt = 0;
      g.fillStyle = "#262b33"; g.beginPath(); g.roundRect(220, 560, 560, 230, 36); g.fill(); g.fillStyle = "#f2f2f2"; g.font = "600 44px " + F; g.textAlign = "left";
      msg.forEach(function (m, i) { var vis = m.slice(0, clamp(shown - cnt, 0, m.length)); cnt += m.length; g.fillText(vis, 255, 630 + i * 62); });
      g.restore(); vignette(0.7);
    },
    // 2. 막차 안에서 깨어남
    "train-wake": function (t, d) {
      var z = 1.06 - 0.05 * t / d; g.save(); g.translate(W / 2, H / 2); g.scale(z, z); g.translate(-W / 2, -H / 2);
      trainBG(t, { dark: clamp(1 - t / 0.6) });
      [88, 47, 12].forEach(function (n, i) { var x = 250 + i * 300; var sl = n === 47; stick(x, 1290, 1.0, { sit: true, num: n, face: sl && t < 1.0 ? "sleep" : (sl ? "wide" : "n"), hair: n === 12 ? "#2b1d16" : null, look: sl ? (t < 1 ? 0.25 : Math.sin(t * 3) * 0.15) : Math.sin(t + i) * 0.05, aL: 0.5, aR: -0.5, eL: -1.2, eR: 1.2 }); });
      stick(90, 1820, 1.2, { num: 56, look: 0.1, aL: 2.9, eL: 0.1, aR: -0.3 }); stick(1000, 1830, 1.2, { num: 23, look: -0.1, aR: -2.9, eR: -0.1, aL: 0.3 });
      g.restore(); vignette();
    },
    // 3. 천장 스피커
    "speaker": function (t, d) {
      trainBG(t, { dark: 0.55 }); var z = 1 + 0.08 * t / d; g.save(); g.translate(W / 2, 700); g.scale(z, z);
      g.fillStyle = "#2f3338"; g.beginPath(); g.roundRect(-230, -150, 460, 300, 40); g.fill(); g.fillStyle = "#1c1f23"; for (var r = 0; r < 5; r++) for (var c = 0; c < 9; c++) { g.beginPath(); g.arc(-160 + c * 40, -80 + r * 40, 9, 0, 7); g.fill(); }
      var pulse = 0.5 + 0.5 * Math.sin(t * 10); g.fillStyle = "rgba(255,40,50," + (0.5 + 0.5 * pulse) + ")"; g.beginPath(); g.arc(180, -110, 18, 0, 7); g.fill();
      g.strokeStyle = "rgba(255,80,80,.8)"; g.lineWidth = 8; for (var k = 1; k <= 3; k++) { var rr = 260 + k * 50 + ((t * 120) % 50); g.globalAlpha = clamp(1 - (rr - 260) / 200); g.beginPath(); g.arc(0, 0, rr, -0.5, 0.5); g.stroke(); g.beginPath(); g.arc(0, 0, rr, Math.PI - 0.5, Math.PI + 0.5); g.stroke(); } g.globalAlpha = 1; g.restore(); vignette(0.6);
    },
    // 4. 숫자판 배경 (숫자는 HTML)
    "board": function () {
      g.fillStyle = "#0b1220"; g.fillRect(0, 0, W, H); var gr = g.createLinearGradient(0, H * 0.4, 0, H); gr.addColorStop(0, "rgba(0,0,0,0)"); gr.addColorStop(1, "rgba(240,140,90,.35)"); g.fillStyle = gr; g.fillRect(0, 0, W, H);
      vignette(0.5);
    },
    // 5. 첫 번째 역 배경 (숫자는 HTML). flashAt~flashEnd 동안 빨간 배경
    "station": function (t, d, o) {
      var a = parseFloat(o.flashAt || "0.9"), b = parseFloat(o.flashEnd || "1.4"); var red = t >= a && t < b;
      g.fillStyle = red ? "#3a0a0e" : "#0b1220"; g.fillRect(0, 0, W, H); vignette(0.5);
    },
    // 6. 문이 열리고 한 명이 사라짐
    "door": function (t, d, o) {
      trainBG(t, { dark: 0.25 }); var z = 1 + 0.06 * t / d; g.save(); g.translate(W / 2, H / 2); g.scale(z, z); g.translate(-W / 2, -H / 2);
      var open = ease((t - 0.2) / 0.8) * (1 - ease((t - 2.2) / 0.6)); g.fillStyle = "#fff7d6"; g.fillRect(340, 520, 400, 960);
      g.fillStyle = "#8e9ea6"; g.fillRect(340 - open * 200, 520, 200, 960); g.fillRect(540 + open * 200, 520, 200, 960); g.fillStyle = "#5f6e75"; g.fillRect(340 - open * 200 + 30, 600, 140, 300); g.fillRect(540 + open * 200 + 30, 600, 140, 300);
      var a = clamp(1 - (t - 1.3) / 0.8); if (a > 0) stick(540, 1440, 0.95, { num: o.gone || 23, alpha: a, face: "n" });
      stick(170, 1680, 1.0, { num: 47, face: "wide", aL: 0.6, aR: -0.6 }); stick(930, 1700, 1.0, { num: 61, face: "worry" });
      g.restore(); vignette();
    },
    // 7. 12번이 다가와 귓속말
    "whisper": function (t, d, o) {
      trainBG(t, { dark: 0.35 }); var z = 1.1 + 0.08 * t / d; g.save(); g.translate(W / 2, H * 0.62); g.scale(z, z); g.translate(-W / 2, -H * 0.62);
      var gx = lerp(860, 640, ease(t / 1.2)); stick(gx, 1650, 1.15, { num: 12, hair: "#2b1d16", face: "smirk", lean: -0.12, aL: 0.3, aR: -1.4, eR: -0.6, look: -0.15 });
      stick(330, 1660, 1.15, { num: 47, face: t > 2.2 ? "wide" : "worry", look: 0.12 });
      if (t > 2.2) { g.fillStyle = "#fff"; g.strokeStyle = "#000"; g.lineWidth = 6; g.beginPath(); g.roundRect(560, 980, 420, 120, 30); g.fill(); g.stroke(); g.fillStyle = "#000"; g.font = "800 44px " + F; g.textAlign = "center"; g.fillText(o.bubble || "나가는 법 알아", 770, 1055); }
      g.restore(); vignette();
    },
    // 8. 손 클로즈업, 피 번짐
    "hand": function (t, d) {
      g.fillStyle = "#141c22"; g.fillRect(0, 0, W, H); var z = 1 + 0.12 * ease(t / d); g.save(); g.translate(W / 2, H / 2); g.scale(z, z); g.translate(-W / 2, -H / 2);
      g.lineCap = "round"; g.strokeStyle = LINE; g.lineWidth = 250; g.beginPath(); g.moveTo(-100, 1500); g.lineTo(560, 1000); g.stroke(); g.strokeStyle = SKIN; g.lineWidth = 230; g.stroke();
      g.fillStyle = SKIN; g.strokeStyle = LINE; g.lineWidth = 12; g.beginPath(); g.ellipse(620, 950, 170, 150, 0.4, 0, 7); g.fill(); g.stroke();
      var i; for (i = 0; i < 4; i++) { g.save(); g.translate(640 + i * 30, 880); g.rotate(-0.9 + i * 0.35); g.fillStyle = SKIN; g.beginPath(); g.roundRect(-30, -200, 60, 200, 30); g.fill(); g.stroke(); g.restore(); }
      var k = clamp((t - 1.2) / 1.2); g.fillStyle = "rgba(150,10,15," + 0.85 * k + ")"; g.beginPath(); g.ellipse(600, 980, 110 * k + 10, 70 * k + 5, 0.5, 0, 7); g.fill(); g.beginPath(); g.ellipse(700, 860, 40 * k, 90 * k, 0.2, 0, 7); g.fill();
      for (i = 0; i < 3; i++) { g.beginPath(); g.ellipse(560 + i * 60, 1060 + k * 80 * (i + 1) * 0.5, 10, 30 * k, 0, 0, 7); g.fill(); }
      g.restore(); vignette(0.75);
    },
    // 9. 선택지 A / B
    "choice": function (t, d, o) {
      trainBG(t, { dark: 0.6 });
      var c = function (y, label, txt, col, dl) {
        var k = eout((t - dl) / 0.35); g.save(); g.translate(W / 2 + (1 - k) * 600, y); g.fillStyle = "rgba(15,20,26,.92)"; g.strokeStyle = col; g.lineWidth = 6; g.beginPath(); g.roundRect(-430, -90, 860, 180, 30); g.fill(); g.stroke();
        g.fillStyle = col; g.beginPath(); g.arc(-340, 0, 52, 0, 7); g.fill(); g.fillStyle = "#000"; g.font = "900 60px " + F; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(label, -340, 4);
        g.fillStyle = "#fff"; g.font = "800 52px " + F; g.textAlign = "left"; g.fillText(txt, -260, 4); g.restore();
      };
      c(760, "A", o.choiceA || "12번을 따라간다", "#ffd84a", 0.2); c(980, "B", o.choiceB || "혼자 움직인다", "#7fd3ff", 0.5); vignette(0.4);
    },
    // 10. 엔딩: 댓글 입력 → 로고 카드
    "end": function (t, d, o) {
      g.fillStyle = "#0a0d12"; g.fillRect(0, 0, W, H); g.textAlign = "center"; g.textBaseline = "alphabetic";
      var cut = parseFloat(o.logoAt || "2.4");
      if (t < cut) {
        g.fillStyle = "#fff"; g.font = "900 96px " + F; g.fillText(o.question || "너라면 뭐 할래?", W / 2, 720); g.font = "700 40px " + F; g.fillStyle = "#9fb3c0"; g.fillText(o.sub || "댓글에 너의 선택을 적어줘", W / 2, 800);
        var full = o.typed || "나라면 B. 혼자 간다";
        g.fillStyle = "#1c232b"; g.beginPath(); g.roundRect(140, 880, 800, 110, 55); g.fill(); var typed = full.slice(0, Math.floor(clamp((t - 0.5) / 1.2) * full.length)); g.fillStyle = "#e8e8e8"; g.font = "600 42px " + F; g.textAlign = "left"; g.fillText(typed || o.placeholder || "댓글 달기...", 200, 950);
        g.fillStyle = "#ffd84a"; g.beginPath(); g.arc(880, 935, 36, 0, 7); g.fill(); g.textAlign = "center"; g.font = "900 40px " + F; g.fillStyle = "#ffd84a"; g.fillText(o.cta || "댓글 1등이 PART 2를 정한다", W / 2, 1120);
      } else {
        var k = eout((t - cut) / 0.5); g.globalAlpha = k; g.fillStyle = "#7fd3ff"; g.font = "900 160px " + F; g.fillText(o.left || "99", W / 2, 760); g.fillStyle = "#fff"; g.font = "900 120px " + F; g.fillText(o.title || "막차 47", W / 2, 920);
        g.fillStyle = "#ff5a5a"; g.font = "700 40px " + MONO; g.fillText(o.part || "PART 1 · 네가 정해", W / 2, 990);
        // 좋아요(하트) / 팔로우(+) 버튼: 폰트에 기대지 않고 도형으로 그린다
        g.fillStyle = "#ff4d6d"; g.beginPath(); g.arc(430, 1180, 50, 0, 7); g.fill();
        g.fillStyle = "#fff"; g.beginPath(); g.moveTo(430, 1204); g.bezierCurveTo(398, 1182, 402, 1156, 418, 1156); g.bezierCurveTo(425, 1156, 430, 1162, 430, 1168); g.bezierCurveTo(430, 1162, 435, 1156, 442, 1156); g.bezierCurveTo(458, 1156, 462, 1182, 430, 1204); g.closePath(); g.fill();
        g.fillStyle = "#ddd"; g.beginPath(); g.arc(650, 1180, 50, 0, 7); g.fill();
        g.fillStyle = "#000"; g.fillRect(646, 1160, 8, 40); g.fillRect(630, 1176, 40, 8);
        g.font = "600 30px " + F; g.fillStyle = "#aaa"; g.fillText(o.like || "좋아요", 430, 1270); g.fillText(o.follow || "팔로우", 650, 1270); g.globalAlpha = 1;
      }
      vignette(0.5);
    }
  };

  // 필름 그레인: 영상 전체 기준 프레임 번호로만 정해진다(난수 없음)
  function grain(T) {
    var fr = Math.floor(T * FPS + 1e-6);
    g.fillStyle = "rgba(255,255,255,0.025)";
    for (var k = 0; k < 60; k++) g.fillRect((k * 7919 + fr * 131) % W, (k * 104729 + fr * 71) % H, 2, 2);
  }

  function render(ctx, key, t, d, start, opts) {
    g = ctx; g.setTransform(1, 0, 0, 1, 0, 0); g.globalAlpha = 1; g.shadowBlur = 0; g.textAlign = "left"; g.textBaseline = "alphabetic"; g.lineCap = "butt";
    SCENES[key](t, d, opts || {});
    grain((start || 0) + t);
  }

  // 장면 타임라인에 캔버스를 연결한다. HyperFrames 가 타임라인을 seek 하면 그 시점 프레임을 그린다.
  function mount(canvas, key, tl, o) {
    var ctx = canvas.getContext("2d"), st = { t: 0 }, dur = o.dur, start = o.start || 0;
    var draw = function () { render(ctx, key, clamp(st.t, 0, dur), dur, start, canvas.dataset); };
    tl.fromTo(st, { t: 0 }, { t: dur, duration: dur, ease: "none", onUpdate: draw }, 0);
    draw();
    return draw;
  }

  window.Makcha = { W: W, H: H, FPS: FPS, ready: loadFonts(), mount: mount, render: render, scenes: SCENES };
})();
