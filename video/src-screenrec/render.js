const {chromium}=require('playwright');const path=require('path'),fs=require('fs');
(async()=>{const [dir,mode,arg]=process.argv.slice(2);
const b=await chromium.launch();const p=await b.newPage({viewport:{width:1920,height:1080}});
p.on('pageerror',e=>console.log('ERR',e.message));
await p.goto('file://'+path.join(dir,'index.html'));await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(300);
if(mode==='test'){for(const t of arg.split(',').map(Number)){await p.evaluate(t=>seek(t),t);await p.screenshot({path:`${dir}/t${t}.png`})}}
else{const N=Math.round(Number(arg)*30);const out=dir+'/frames';fs.rmSync(out,{recursive:true,force:true});fs.mkdirSync(out);
for(let f=0;f<N;f++){await p.evaluate(t=>seek(t),f*1000/30);await p.screenshot({path:`${out}/${String(f).padStart(4,'0')}.png`})}}
await b.close()})();
