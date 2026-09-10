#!/usr/bin/env python3
"""
다중 VL 동시 송신(경쟁) 테스트 — 진짜 AFDX 시나리오.
여러 VL을 동시에 송신시켜 스케줄러 경쟁이 VL별 지터에 미치는 영향을 본다.
프레임은 dst MAC 마지막바이트(=VLID)로 VL 구분.
  sudo ./measure_setup.sh 먼저. 그다음:
  python3 multi_vl_test.py --vls 1,2,3 --bag 200 --dev enp4s0 --repeat 6
"""
import argparse, asyncio, json, os, subprocess, sys, time, random, statistics as st
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from capture_jitter import detect_anomalies

async def _rpc(ws, cmd, t=10):
    i='c'+str(random.random()); await ws.send(json.dumps({"op":"cmd","c":cmd,"t":t,"id":i}))
    while True:
        m=await asyncio.wait_for(ws.recv(),timeout=t+5)
        if isinstance(m,str):
            d=json.loads(m)
            if d.get("op")=="cmdresult" and d["id"]==i: return d["out"]

async def board(wsport, vls, bag, length, count, repeat):
    import websockets
    async with websockets.connect(f"ws://localhost:{wsport}",max_size=None) as ws:
        K="cd /mnt/flash && ./kfdx_app"
        for v in vls:
            await _rpc(ws,f"{K} --del --vlid={v} >/dev/null 2>&1; {K} --add --vlid={v} --bag={bag} "
                         f"--dir=tx --type=queueing --min=64 --max=1518 --tx_buf_size=0x100000 >/dev/null 2>&1; echo x")
        print(f"[board] VL {vls} 생성 (BAG {bag}x10us)")
        for _ in range(repeat):
            for v in vls:
                await _rpc(ws,f"{K} --send --vlid={v} --udp --len={length} --count={count} >/dev/null 2>&1; echo s")
        print(f"[board] {len(vls)}VL 교차 송신 {repeat}라운드")

def per_vl(pcap, vls, bag_us):
    from scapy.all import rdpcap
    pk=rdpcap(pcap)
    byvl={v:[] for v in vls}
    for p in pk:
        b=bytes(p)
        if b[0:1]==b'\x03':
            vid=b[5]
            if vid in byvl: byvl[vid].append((float(p.time), b[-1], len(b)))
    out={}
    for v,frames in byvl.items():
        ts=sorted(t for t,_,_ in frames)
        if len(ts)<5: out[v]=None; continue
        d=[(ts[i]-ts[i-1])*1e6 for i in range(1,len(ts))]
        d=[x for x in d if 0.3*bag_us<x<1.7*bag_us]
        if not d: out[v]=None; continue
        med=st.median(d); mad=sorted(abs(x-med) for x in d)[len(d)//2]
        an=detect_anomalies(frames, bag_us, 1.4826*mad, mad)
        out[v]=dict(n=len(frames), used=len(d), dt_mean=st.mean(d),
                    rob_std=1.4826*mad, rms=(sum((x-bag_us)**2 for x in d)/len(d))**.5,
                    **{k:an[k] for k in ('verdict','seq_loss','lmax_violation','rate_violation')})
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--vls", default="1,2,3")
    ap.add_argument("--bag", type=int, default=200)
    ap.add_argument("--dev", default="enp4s0")
    ap.add_argument("--len", dest="length", type=int, default=17)
    ap.add_argument("--count", type=int, default=2000)
    ap.add_argument("--repeat", type=int, default=6)
    ap.add_argument("--wsport", default="8778")
    ap.add_argument("--pcap", default="/tmp/afdx_mvl.pcap")
    a=ap.parse_args()
    vls=[int(x) for x in a.vls.split(",")]; bag_us=a.bag*10.0
    dur=int(a.repeat*len(vls)*0.6+6)
    try: os.path.exists(a.pcap) and os.remove(a.pcap)
    except OSError: pass
    td=subprocess.Popen(["taskset","-c","9","timeout",str(dur),"tcpdump","-i",a.dev,"-nn",
                         "--time-stamp-precision=nano","-w",a.pcap], stderr=subprocess.DEVNULL)
    time.sleep(2.0)
    try: asyncio.run(board(a.wsport, vls, a.bag, a.length, a.count, a.repeat))
    finally: td.wait()
    res=per_vl(a.pcap, vls, bag_us)
    print(f"\n=== 다중 VL 경쟁 결과 (BAG {a.bag}x10us={bag_us:.0f}us, {len(vls)}VL 동시) ===")
    print(f"{'VL':>3} {'프레임':>6} {'표본':>5} {'평균ΔT':>9} {'지터MAD':>8} {'RMS':>7} {'판정':>8} {'손실/Lmax':>9}")
    for v in vls:
        r=res.get(v)
        if r: print(f"{v:>3} {r['n']:>6} {r['used']:>5} {r['dt_mean']:>8.1f}u {r['rob_std']:>7.2f}u {r['rms']:>6.1f}u {r['verdict']:>8} {r['seq_loss']}/{r['lmax_violation']:>7}")
        else: print(f"{v:>3}  (프레임 부족)")
    ok=[res[v]['rob_std'] for v in vls if res.get(v)]
    if ok: print(f"\nVL별 지터 MAD-std: min {min(ok):.2f} max {max(ok):.2f} us  (단일 VL 대비 경쟁으로 증가 여부 확인)")
    json.dump({str(v):res.get(v) for v in vls}, open("results/multi_vl.json","w"), indent=1)
    print("saved results/multi_vl.json")

if __name__=="__main__": main()
