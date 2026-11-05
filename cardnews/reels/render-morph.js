const {chromium}=require('playwright');const D=process.argv[2];const SUB=240,N=20*SUB;
(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:1080,height:1920}});
await p.goto('file://'+D+'/morph-built.html');await p.waitForTimeout(2000);await p.evaluate(()=>document.fonts.ready);
const t0=Date.now();
for(let i=0;i<N;i++){await p.evaluate(t=>window.seek(t),i/SUB);await p.screenshot({path:`${D}/fr/f${String(i).padStart(5,'0')}.jpg`,type:'jpeg',quality:92});}
console.log('done',(Date.now()-t0)/1000);await b.close();})();
