import json,sys,os,subprocess
D=sys.argv[1]
L=json.load(open(D+'/lines.json'));segs=[];t=0.1
for i,l in enumerate(L):
    d=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',f'{D}/vo4/v{i:02d}.wav']))
    segs.append(dict(i=i,start=round(t,3),dur=round(d,3),sub=l[0],scene=l[2])); t+=d+l[3]
T=round(t+1.6,2)
CL={"c0":[500,760,440,130,2.0],"c1":[40,400,290,680,1.45],"c2":[262,1136,110,132,3.0],"c3":[430,200,560,880,1.1]}
json.dump(segs,open(D+'/segs.json','w'),ensure_ascii=False)
json.dump(dict(T=T),open(D+'/meta.json','w'))
h=open(D+'/photo.html').read().replace('SEGS_JSON',json.dumps(segs,ensure_ascii=False)).replace('TOTAL',str(T)).replace('CLUES_JSON',json.dumps(CL))
open(D+'/built.html','w').write(h);print('T',T)
