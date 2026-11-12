const {chromium}=require('playwright');const D=process.argv[2];const a=+process.argv[3],b=+process.argv[4];const q=process.argv[5]||'';const FPS=30;
(async()=>{const br=await chromium.launch();const p=await br.newPage({viewport:{width:1080,height:1920},deviceScaleFactor:2});
await p.goto('http://127.0.0.1:8765/reel10/built.html'+q);await p.waitForFunction(()=>window.ready,null,{timeout:120000});const t0=Date.now();
for(let i=a;i<b;i++){if(require('fs').existsSync(`${D}/fr/f${String(i).padStart(5,'0')}.png`))continue;await p.evaluate(t=>window.seek(t),i/FPS);await new Promise(r=>setTimeout(r,0));await p.screenshot({path:`${D}/fr/f${String(i).padStart(5,'0')}.png`});}
console.log('done',a,b,(Date.now()-t0)/1000);await br.close();})();
