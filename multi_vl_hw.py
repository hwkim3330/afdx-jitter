#!/usr/bin/env python3
"""다중 VL 경쟁 하 timing isolation 실험 — HW 타임스탬프 (연구축 C).

질문: 단일 VL에서 확인한 결정론적 240 ns 페이싱이, 여러 VL이 동시에 MAC을 두고
경쟁할 때도 유지되나? 아니면 멀티플렉싱 지터가 더해지나?

방법: N개 VL(1..N)을 같은 BAG로 TX 설정 → 모두 동시 송신 → NIC HW 타임스탬프로
전 VL 캡처(필터 ALL) → VLID(dst[5])로 분리 → VL별 지터(mean/MAD-std/P2P) 계산.
N=1,2,4,8 스위프로 지터 증가를 정량화.

안전: 설정한 VL만 --add/--del/--send. **미설정 VL --get 금지(B16 커널 hang)**,
--link_down 금지. VL1은 삭제하지 않고 BAG만 원복.

사용(보드 살아있을 때): python3 multi_vl_hw.py --nvls 1,2,4,8 --bag 100 --len 1400
"""
import argparse, json, time, asyncio, random, subprocess, sys, statistics as st
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import websockets
HERE=__import__('os').path.dirname(__import__('os').path.abspath(__file__))

async def _rpc(ws,c,t):
    i=str(random.random()); await ws.send(json.dumps({'op':'cmd','c':c,'t':t,'id':i}))
    while True:
        m=await asyncio.wait_for(ws.recv(),timeout=t+5)
        if isinstance(m,str):
            d=json.loads(m)
            if d.get('id')==i: return d.get('out','')

async def _cmd(cmd,t=6):
    async with websockets.connect('ws://localhost:8778',max_size=None) as ws:
        return await _rpc(ws,f'cd /mnt/flash && ./kfdx_app {cmd} 2>&1 | tail -2',t)

async def _send_all(deadline, vls, length):
    async with websockets.connect('ws://localhost:8778',max_size=None) as ws:
        while time.time()<deadline:
            for v in vls:
                if time.time()>=deadline: break
                await _rpc(ws,f'cd /mnt/flash && ./kfdx_app --send --vlid={v} --udp --len={length} --count=3000 >/dev/null 2>&1;echo s',9)

def add_vls(vls, bag, lmax=1518):
    for v in vls:
        asyncio.run(_cmd(f'--add --vlid={v} --bag={bag} --dir=tx --type=queueing --min=64 --max={lmax}'))

def restore(added):
    for v in added:
        if v!=1: asyncio.run(_cmd(f'--del --vlid={v}'))
    asyncio.run(_cmd('--set --vlid=1 --bag=200 --dir=tx'))  # VL1 원복

def capture_all(iface, dur, pw="1"):
    dump=f"{HERE}/results/mvl_frames.json"
    p=subprocess.Popen(['sudo','-S','python3',f'{HERE}/hwts_jitter.py','--iface',iface,
                        '--dur',str(dur),'--dump-vl',dump],
                       stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,text=True)
    try: p.stdin.write(pw+"\n"); p.stdin.flush()
    except Exception: pass
    return p, dump

def per_vl_metrics(frames, bag_us):
    """frames: [(hw,vlid,sn,len)] → {vlid: metrics}."""
    by={}
    for hw,vlid,sn,L in frames:
        if hw>0: by.setdefault(vlid,[]).append(hw)
    out={}
    for vlid,ts in by.items():
        ts=sorted(ts)
        if len(ts)<10: continue
        d=[(ts[i]-ts[i-1])*1e6 for i in range(1,len(ts))]
        inb=[x for x in d if 0.5*bag_us<x<1.5*bag_us]
        if len(inb)<10: continue
        mean=st.mean(inb); med=st.median(inb)
        mad=sorted(abs(x-med) for x in inb)[len(inb)//2]
        out[vlid]=dict(n=len(inb), mean_us=round(mean,3),
                       ppm=round((mean-bag_us)/bag_us*1e6,2),
                       mad_std_ns=round(1.4826*mad*1000,1),
                       p2p_ns=round((max(inb)-min(inb))*1000,1))
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--nvls",default="1,2,4,8")
    ap.add_argument("--bag",type=int,default=100, help="×10µs (각 VL 동일)")
    ap.add_argument("--len",type=int,default=1400, help="프레임 길이(큰 값=직렬화 길어 경쟁 유발)")
    ap.add_argument("--iface",default="enp4s0")
    ap.add_argument("--dur",type=float,default=12)
    a=ap.parse_args()
    counts=[int(x) for x in a.nvls.split(",")]
    bag_us=a.bag*10
    results=[]
    try:
        for N in counts:
            vls=list(range(1,N+1))
            print(f"\n=== {N} VL 경쟁 (BAG {bag_us}µs, len {a.len}) ===", flush=True)
            add_vls(vls, a.bag, max(1518,a.len+64))
            p,dump=capture_all(a.iface,a.dur)
            time.sleep(1.2)
            asyncio.run(_send_all(time.time()+a.dur-1.5, vls, a.len))
            p.wait()
            frames=json.load(open(dump))
            m=per_vl_metrics(frames, bag_us)
            # 경쟁 지표: 모든 VL 프레임의 최소 인접간격(직렬화 충돌)
            allhw=sorted(f[0] for f in frames if f[0]>0)
            gaps=[(allhw[i]-allhw[i-1])*1e6 for i in range(1,len(allhw))] if len(allhw)>1 else []
            min_gap=min(gaps) if gaps else 0
            row=dict(N=N, bag_us=bag_us, len=a.len, per_vl=m,
                     max_p2p_ns=max((v['p2p_ns'] for v in m.values()), default=0),
                     mean_p2p_ns=round(st.mean([v['p2p_ns'] for v in m.values()]),1) if m else 0,
                     min_intergap_us=round(min_gap,3), total_frames=len(allhw))
            results.append(row)
            for vlid in sorted(m):
                v=m[vlid]; print(f"  VL{vlid}: mean {v['mean_us']}µs  MAD-std {v['mad_std_ns']}ns  P2P {v['p2p_ns']}ns  ppm {v['ppm']:+}  n={v['n']}")
            print(f"  → VL별 최대 P2P {row['max_p2p_ns']}ns (단일=238ns 기준), 최소 프레임간격 {row['min_intergap_us']}µs", flush=True)
    finally:
        print("\n복원(추가 VL 삭제, VL1 BAG=200)…")
        restore(list(range(1,max(counts)+1)))
    json.dump(results, open(f"{HERE}/results/multi_vl.json","w"), ensure_ascii=False, indent=1)
    print("saved results/multi_vl.json")
    print("\n해석: VL별 mean이 BAG를 유지하면 페이싱 격리 OK. P2P가 238ns→↑ 증가분 = 멀티플렉싱 지터")
    print("(다른 VL 프레임 직렬화가 릴리스를 밀어낸 양). min 프레임간격이 프레임직렬화(~%dns)에 근접하면 포화."%(int((a.len+26)*8)))

if __name__=="__main__": main()
