import json,sys,os,subprocess
D=sys.argv[1];S=os.path.dirname(D);mode=sys.argv[2]  # est|real
L=json.load(open(D+'/lines.json'));segs=[];t=0.1
for i,l in enumerate(L):
    if mode=='real': d=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',f'{D}/vo4/v{i:02d}.wav']))
    else: d=0.2+0.082*len(l[1].replace(' ',''))
    segs.append(dict(i=i,start=round(t,3),dur=round(d,3),sub=l[0],scene=l[2])); t+=d+l[3]
T=round(t+1.8,2)
json.dump(segs,open(D+'/segs.json','w'),ensure_ascii=False)
json.dump(dict(T=T,ts=[round(s['start']+s['dur']*0.75,2) for s in segs]),open(D+'/meta.json','w'))
h=open(D+'/office.html').read().replace('SEGS_JSON',json.dumps(segs,ensure_ascii=False)).replace('TOTAL',str(T))
open(D+'/built.html','w').write(h);print('T',T)
