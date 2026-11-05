import numpy as np, sys, wave
D=sys.argv[1]; SR=44100; T=15.0; N=int(SR*T); BEAT=0.5
rng=np.random.default_rng(11)
def env(n,a=0.002,d=0.2): t=np.arange(n)/SR; return np.minimum(1,t/a)*np.exp(-t/d)
def place(buf,sig,t,g=1.0):
    i=int(round(t*SR))
    if i<0 or i>=N: return
    j=min(N,i+len(sig)); buf[i:j]+=sig[:j-i]*g
def hp(x,a):
    y=np.empty_like(x); s=0.0
    for i in range(len(x)): s+=a*(x[i]-s); y[i]=x[i]-s
    return y
midi=lambda m:440*2**((m-69)/12)
def note(f,dur,kind='saw',a=0.005,d=0.3):
    n=int(dur*SR); t=np.arange(n)/SR
    x=np.sin(2*np.pi*f*t) if kind=='sine' else (2*np.abs(2*((f*t)%1)-1)-1 if kind=='tri' else sum(np.sin(2*np.pi*f*k*t)/k for k in range(1,9))*0.6)
    return x*env(n,a,d)
def kick():
    n=int(0.35*SR); t=np.arange(n)/SR; f=45+80*np.exp(-t/0.035); return np.sin(2*np.pi*np.cumsum(f)/SR)*env(n,0.001,0.17)
def clap():
    n=int(0.25*SR); x=hp(rng.standard_normal(n),0.3); e=np.zeros(n)
    for k,o in enumerate([0,0.008,0.016]): i=int(o*SR); e[i:]+=env(n-i,0.0005,0.012 if k<2 else 0.09)
    return x*e*0.5
def hat(o=False): n=int((0.12 if o else 0.04)*SR); return hp(rng.standard_normal(n),0.6)*env(n,0.0005,0.05 if o else 0.012)*0.25
music=np.zeros(N); duck=np.ones(N)
chords=[[57,60,64],[53,57,60],[48,52,55],[55,59,62]]; roots=[45,41,48,43]
for bar in range(8):
    b0=bar*2.0; ch=chords[bar%4]; rt=roots[bar%4]
    for k in range(4):
        tb=b0+k*BEAT
        if tb>=T: break
        if not (bar==0 and k<2):  # intro: first two beats sparse
            place(music,kick(),tb,0.9); d=1-0.55*np.exp(-np.arange(int(0.22*SR))/SR/0.07); i=int(tb*SR); m=min(len(d),N-i); duck[i:i+m]=np.minimum(duck[i:i+m],d[:m])
        if k in (1,3): place(music,clap(),tb,0.7)
        place(music,hat(k%2==1),tb+0.25,0.8); place(music,hat(),tb+0.125,0.35); place(music,hat(),tb+0.375,0.35)
        for e in range(2): place(music,note(midi(rt-12),0.24,'tri',0.003,0.12),tb+e*0.25,0.55)
    seq=[0,1,2,1,2,0,1,2]
    for s_ in range(16): place(music,note(midi(ch[seq[s_%8]]+12),0.2,'saw',0.002,0.07),b0+s_*0.125,0.07)
    for m_ in ch: place(music,note(midi(m_),2.0,'tri',0.4,1.6),b0,0.05)
music*=duck
# outro: drop drums after 14.5 -> let pad ring
sfx=np.zeros(N)
def whoosh(L=0.3):
    n=int(L*SR); x=rng.standard_normal(n); out=np.zeros(n); s=0
    for i in range(n): a=0.02+0.25*np.sin(np.pi*i/n); s+=a*(x[i]-s); out[i]=s
    return out*np.sin(np.pi*np.arange(n)/n)*0.9
def click(): n=int(0.05*SR); t=np.arange(n)/SR; return (np.sin(2*np.pi*2400*t)*0.6+rng.standard_normal(n)*0.4)*env(n,0.0003,0.006)
def tick(): n=int(0.025*SR); t=np.arange(n)/SR; return np.sin(2*np.pi*3200*t)*env(n,0.0002,0.004)
def thock(): n=int(0.15*SR); t=np.arange(n)/SR; return np.sin(2*np.pi*(180+200*np.exp(-t/0.01))*t)*env(n,0.001,0.05)
def chime(fs):
    out=np.zeros(int(0.6*SR))
    for k,f in enumerate(fs): s_=note(f,0.5,'sine',0.002,0.18); i=int(k*0.07*SR); out[i:i+len(s_)]+=s_[:len(out)-i]
    return out
def blip(): return note(midi(84),0.12,'sine',0.001,0.04)
for t in [0.5,4.0,5.0,10.5,12.0,14.0]: place(sfx,whoosh(0.26),t-0.05,0.35)
place(sfx,click(),0.5,0.8)
caps=[(0.5,'한 줄로\n지시하고'),(4.0,'AI가 직접\n사이트 클릭'),(10.5,'나는 결과만\n확인'),(12.0,"댓글에 '체험단'\n지시문 DM"),(13.5,'체험단 신청,\nAI가 대신 함')]
for t0,s_ in caps:
    for i,ch in enumerate(s_):
        if ch not in ' \n': place(sfx,tick(),t0+i*0.045,0.2)
msg='무신사·카카오 체험단, 모집 중인 것만 신청해줘'
for i,ch in enumerate(msg):
    if ch!=' ': place(sfx,tick(),0.75+i*0.07,0.16)
place(sfx,click(),3.0,0.8); place(sfx,thock(),3.02,0.45)
place(sfx,click(),3.5,0.8); place(sfx,thock(),3.52,0.6)
ACT=[[5.5,1],[6.0,0],[6.5,1],[7.0,0],[9.0,1],[9.5,0],[10.0,1]]
for t,a in ACT:
    place(sfx,click(),t-0.02,0.7)
    if a: place(sfx,blip(),t+0.05,0.35)
place(sfx,click(),7.5,0.6); place(sfx,thock(),8.0,0.4); place(sfx,click(),8.5,0.7); place(sfx,whoosh(0.2),8.48,0.25)
for k in range(4): place(sfx,tick(),10.75+k*0.25,0.4)
place(sfx,chime([midi(72),midi(79),midi(84)]),11.5,0.4)
place(sfx,chime([midi(76),midi(83)]),12.05,0.3)
mix=music*0.55+sfx*0.9
mix/=np.max(np.abs(mix))*1.05
with wave.open(D+'/audio.wav','wb') as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((mix*32767).astype(np.int16).tobytes())
print('ok')
