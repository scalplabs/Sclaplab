import numpy as np, json, sys, wave, subprocess
D=sys.argv[1]; SR=44100
segs=json.load(open(D+'/segs.json')); T=json.load(open(D+'/meta.json'))['T']; N=int(SR*T)
def load(p):
    raw=subprocess.check_output(['ffmpeg','-v','error','-i',p,'-f','s16le','-ac','1','-ar',str(SR),'-']); return np.frombuffer(raw,np.int16).astype(float)/32768
voice=np.zeros(N)
for s in segs:
    x=load(f"{D}/vo4/v{s['i']:02d}.wav"); i=int(s['start']*SR); j=min(N,i+len(x)); voice[i:j]+=x[:j-i]
rng=np.random.default_rng(3)
def env(n,a=0.002,d=0.2): t=np.arange(n)/SR; return np.minimum(1,t/a)*np.exp(-t/d)
def place(buf,sig,t,g=1.0):
    i=int(round(t*SR))
    if i<0 or i>=N: return
    j=min(N,i+len(sig)); buf[i:j]+=sig[:j-i]*g
def note(f,dur,a=0.4,d=1.6): n=int(dur*SR); t=np.arange(n)/SR; return (2*np.abs(2*((f*t)%1)-1)-1)*env(n,a,d)
midi=lambda m:440*2**((m-69)/12)
bed=np.zeros(N); BEAT=60/100
chords=[[57,60,64],[53,57,60],[48,52,55],[55,59,62]]
bar=0; t=0
while t<T:
    for m in chords[bar%4]: place(bed,note(midi(m),4*BEAT,0.5,2.5),t,0.05)
    for k in range(4):
        n=int(0.3*SR); tt=np.arange(n)/SR; kk=np.sin(2*np.pi*np.cumsum(45+60*np.exp(-tt/0.04))/SR)*env(n,0.001,0.12); place(bed,kk,t+k*BEAT,0.35)
        n2=int(0.03*SR); place(bed,rng.standard_normal(n2)*env(n2,0.0005,0.01),t+k*BEAT+BEAT/2,0.05)
    t+=4*BEAT; bar+=1
# duck bed under voice
ve=np.convolve(np.abs(voice),np.ones(2205)/2205,'same'); duck=1-0.6*np.clip(ve/0.05,0,1); bed*=duck
sfx=np.zeros(N)
def whoosh(L=0.25):
    n=int(L*SR); x=rng.standard_normal(n); out=np.zeros(n); s=0
    for i in range(n): a=0.02+0.2*np.sin(np.pi*i/n); s+=a*(x[i]-s); out[i]=s
    return out*np.sin(np.pi*np.arange(n)/n)
def thump(): n=int(0.18*SR); t=np.arange(n)/SR; return np.sin(2*np.pi*(120+160*np.exp(-t/0.015))*t)*env(n,0.001,0.06)
def tick(): n=int(0.025*SR); t=np.arange(n)/SR; return np.sin(2*np.pi*3000*t)*env(n,0.0002,0.004)
prev=None
for s in segs:
    if s['scene']!=prev and s['scene']!='hook': place(sfx,whoosh(),s['start']-0.15,0.35); prev=s['scene']
place(sfx,thump(),segs[0]['start']+0.03,0.7)
def beep(f=1800,L=0.09): n=int(L*SR); t=np.arange(n)/SR; return np.sin(2*np.pi*f*t)*env(n,0.001,0.03)
for s in segs:
    if s['scene'] in ('c0','c1','c2') and s['scene']!=segs[s['i']-1]['scene']:
        place(sfx,whoosh(0.5)*0.8,s['start']-0.05,0.4); place(sfx,beep(1600),s['start']+0.45,0.35); place(sfx,beep(2400),s['start']+0.55,0.3)
q=[s for s in segs if s['scene']=='quiz'][0]
for k in range(3): place(sfx,beep(1200 if k<2 else 1200,0.12),q['start']+0.9+k*0.55,0.5)
rv=[s for s in segs if s['scene']=='reveal'][0]
place(sfx,thump(),rv['start']+0.02,0.9); place(sfx,beep(2400,0.15),rv['start']+0.05,0.35)
tp=[s for s in segs if s['scene']=='tip'][0]
for k in range(3): place(sfx,tick(),tp['start']+0.6+k*0.4,0.6)
out=[s for s in segs if s['scene']=='outro']
place(sfx,tick(),out[0]['start']+0.6,0.6); place(sfx,tick(),out[1]['start']+0.2,0.4); place(sfx,tick(),out[1]['start']+0.35,0.4); place(sfx,tick(),out[2]['start']+0.15,0.6)
mix=voice*1.0+bed*0.35+sfx*0.45
mix/=np.max(np.abs(mix))*1.05
with wave.open(D+'/audio.wav','wb') as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((mix*32767).astype(np.int16).tobytes())
print('ok',T)
