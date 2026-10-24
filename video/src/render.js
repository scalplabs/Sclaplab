const {chromium}=require('playwright');const path=require('path');
(async()=>{const dir=process.argv[2],mode=process.argv[3];
const b=await chromium.launch();const p=await b.newPage({viewport:{width:1080,height:1920}});
p.on('pageerror',e=>console.log('ERR',e.message));
await p.goto('file://'+path.join(dir,'index.html'));await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(300);
if(mode==='test'){for(const t of [1000,2200,3800,6800,9500,11500,14400]){await p.evaluate(t=>seek(t),t);await p.screenshot({path:`${dir}/../t${t}.png`})}}
else{const N=Math.round(14.6*30);const fs=require('fs');fs.mkdirSync(dir+'/../frames',{recursive:true});
for(let f=0;f<N;f++){await p.evaluate(t=>seek(t),f*1000/30);await p.screenshot({path:`${dir}/../frames/${String(f).padStart(4,'0')}.png`})}}
await b.close()})();
