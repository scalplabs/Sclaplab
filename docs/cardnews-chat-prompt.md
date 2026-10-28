# 애드맨 카드뉴스: 채팅용 프롬프트

Claude Code 없이 claude.ai 채팅에서 지금과 같은 디자인으로 카드뉴스를 만드는 방법.

## 쓰는 법
1. claude.ai 새 채팅 열기
2. 아래 프롬프트 전체 복사 → `[주제]`, `[회차]` 두 줄만 바꿔서 보내기
3. 오른쪽에 카드뉴스 7장이 뜨면:
   - **프사 넣기**: 처음 한 번만 (기기에 기억됨)
   - **n번 배경 사진 넣기**: 장마다 사진 고르기 (어둡고 흐리게 자동 처리)
   - **캡처 모드**: 버튼 숨겨짐 → 장마다 캡처 → 4:5로 자르기. 화면 한 번 누르면 원래대로
4. 수정은 말로: "3번 제목 더 짧게", "5번 표에 한 줄 추가"

## 메모
- 폰트: 채팅에선 Pretendard 대신 애플 기본 고딕(아이폰) / Noto Sans KR로 나옴. 거의 같음
- 사진: 픽사베이(pixabay.com)에서 "smartphone night" 같은 영어로 검색해서 받으면 편함
- 원본 템플릿 파일: `cardnews/adman-chat-template.html`

## 프롬프트

````
너는 인스타 카드뉴스 계정 '애드맨(@adman_park)'의 전속 디자이너야.
아래 [템플릿 HTML]을 HTML 아티팩트로 만들어.
디자인·CSS·스크립트는 한 글자도 바꾸지 말고, ACCOUNT.vol 과 SLIDES 배열만 [주제]에 맞게 새로 채워.

[주제]: 여기에 주제 쓰기
[회차]: VOL.003

## 문구 규칙
- 7장 구성: 1 훅 / 2 공감(BEFORE) / 3 방법(STEP 1) / 4 복붙 프롬프트(PROMPT) / 5 결과(RESULT) / 6 주의(WARNING) / 7 팔로우(FOLLOW)
- 제목은 2줄(\n으로 줄바꿈), 한 줄 12자 안팎. 강조 단어 1~2개는 **두 별표**로 감싸기
- 1장 제목: 평범한 목표 말고 "누구처럼 되기"로 바꿔 말하기. 다들 아는 사람·캐릭터 이름을 **강조**
  예) 다리근육 키우기 → "한마 바키 다리 만들기" / 피부 좋아지기 → "손예진 피부 되기"
      롤 잘하기 → "페이커 되는 법" / 그림 잘 그리기 → "피카소처럼 그리기" / 돈 모으기 → "워런 버핏처럼 돈 모으기"
  숫자(1장, 3분 등)도 같이 넣기. 예) "카드 명세서 1장으로\n**워런 버핏**처럼 돈 모으기"
- 1장 부제: 타겟을 콕 집기. 예) "○○하는 사람 필독", "○○ 모르면 손해"
- 부제는 한 줄 20자 안팎, "~요/~니다" 구어체
- 4장 프롬프트는 실제로 복붙해서 바로 쓸 수 있게. 번호 앞 ①②③는 **별표**로 강조
- 5장 결과는 "예시" 태그 달기. 확인 안 된 수치·사실은 지어내지 않기
- 7장은 댓글 참여 유도. card type 은 comment, 키워드는 주제에 맞는 2~3글자 한 단어
  예) title:"댓글에 **'명세서'**\n남기면 바로 보내드림", sub:"이미지라 복사 안 되죠? 원문은 DM으로 드려요", card:{type:'comment', keyword:'명세서'}
- hot:true 는 1장·6장·7장 라벨만. size:76 은 1장·7장만
- 1장은 hero:true (표 없이 사진을 크게, 아래만 어둡게). 사진은 실존 연예인 말고 무료 사진으로: 주제 분위기에 맞는 뒷모습·옆모습·클로즈업
- 카드 type 은 chat / notes / prompt / rows / bars / comment / profile 중에서 템플릿 예시 형식 그대로 사용 (bars 형식: items:[['라벨','값',퍼센트숫자,강조true/false]], big:'−90%', bigLabel:'시간 절약')

## 다 만들고 나서
7장 제목·부제만 표로 짧게 보여주고, 인스타 캡션(해시태그는 항상 이 5개 그대로: #애드맨 #AI꿀팁 #챗GPT활용 #AI활용 #생활꿀팁, 7장과 같은 키워드로 "댓글에 '○○' 남기면 프롬프트 원문 DM" 1줄 포함)을 같이 줘.

[템플릿 HTML]
```html
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>애드맨 카드뉴스</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@500;700;800&family=IBM+Plex+Mono:wght@500;600&display=swap">
<style>
:root{--bg:#0A0A0A;--fg:#F2F2F2;--g1:#C8C8C8;--g2:#8C8C8C;--g3:#6A6A6A;--line:#2A2A2A;--card:rgba(20,20,20,.7);--accent:#FF5A00;--sans:'Pretendard','Apple SD Gothic Neo','Noto Sans KR',sans-serif;--mono:'IBM Plex Mono',monospace;color-scheme:dark}
html,body{margin:0;background:#000;color:var(--fg);font-family:var(--sans)}
.bar{position:sticky;top:0;z-index:5;display:flex;gap:8px;flex-wrap:wrap;padding:10px 16px;background:#000;border-bottom:1px solid var(--line)}
.btn{font:700 14px var(--sans);color:var(--fg);background:#1A1A1A;border:1px solid var(--line);padding:10px 14px;border-radius:0;cursor:pointer}
.btn.hot{background:var(--accent);color:#0A0A0A;border-color:var(--accent)}
.wrap{display:flex;flex-direction:column;gap:14px;padding:16px}
.item{display:flex;flex-direction:column;gap:8px;width:100%;max-width:540px;margin:0 auto}
.holder{width:100%;aspect-ratio:1080/1350;position:relative;overflow:hidden}
.slide{position:absolute;left:0;top:0;width:1080px;height:1350px;transform-origin:0 0;overflow:hidden;background:var(--bg);color:var(--fg)}
.bgp{position:absolute;left:-60px;top:-60px;width:1200px;height:1470px;object-fit:cover;filter:blur(18px) grayscale(.4)}
.dim{position:absolute;inset:0;background:rgba(10,10,10,.72)}
.head{position:absolute;left:120px;right:120px;top:120px;opacity:.6;display:flex;justify-content:space-between;align-items:center;font:600 18px var(--mono);letter-spacing:.16em;color:var(--g3)}
.head i{display:inline-block;width:10px;height:10px;background:var(--accent);margin-right:12px}
.card{position:absolute;left:120px;top:200px;width:840px;box-sizing:border-box;padding:44px 48px;background:var(--card);border:1px solid var(--line);opacity:.45;filter:saturate(.7);display:flex;flex-direction:column;gap:28px}
.fig{position:absolute;left:0;top:-40px;font:600 17px var(--mono);letter-spacing:.16em;color:var(--g3)}
.br{position:absolute;width:26px;height:26px;border:0 solid var(--accent)}
.br.a{left:-10px;top:-10px;border-left-width:3px;border-top-width:3px}.br.b{right:-10px;top:-10px;border-right-width:3px;border-top-width:3px}
.br.c{left:-10px;bottom:-10px;border-left-width:3px;border-bottom-width:3px}.br.d{right:-10px;bottom:-10px;border-right-width:3px;border-bottom-width:3px}
.txt{position:absolute;left:120px;right:120px;bottom:230px;display:flex;flex-direction:column}
.rule{width:64px;height:6px;background:var(--accent);margin-bottom:24px}
.label{font:600 22px var(--mono);letter-spacing:.16em;color:var(--g2)}
.label.hot{color:var(--accent)}
.title{margin:22px 0 0;font-weight:800;line-height:1.16;letter-spacing:-.035em;white-space:pre-line}
.sub{margin:22px 0 0;font-size:32px;font-weight:500;color:var(--g2)}
.em{color:var(--accent)}
.foot{position:absolute;left:120px;right:120px;bottom:120px;padding-top:22px;border-top:1px solid rgba(255,255,255,.1);display:flex;justify-content:space-between;align-items:center;font:500 20px var(--mono);letter-spacing:.08em;color:var(--g3)}
.foot span{display:flex;align-items:center;gap:14px}
.av{width:44px;height:44px;object-fit:cover;image-rendering:pixelated;border:1px solid var(--line);background:var(--accent);display:flex;align-items:center;justify-content:center;color:#0A0A0A;font:800 22px var(--sans)}
.bub{max-width:70%;padding:18px 24px;font-size:28px;font-weight:700;background:#1C1C1C;color:var(--g1)}
.bub.r{align-self:flex-end;background:rgba(255,90,0,.14);color:var(--accent);border:1px solid rgba(255,90,0,.4)}
.tag{font:600 16px var(--mono);letter-spacing:.14em;color:var(--accent);border:1px solid var(--accent);padding:8px 12px}
.row2{display:flex;justify-content:space-between;align-items:center;gap:20px}
.rows{display:flex;flex-direction:column}
.rows div{display:flex;justify-content:space-between;gap:24px;padding:20px 0;border-top:1px solid rgba(255,255,255,.08);font-size:26px}
.rows div b{font-weight:800;text-align:right}
.note{padding:20px 24px;border:1px dashed #3A3A3A;font-size:28px;font-weight:700;color:var(--g2)}
.ptxt{font-size:30px;font-weight:500;line-height:1.7;color:var(--g1);white-space:pre-line}
.send{width:60px;height:60px;background:var(--accent);display:flex;align-items:center;justify-content:center}
.big{font-size:96px;font-weight:800;letter-spacing:-.04em;color:var(--accent)}
.track{height:14px;background:#262626}.track i{display:block;height:14px;background:var(--accent)}
.cta{display:grid;grid-template-columns:1fr 1fr;gap:14px}.cta div{padding:22px;font-size:26px;font-weight:800;text-align:center;border:1px solid rgba(255,255,255,.16)}
.cta div:first-child{background:var(--accent);color:#0A0A0A;border-color:var(--accent)}
body.cap .bar,body.cap .btn{display:none}
body.cap .wrap{padding:0;gap:0}
body.cap .item{max-width:none}
</style>
</head>
<body>
<div class="bar">
<label class="btn hot">프사 넣기<input id="avIn" type="file" accept="image/*" hidden></label>
<button class="btn" id="capBtn" type="button">캡처 모드</button>
</div>
<div class="wrap" id="wrap"></div>
<script>
/* ===== 여기만 바꾸면 됨 ===== */
const ACCOUNT = { name:'애드맨', handle:'@adman_park', vol:'VOL.002',
  bio:'남들은 이미 AI로 앞서가는 중.\n모르면 손해 보는 AI 정보\n알아두면 쓸모 있는 AI 꿀팁' };

const SLIDES = [
 { fig:'CHAT', label:'AI 꿀팁 · 연애', hot:true, size:76, hero:true,
   title:'카톡 캡처 1장이면\n상대 **속마음** 다 보입니다', sub:'읽씹당하고 혼자 고민하는 사람 필독',
   card:{ type:'chat', items:[['l','오늘 좀 바빠서 ㅎㅎ'],['r','아 그래? 괜찮아!'],['l','ㅇㅇ']], tag:'AI ANALYSIS', note:'신호 **3개** 발견' } },
 { fig:'OVERTHINK', label:'BEFORE', title:'혼자 해석하면\n**꼭** 꼬입니다', sub:'답장 하나에 밤새 고민한 적 있죠?',
   card:{ type:'notes', lead:'ㅇㅇ', items:['바쁜가?','내가 싫은가?','화났나?'] } },
 { fig:'PRIVACY', label:'STEP 1', title:'이름·번호는\n**꼭 가리고** 캡처', sub:'상대 개인정보부터 지키세요',
   card:{ type:'chat', items:[['l','████ 오늘 시간 돼?'],['r','응 저녁 괜찮아']], tag:'NAME · PHOTO · NUMBER HIDDEN' } },
 { fig:'PROMPT', label:'PROMPT', title:'이대로 **복사**해서\n붙여넣으세요', sub:'캡처만 첨부하면 끝',
   card:{ type:'prompt', text:'첨부한 카톡 대화를 보고 정리해줘.\n**①** 대화 초반과 최근의 말투 변화\n**②** 호감 신호와 거리 두기 신호\n**③** 지금 보내면 좋은 답장 3개\n(가볍게 / 솔직하게 / 유머)\n확실하지 않은 건 "추측"이라고 표시해줘.', foot:'+ 캡처 1장 첨부' } },
 { fig:'OUTPUT', label:'RESULT', title:'**3분** 뒤엔\n이게 나와요', sub:'말투 변화·신호·추천 답장까지',
   card:{ type:'rows', head:'AI 분석 결과', tag:'예시', rows:[['① 말투 변화','초반보다 답이 짧아짐'],['② 신호','호감 · 거리 두기 구분'],['③ 추천 답장','가볍게 / 솔직하게 / 유머',true]] } },
 { fig:'CHECK', label:'WARNING', hot:true, title:'AI 분석은\n**정답**이 아닙니다', sub:'참고만 하고, 진짜 마음은 직접 물어보세요',
   card:{ type:'rows', head:'AI 분석 결과', tag:'GUESS', rows:[['상대 마음','추측',true],['근거','말투와 답장 길이뿐'],['확인 방법','직접 물어보기']] } },
 { fig:'COMMENT', label:'COMMENT', hot:true, size:76, title:"댓글에 **'분석'**\n남기면 바로 보내드림", sub:'이미지라 복사 안 되죠? 원문은 DM으로 드려요',
   card:{ type:'comment', keyword:'분석' } },
];
/* ===== 여기까지 ===== */

const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const em=s=>esc(s).replace(/\*\*(.+?)\*\*/g,'<span class="em">$1</span>');
let avatar=null; try{avatar=localStorage.getItem('adman-av')}catch(e){}
const photos={};
const avHtml=(n)=>avatar?`<img class="av" src="${avatar}" alt="" style="width:${n}px;height:${n}px">`:`<div class="av" style="width:${n}px;height:${n}px;font-size:${n/2}px">${esc(ACCOUNT.name[0])}</div>`;
function cardHtml(c){
  if(c.type==='chat') return c.items.map(([w,t])=>`<div class="bub ${w==='r'?'r':''}">${esc(t)}</div>`).join('')+(c.tag?`<div class="row2"><span class="tag">■ ${esc(c.tag)}</span><span style="font-size:26px;font-weight:700">${em(c.note||'')}</span></div>`:'');
  if(c.type==='notes') return `<div class="bub" style="align-self:flex-start">${esc(c.lead)}</div>`+c.items.map(t=>`<div class="note">${esc(t)}</div>`).join('');
  if(c.type==='prompt') return `<div class="ptxt">${em(c.text)}</div><div class="row2" style="padding-top:24px;border-top:1px solid rgba(255,255,255,.08)"><span style="font-size:22px;font-weight:700;color:var(--g3)">${esc(c.foot||'챗GPT · 클로드 · 제미나이')}</span><div class="send"><svg width="28" height="28" viewBox="0 0 24 24"><path d="M12 19V5M5 12l7-7 7 7" fill="none" stroke="#0A0A0A" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg></div></div>`;
  if(c.type==='rows') return `<div class="row2"><span style="font-size:28px;font-weight:800">${esc(c.head||'')}</span>${c.tag?`<span class="tag">■ ${esc(c.tag)}</span>`:''}</div><div class="rows">${c.rows.map(([a,b,h])=>`<div><span style="color:var(--g2)">${esc(a)}</span><b${h?' class="em"':''}>${esc(b)}</b></div>`).join('')}</div>`;
  if(c.type==='bars') return `<div style="font-size:24px;font-weight:700;color:var(--g2)">${esc(c.head||'')}</div>`+c.items.map(([a,b,p,h])=>`<div style="display:flex;flex-direction:column;gap:14px"><div class="row2" style="font-size:28px;font-weight:700"><span${h?'':' style="color:var(--g2)"'}>${esc(a)}</span><span${h?' class="em"':' style="color:var(--g2)"'}>${esc(b)}</span></div><div class="track"><i style="width:${p}%;${h?'':'background:#3A3A3A'}"></i></div></div>`).join('')+(c.big?`<div style="display:flex;align-items:baseline;gap:18px;padding-top:32px;border-top:1px solid rgba(255,255,255,.08)"><span class="big">${esc(c.big)}</span><span style="font-size:26px;font-weight:700;color:var(--g2)">${esc(c.bigLabel||'')}</span></div>`:'');
  if(c.type==='comment') return `<div class="row2" style="justify-content:flex-start;gap:18px;padding-bottom:22px;border-bottom:1px solid rgba(255,255,255,.08)"><div style="width:56px;height:56px;background:#3A3A3A"></div><div style="display:flex;flex-direction:column;gap:6px"><span style="font-size:22px;font-weight:700;color:var(--g2)">댓글</span><span style="font-size:30px;font-weight:800">${esc(c.keyword)}</span></div></div><div class="row2" style="justify-content:flex-start;gap:18px">${avHtml(56)}<span style="font-size:24px;font-weight:700;color:var(--g2)">${esc(ACCOUNT.handle)} · DM</span></div><div class="bub r">${esc(c.reply||'요청하신 프롬프트 원문 보내드려요')}</div><div class="cta"><div>댓글 남기기</div><div>팔로우</div></div>`;
  if(c.type==='profile') return `<div style="display:flex;align-items:center;gap:28px">${avHtml(128)}<div style="display:flex;flex-direction:column;gap:6px"><span style="font-size:38px;font-weight:800">${esc(ACCOUNT.name)}</span><span style="font-size:26px;font-weight:700;color:var(--g2)">${esc(ACCOUNT.handle)}</span></div></div><div style="font-size:27px;font-weight:500;line-height:1.6;color:var(--g1);white-space:pre-line">${esc(ACCOUNT.bio)}</div><div class="cta"><div>팔로우</div><div>저장하기</div></div>`;
  return '';
}
function slideHtml(s,i){
  const n=String(i+1).padStart(2,'0'), t=String(SLIDES.length).padStart(2,'0');
  const bg=s.hero?(photos[i]?`<img src="${photos[i]}" alt="" style="position:absolute;inset:0;width:1080px;height:1350px;object-fit:cover;object-position:30% 20%"><div style="position:absolute;inset:0;background:linear-gradient(180deg,rgba(10,10,10,.25) 0%,rgba(10,10,10,.1) 30%,rgba(10,10,10,.75) 58%,rgba(10,10,10,.96) 78%)"></div>`:'<div class="dim"></div>'):`${photos[i]?`<img class="bgp" src="${photos[i]}" alt="">`:''}<div class="dim"></div>`;
  return `${bg}
  <div class="head"><span>${esc(ACCOUNT.name==='애드맨'?'ADMAN':ACCOUNT.name)} — AI REPORT</span><span><i></i>${esc(ACCOUNT.vol)}</span></div>
  ${s.card&&!s.hero?`<div class="card"><div class="fig">FIG.${n} — ${esc(s.fig||'')}</div><div class="br a"></div><div class="br b"></div><div class="br c"></div><div class="br d"></div>${cardHtml(s.card)}</div>`:''}
  <div class="txt"><div class="rule"></div><div class="label${s.hot?' hot':''}">${esc(s.label)}</div><div class="title" style="font-size:${s.size||84}px">${em(s.title)}</div><p class="sub">${esc(s.sub)}</p></div>
  <div class="foot"><span>${avHtml(44)}${esc(ACCOUNT.handle)}</span><span>${n} / ${t}</span></div>`;
}
const wrap=document.getElementById('wrap');
function render(){
  wrap.innerHTML=SLIDES.map((s,i)=>`<div class="item"><div class="holder"><div class="slide">${slideHtml(s,i)}</div></div><label class="btn">${i+1}번 배경 사진 넣기<input type="file" accept="image/*" data-i="${i}" hidden></label></div>`).join('');
  fit();
}
function fit(){document.querySelectorAll('.holder').forEach(h=>{h.firstElementChild.style.transform=`scale(${h.clientWidth/1080})`})}
function read(file,cb){const r=new FileReader();r.onload=()=>cb(r.result);r.readAsDataURL(file)}
wrap.addEventListener('change',e=>{const i=e.target.dataset.i;if(i!=null&&e.target.files[0])read(e.target.files[0],u=>{photos[i]=u;render()})});
document.getElementById('avIn').addEventListener('change',e=>{if(e.target.files[0])read(e.target.files[0],u=>{avatar=u;try{localStorage.setItem('adman-av',u)}catch(x){}render()})});
document.getElementById('capBtn').addEventListener('click',()=>{document.body.classList.add('cap');fit()});
wrap.addEventListener('click',()=>{if(document.body.classList.contains('cap')){document.body.classList.remove('cap');fit()}});
window.addEventListener('resize',fit);
render();
</script>
</body>
</html>
```
````
