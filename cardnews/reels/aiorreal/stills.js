const {chromium}=require('playwright');const D=process.argv[2];const ts=process.argv.slice(3).map(Number);
(async()=>{const br=await chromium.launch();const p=await br.newPage({viewport:{width:1080,height:1920},deviceScaleFactor:1});
await p.goto('http://127.0.0.1:8765/reel11/built.html');await p.waitForFunction(()=>window.ready,null,{timeout:60000});
for(let i=0;i<ts.length;i++){await p.evaluate(t=>window.seek(t),ts[i]);await p.waitForTimeout(50);await p.screenshot({path:`${D}/st${String(i).padStart(2,'0')}.png`});}
await br.close();})();
