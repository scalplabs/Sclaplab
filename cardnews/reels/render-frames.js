const {chromium}=require('playwright');const R=process.argv[2];const FPS=30,N=600;
(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:1080,height:1920}});
await p.goto('file://'+R+'/reel-built.html');await p.waitForTimeout(1500);await p.evaluate(()=>document.fonts.ready);
const t0=Date.now();
for(let i=0;i<N;i++){await p.evaluate(t=>window.render(t),i/FPS);await p.screenshot({path:`${R}/frames/f${String(i).padStart(4,'0')}.jpg`,type:'jpeg',quality:93});}
console.log('frames done in',(Date.now()-t0)/1000,'s');await b.close();})();
