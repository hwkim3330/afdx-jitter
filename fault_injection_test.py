#!/usr/bin/env python3
"""
AFDX 이상 검출 검증 — 안전한 고장 주입 스위트 (정상→주입→검출→복구).
⚠ 안전: kfdx_app 정상 명령(--add/--set/--send)과 pcap 조작만 사용.
   레지스터 write, --link_down 등 위험 명령 절대 미사용.

시나리오:
  S0 정상            → NORMAL 기대
  S1 Lmax 초과       → FAULT(Lmax) 기대  (큰 프레임 + 낮은 Lmax 정책)
  S2 Rate 위반       → FAULT/WARNING(Rate) 기대  (VL을 BAG정책보다 빠르게 송신)
  S3 시퀀스 손실     → FAULT(손실) 기대  (정상 캡처에서 프레임 삭제 = drop 재현)
  S4 잘못된 VLID     → 검출 기대  (허용집합 밖 VLID 송신)
  S5 복구(정상)      → NORMAL 기대

사전: sudo ./measure_setup.sh enp4s0 8 (선택). 그다음:
  python3 fault_injection_test.py --dev enp4s0
"""
import argparse, asyncio, json, os, subprocess, sys, time, random, statistics as st
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from capture_jitter import detect_anomalies

async def rpc(ws, cmd, t=10):
    i='c'+str(random.random()); await ws.send(json.dumps({"op":"cmd","c":cmd,"t":t,"id":i}))
    while True:
        m=await asyncio.wait_for(ws.recv(),timeout=t+5)
        if isinstance(m,str):
            d=json.loads(m)
            if d.get("op")=="cmdresult" and d["id"]==i: return d["out"]

K="cd /mnt/flash && ./kfdx_app"

def capture(dev, dur, pcap):
    try: os.path.exists(pcap) and os.remove(pcap)
    except OSError: pass
    return subprocess.Popen(["taskset","-c","9","timeout",str(dur),"tcpdump","-i",dev,"-nn",
                             "--time-stamp-precision=nano","-w",pcap], stderr=subprocess.DEVNULL)

def load_frames(pcap, vlid=None):
    from scapy.all import rdpcap
    fr=[]
    for p in rdpcap(pcap):
        b=bytes(p)
        if b[0:1]==b'\x03' and (vlid is None or b[5]==vlid):
            fr.append((float(p.time), b[-1], len(b), b[5]))
    return fr

async def sc_send(wsport, setup_cmds, send_cmds):
    import websockets
    async with websockets.connect(f"ws://localhost:{wsport}",max_size=None) as ws:
        for c in setup_cmds: await rpc(ws, c)
        for c in send_cmds: await rpc(ws, c)

def analyze(frames, bag_us, lmax):
    if len(frames)<8: return None
    f3=[(t,sn,L) for t,sn,L,_ in frames]
    ts=sorted(t for t,_,_ in f3)
    d=[(ts[i]-ts[i-1])*1e6 for i in range(1,len(ts))]
    d=[x for x in d if 0.3*bag_us<x<1.7*bag_us]
    med=st.median(d) if d else 0
    mad=sorted(abs(x-med) for x in d)[len(d)//2] if d else 0
    return detect_anomalies(f3, bag_us, 1.4826*mad, mad, lmax)

def run_scenario(name, dev, wsport, setup, send, dur, bag_us, lmax, allowed_vls, expect, pcap,
                 drop=0, reuse=None):
    print(f"\n── {name} ──")
    if reuse:                      # S3: 기존 캡처 재사용 + 프레임 삭제
        frames=reuse[:]
    else:
        td=capture(dev,dur,pcap); time.sleep(2.0)
        asyncio.run(sc_send(wsport,setup,send))
        td.wait(); frames=load_frames(pcap)
    # 잘못된 VLID 검출 (허용집합 밖)
    vlids=set(v for _,_,_,v in frames)
    bad_vl=sorted(vlids-set(allowed_vls))
    # 시퀀스 손실 주입 (drop개 프레임 중간에서 삭제)
    if drop and len(frames)>drop+20:
        i=len(frames)//2
        frames=frames[:i]+frames[i+drop:]
    tv=[f for f in frames if f[3]==(allowed_vls[0])]   # 대상 VL만 표준분석
    an=analyze(tv, bag_us, lmax)
    if an is None and not bad_vl:
        print("  프레임 부족"); return (name, False)
    verdict = an['verdict'] if an else 'NORMAL'
    if bad_vl: verdict='FAULT'   # 허용외 VLID = FAULT
    info=f"판정 {verdict}"
    if an: info+=f" · 손실 {an['seq_loss']} 중복 {an['seq_dup']} Rate {an['rate_violation']} Lmax {an['lmax_violation']}"
    if bad_vl: info+=f" · ★허용외 VLID {bad_vl}"
    # 판정
    ok = (expect=='NORMAL' and verdict=='NORMAL') or \
         (expect=='FAULT' and verdict in ('FAULT','WARNING')) or \
         (expect=='WARNING' and verdict in ('WARNING','FAULT'))
    # 세부 원인까지 확인
    cause_ok=True
    if an:
        if name.startswith('S1') and an['lmax_violation']==0: cause_ok=False
        if name.startswith('S2') and an['rate_violation']==0: cause_ok=False
        if name.startswith('S3') and an['seq_loss']==0: cause_ok=False
    if name.startswith('S4') and not bad_vl: cause_ok=False
    result = ok and cause_ok
    print(f"  {info}")
    print(f"  기대 [{expect}] → {'✅ PASS' if result else '❌ FAIL'}")
    return (name, result, frames)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--dev", default="enp4s0"); ap.add_argument("--wsport", default="8778")
    a=ap.parse_args(); pc="/tmp/afdx_fi.pcap"; SET=f"{K} --del --vlid=1 >/dev/null 2>&1; {K} --del --vlid=2 >/dev/null 2>&1"
    def vl(v,bag,mx=1518): return f"{K} --add --vlid={v} --bag={bag} --dir=tx --type=queueing --min=64 --max=1518 --tx_buf_size=0x100000 >/dev/null 2>&1; echo x"
    def snd(v,ln,cnt=2000,rounds=8): return [f"{K} --send --vlid={v} --udp --len={ln} --count={cnt} >/dev/null 2>&1;echo s" for _ in range(rounds)]
    results=[]; normal_cap=None
    # S0 정상
    r=run_scenario("S0 정상", a.dev,a.wsport,[SET,vl(1,200)],snd(1,17),12,2000,1518,[1],'NORMAL',pc); results.append(r[:2])
    if len(r)>2: normal_cap=r[2]
    # S1 Lmax 초과 (1514B 프레임, 정책 Lmax=512)
    results.append(run_scenario("S1 Lmax초과", a.dev,a.wsport,[SET,vl(1,200)],snd(1,1471),12,2000,512,[1],'FAULT',pc)[:2])
    # S2 Rate 위반 (VL을 bag=50=500us로 송신, 정책 BAG=2000us)
    results.append(run_scenario("S2 Rate위반", a.dev,a.wsport,[SET,vl(1,50)],snd(1,17,3000,6),12,2000,1518,[1],'FAULT',pc)[:2])
    # S3 시퀀스 손실 (S0 정상캡처에서 프레임 8개 삭제 = drop 재현)
    if normal_cap:
        results.append(run_scenario("S3 시퀀스손실", a.dev,a.wsport,None,None,0,2000,1518,[1],'FAULT',pc,drop=8,reuse=normal_cap)[:2])
    # S4 잘못된 VLID (허용={1}인데 VL2 송신)
    s4=[SET,vl(1,200),vl(2,200)]
    results.append(run_scenario("S4 잘못된VLID", a.dev,a.wsport,s4,snd(1,17,2000,4)+snd(2,17,2000,4),12,2000,1518,[1],'FAULT',pc)[:2])
    # S5 복구
    results.append(run_scenario("S5 복구", a.dev,a.wsport,[SET,vl(1,200)],snd(1,17),12,2000,1518,[1],'NORMAL',pc)[:2])
    print("\n=== 고장주입 검증 요약 ===")
    npass=sum(1 for _,ok in results if ok)
    for name,ok in results: print(f"  {'✅' if ok else '❌'} {name}")
    print(f"  {npass}/{len(results)} PASS")
    json.dump([{"scenario":n,"pass":bool(ok)} for n,ok in results], open("results/fault_injection.json","w"), indent=1)
    print("saved results/fault_injection.json")

if __name__=="__main__": main()
