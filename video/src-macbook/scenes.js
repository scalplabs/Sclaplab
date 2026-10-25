const SKIN='#F6C9A3',HAIR='#4A2E1F',PANTS='#3D5A99';
const s=(tag,a,c)=>`<${tag} class="s" pathLength="1" style="--c:${c}" ${a}/>`;
const l=(d,c)=>`<path class="l" pathLength="1" style="--c:${c}" d="${d}"/>`;

function head(cx,cy,closed=false){
  return s('circle',`cx="${cx}" cy="${cy-4}" r="46"`,HAIR)+
   s('circle',`cx="${cx}" cy="${cy+4}" r="40"`,SKIN)+
   s('path',`d="M${cx-42} ${cy} Q${cx-34} ${cy-48} ${cx} ${cy-46} Q${cx+36} ${cy-48} ${cx+44} ${cy} Q${cx+22} ${cy-20} ${cx+4} ${cy-16} Q${cx-18} ${cy-24} ${cx-42} ${cy}Z"`,HAIR)+
   (closed? `<path class="m" pathLength="1" d="M${cx-22} ${cy+8} q8 6 16 0 M${cx+6} ${cy+8} q8 6 16 0"/>`
          : `<circle class="k" cx="${cx-14}" cy="${cy+7}" r="5.5"/><circle class="k" cx="${cx+14}" cy="${cy+7}" r="5.5"/>`)+
   `<circle class="bl" cx="${cx-24}" cy="${cy+20}" r="7"/><circle class="bl" cx="${cx+24}" cy="${cy+20}" r="7"/>`+
   `<path class="m" pathLength="1" d="M${cx-10} ${cy+22} Q${cx} ${cy+31} ${cx+10} ${cy+22}"/>`;
}
const arm=(x,y,ang,len=72)=>s('rect',`x="${x-11}" y="${y}" width="22" height="${len}" rx="11" transform="rotate(${ang} ${x} ${y})"`,SKIN);
function standing(x,shirt,armL=20,armR=-20){
  return arm(x-30,170,armL)+arm(x+30,170,armR)+
   s('rect',`x="${x-26}" y="236" width="22" height="62" rx="8"`,PANTS)+
   s('rect',`x="${x+4}" y="236" width="22" height="62" rx="8"`,PANTS)+
   s('ellipse',`cx="${x-18}" cy="300" rx="20" ry="11"`,'#fff')+
   s('ellipse',`cx="${x+18}" cy="300" rx="20" ry="11"`,'#fff')+
   s('rect',`x="${x-34}" y="160" width="68" height="84" rx="20"`,shirt)+
   head(x,116);
}
const ground=(c='#8FD18B')=>s('path',`d="M-10 290 Q200 262 410 290 L410 410 L-10 410Z"`,c);
const sun=()=>s('circle',`cx="335" cy="62" r="30"`,'#FFD54A')+s('path',`d="M40 80 q0-26 30-26 q10-20 34-12 q24-4 30 20 q22 2 18 18Z"`,'#fff');
const sky=(c)=>`<rect class="sky" style="--sky:${c||'#BFE6FF'}" width="400" height="400"/>`;

const SCENES=[
 // bike
 ()=>sky()+sun()+ground()+
  s('circle','cx="105" cy="318" r="52"','#333')+s('circle','cx="105" cy="318" r="36"','#EDEDED')+
  s('circle','cx="295" cy="318" r="52"','#333')+s('circle','cx="295" cy="318" r="36"','#EDEDED')+
  l('M105 318 L175 248 L205 318 Z M175 248 L268 236 L295 318 M205 318 L268 236','#E53935')+
  l('M250 210 L268 236 M240 208 L262 206','#555')+
  arm(170,166,-62,92)+
  s('rect','x="168" y="226" width="26" height="70" rx="10" transform="rotate(-20 181 230)"',PANTS)+
  s('ellipse','cx="214" cy="300" rx="20" ry="11"','#fff')+
  s('ellipse','cx="176" cy="248" rx="26" ry="9"','#222')+
  s('rect','x="146" y="150" width="64" height="88" rx="20" transform="rotate(12 178 194)"','#FF8A3D')+
  arm(196,166,-70,90)+s('circle','cx="262" cy="206" r="11"',SKIN)+
  head(170,108),
 // slide
 ()=>sky()+sun()+ground()+
  l('M58 160 L58 300 M100 160 L100 300 M58 195 L100 195 M58 230 L100 230 M58 265 L100 265','#5C6BC0')+
  s('rect','x="50" y="150" width="80" height="16" rx="6"','#5C6BC0')+
  s('path','d="M120 150 L150 150 Q250 230 360 290 L330 306 Q230 250 120 168Z"','#FF7043')+
  `<g transform="translate(-40 -88) scale(.82)">`+arm(210,170,160)+arm(250,170,-160)+
  s('rect','x="196" y="236" width="56" height="34" rx="12"',PANTS)+
  s('rect','x="196" y="160" width="68" height="84" rx="20"','#29B6F6')+head(230,116)+`</g>`,
 // sleeping w/ cat
 ()=>sky('#FFE3B8')+s('circle','cx="330" cy="70" r="26"','#FFF6C9')+
  s('rect','x="20" y="250" width="360" height="140" rx="20"','#C8A2FF')+
  s('ellipse','cx="120" cy="250" rx="90" ry="40"','#fff')+
  `<g transform="rotate(-12 120 210)">`+head(120,208,true)+`</g>`+
  s('ellipse','cx="255" cy="262" rx="70" ry="42"','#FFA94D')+
  s('path','d="M290 230 L300 196 L318 222Z M330 230 L344 198 L352 232Z"','#FFA94D')+
  s('circle','cx="322" cy="246" r="34"','#FFA94D')+
  `<path class="m" pathLength="1" d="M305 246 q6 5 12 0 M327 246 q6 5 12 0"/>`+
  s('path','d="M326 260 l-4 4 l-4 -4Z"','#FF7A8A')+
  s('rect','x="150" y="250" width="130" height="24" rx="12" transform="rotate(-6 150 262)"',SKIN)+
  s('path','d="M20 300 Q200 270 380 300 L380 390 L20 390Z"','#9D7BEA'),
 // balloon
 ()=>sky()+sun()+ground()+
  l('M262 102 Q250 150 238 174','#666')+
  s('ellipse','cx="275" cy="62" rx="44" ry="52"','#FF4D6D')+s('path','d="M268 112 l7 10 l7 -10Z"','#FF4D6D')+
  standing(190,'#FFD23F',22,-150)+s('circle','cx="240" cy="166" r="11"',SKIN),
 // ball
 ()=>sky()+sun()+ground()+
  standing(170,'#5BD08A',40,-40)+
  s('circle','cx="275" cy="290" r="36"','#fff')+
  s('path','d="M275 272 l15 11 l-6 18 h-18 l-6 -18Z"','#222'),
];
const COVER=()=>standing(200,'#fff',20,-160)+s('circle','cx="214" cy="104" r="11"',SKIN)+
  s('path','d="M60 300 Q200 280 340 300"','#fff')+
  s('path','d="M60 90 l8 18 l20 2 l-15 13 l5 20 l-18 -10 l-18 10 l5 -20 l-15 -13 l20 -2Z"','#fff')+
  s('path','d="M320 160 l6 14 l15 1 l-11 10 l4 15 l-14 -8 l-14 8 l4 -15 l-11 -10 l15 -1Z"','#fff');
const CAPS=['민준이가 집 앞에서 자전거를 타요.','민준이가 미끄럼틀을 타요.','민준이가 고양이를 안고 자요.','민준이가 풍선을 들고 있어요.','민준이가 공놀이를 해요.'];
