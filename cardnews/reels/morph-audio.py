import numpy as np, json, sys, wave
D=sys.argv[1]; SR=44100; T=20.0; BEAT=0.5; N=int(SR*T)
rng=np.random.default_rng(7)
def env(n,a=0.002,d=0.2):
    t=np.arange(n)/SR; e=np.minimum(1,t/a)*np.exp(-t/d); return e
def place(buf,sig,t,gain=1.0):
    i=int(round(t*SR)); 
    if i>=N: return
    j=min(N,i+len(sig)); buf[i:j]+=sig[:j-i]*gain
def lp(x,a): # one-pole lowpass
    y=np.empty_like(x); s=0.0
    for i in range(len(x)): s+=a*(x[i]-s); y[i]=s
    return y
music=np.zeros(N); sfx=np.zeros(N); duck=np.ones(N)
# kick
def kick():
    n=int(0.35*SR); t=np.arange(n)/SR; f=45+75*np.exp(-t/0.04); ph=2*np.pi*np.cumsum(f)/SR
    return np.sin(ph)*env(n,0.001,0.16)+0.15*rng.standard_normal(n)*env(n,0.0005,0.004)
def clap():
    n=int(0.25*SR); x=rng.standard_normal(n); x=x-lp(x,0.3); e=np.zeros(n)
    for k,o in enumerate([0,0.008,0.016]): i=int(o*SR); e[i:]+=env(n-i,0.0005,0.012 if k<2 else 0.09)
    return x*e*0.5
def hat(o=False):
    n=int((0.12 if o else 0.04)*SR); x=rng.standard_normal(n); x=x-lp(x,0.6); return x*env(n,0.0005,0.05 if o else 0.012)*0.25
def note(f,dur,kind='saw',a=0.005,d=0.3):
    n=int(dur*SR); t=np.arange(n)/SR
    if kind=='sine': x=np.sin(2*np.pi*f*t)
    elif kind=='tri': x=2*np.abs(2*((f*t)%1)-1)-1
    else: x=sum(np.sin(2*np.pi*f*k*t)/k for k in range(1,9))*0.6
    return x*env(n,a,d)
midi=lambda m:440*2**((m-69)/12)
chords=[[57,60,64],[53,57,60],[48,52,55],[55,59,62]] # Am F C G
roots=[45,41,48,43]
for bar in range(10):
    ch=chords[bar%4]; rt=roots[bar%4]; b0=bar*2.0
    for k in range(4):
        tb=b0+k*BEAT; place(music,kick(),tb,0.9)
        d=np.ones(int(0.22*SR)); d=1-0.55*np.exp(-np.arange(len(d))/SR/0.07); i=int(tb*SR); duck[i:i+len(d)]=np.minimum(duck[i:i+len(d)],d[:max(0,min(len(d),N-i))])
        if k in (1,3): place(music,clap(),tb,0.7)
        place(music,hat(k%2==1),tb+0.25,0.8); place(music,hat(),tb+0.125,0.35); place(music,hat(),tb+0.375,0.35)
        for e in range(2): place(music,note(midi(rt-12),0.24,'tri',0.003,0.12),tb+e*0.25,0.55)
    # pluck arp 16ths
    seq=[0,1,2,1,2,0,1,2]
    for s in range(16):
        m=ch[seq[s%8]]+12; place(music,note(midi(m),0.2,'saw',0.002,0.07),b0+s*0.125,0.07)
    # pad
    for m in ch: place(music,note(midi(m),2.0,'tri',0.4,1.6),b0,0.05)
music*=duck
# ---- SFX ----
ST=[0.5,1.5,2,4,6,8,10,12,14,16,18]
def whoosh():
    n=int(0.28*SR); x=rng.standard_normal(n); t=np.arange(n)/SR; out=np.zeros(n); s=0
    for i in range(n): a=0.02+0.25*np.sin(np.pi*i/n); s+=a*(x[i]-s); out[i]=s
    return out*np.sin(np.pi*t/0.28)*0.9
def click():
    n=int(0.05*SR); t=np.arange(n)/SR; return (np.sin(2*np.pi*2400*t)*0.6+rng.standard_normal(n)*0.4)*env(n,0.0003,0.006)
def tick():
    n=int(0.025*SR); t=np.arange(n)/SR; return np.sin(2*np.pi*3200*t)*env(n,0.0002,0.004)
def thock():
    n=int(0.15*SR); t=np.arange(n)/SR; return np.sin(2*np.pi*(180+200*np.exp(-t/0.01))*t)*env(n,0.001,0.05)
def chime(fs):
    out=np.zeros(int(0.6*SR))
    for k,f in enumerate(fs): s=note(f,0.5,'sine',0.002,0.18); i=int(k*0.07*SR); out[i:i+len(s)]+=s[:len(out)-i]
    return out
events=[]
for t in ST: place(sfx,whoosh(),t-0.04,0.35); events.append(('morph',t))
for t in [0.5,8.5,9.0,9.5,10.5,11.0,11.5]: place(sfx,click(),t,0.8); events.append(('click',t))
place(sfx,click(),6.05,0.6); place(sfx,thock(),7.5,0.5)
for t in [8.5,9.0,9.5]: place(sfx,thock(),t+0.02,0.45)
place(sfx,chime([midi(76),midi(83)]),1.55,0.35)
for t in [12.5,13.0,13.5]: place(sfx,tick(),t,0.5)
place(sfx,thock(),15.5,0.7); place(sfx,chime([midi(72),midi(79),midi(84)]),16.0,0.35)
ticks=json.load(open(D+"/ticks.json"))
for tt in ticks: place(sfx,tick(),tt,0.22)
for i in range(5): place(sfx,tick(),14.5+i*0.11,0.3)
mix=music*0.55+sfx*0.9
mix/=np.max(np.abs(mix))*1.05
pcm=(mix*32767).astype(np.int16)
with wave.open(D+'/audio.wav','wb') as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
# verify beat grid by onset analysis of the music bed
fr=512; e=np.array([np.sum(music[i:i+fr]**2) for i in range(0,N-fr,fr)]); on=np.maximum(0,np.diff(e)); pk=[i for i in range(1,len(on)-1) if on[i]>on[i-1] and on[i]>=on[i+1] and on[i]>0.3*on.max()]
ts=np.array(pk)*fr/SR; print('detected onsets',len(ts),'median spacing',np.median(np.diff(ts)) if len(ts)>1 else None,'first',ts[:4])
