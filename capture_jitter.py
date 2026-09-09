#!/usr/bin/env python3
"""
AFDX 실측 지터 캡처/분석 (외부 수신 ΔTtx 방식).

  Ttx(n)   Ttx(n+1)          ΔTtx(n) = Ttx(n+1) - Ttx(n)      [PC 수신 타임스탬프]
    └──ΔTtx──┘               J(n)    = ΔTtx(n) - BAG          [프레임별 송출 지터]

보드(KFDX)가 VL 로 프레임을 반복 송신하는 동안 PC NIC 에서 캡처한다.
--send 1회는 tx_buf 한 버퍼분(~수십 프레임)만 내보내므로 --repeat 로 여러 번 쏜다.
버스트 사이의 큰 간격(> 1.5×BAG)은 경계로 보고 지터 통계에서 제외한다.

주의: USB NIC(r8152)는 SW 타임스탬프라 수백us 노이즈 → 측정 지터의 바닥이 NIC.
      정밀 측정은 HW 타임스탬프 NIC(i225/i226 등, `ethtool -T` 에 hardware-*) 사용.

사전 1회: sudo setcap cap_net_raw,cap_net_admin+eip /usr/bin/tcpdump
실행:
  python3 capture_jitter.py --dev enxc84d44263ba6 --bag 200 --repeat 12 --out run
"""
import argparse, asyncio, json, os, subprocess, time, random, statistics as st

async def _rpc(ws, cmd, t=10):
    i='c'+str(random.random()); await ws.send(json.dumps({"op":"cmd","c":cmd,"t":t,"id":i}))
    while True:
        m=await asyncio.wait_for(ws.recv(),timeout=t+5)
        if isinstance(m,str):
            d=json.loads(m)
            if d.get("op")=="cmdresult" and d["id"]==i: return d["out"]

async def board_seq(wsport, vlid, bag, length, count, repeat):
    import websockets
    async with websockets.connect(f"ws://localhost:{wsport}",max_size=None) as ws:
        phy=await _rpc(ws,"cd /mnt/flash && ./kfdx_app --status --phy 2>&1 | grep -E 'LINK|SPEED'")
        print("[board] PHY:", " ".join(phy.split()))
        await _rpc(ws,f"cd /mnt/flash && ./kfdx_app --set --vlid={vlid} --bag={bag} --dir=tx "
                     f"--type=queueing --min=64 --max=1518 --tx_buf_size=0x100000 >/dev/null 2>&1; echo ok")
        print(f"[board] send x{repeat}  vlid={vlid} len={length} count={count} (BAG {bag}x10us={bag*10}us)")
        for k in range(repeat):
            await _rpc(ws,f"cd /mnt/flash && ./kfdx_app --send --vlid={vlid} --udp --len={length} "
                         f"--count={count} >/dev/null 2>&1; echo s")

def analyze(pcap, bag_us, out):
    from scapy.all import rdpcap
    pk=rdpcap(pcap)
    afdx=sorted((float(p.time) for p in pk if bytes(p)[0:1]==b'\x03'))
    print(f"\n[analyze] AFDX 프레임 {len(afdx)} / 전체 {len(pk)}")
    if len(afdx)<5:
        print("  프레임 부족 — 배선/송신 확인"); return None
    d_all=[(afdx[i]-afdx[i-1])*1e6 for i in range(1,len(afdx))]
    # 버스트 경계(큰 간격) 제외 → 버스트 내 간격만 지터로
    d=[x for x in d_all if 0.3*bag_us < x < 1.7*bag_us]
    bounds=len(d_all)-len(d)
    J=[x-bag_us for x in d]
    res=dict(frames=len(afdx), used_intervals=len(d), bursts=bounds+1, bag_us=bag_us,
             dt_min=min(d), dt_max=max(d), dt_mean=st.mean(d), dt_median=st.median(d),
             j_min=min(J), j_max=max(J), j_mean=st.mean(J),
             j_abs_max=max(abs(x) for x in J), j_rms=(sum(x*x for x in J)/len(J))**.5,
             stdev=st.pstdev(d), p2p=max(d)-min(d))
    print(f"  버스트 {res['bursts']}개, 지터 유효표본 {res['used_intervals']} (경계 {bounds} 제외)")
    print(f"  ΔTtx us : min {res['dt_min']:.1f}  max {res['dt_max']:.1f}  mean {res['dt_mean']:.2f}  median {res['dt_median']:.2f}")
    print(f"  Jitter  : |J|max {res['j_abs_max']:.1f}  RMS {res['j_rms']:.1f}  P2P {res['p2p']:.1f}  stdev {res['stdev']:.1f} us")
    if out:
        json.dump({**res,"deltas_us":d}, open(out+".json","w"), indent=1)
        _plot(d, J, bag_us, res, out+".png")
        print(f"  saved {out}.json, {out}.png")
    return res

def _plot(d, J, bag_us, res, png):
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print("  (matplotlib 없음, 플롯 생략)"); return
    fig,ax=plt.subplots(1,2,figsize=(12,4.2))
    ax[0].plot(d, lw=.7, color="#3fb950")
    ax[0].axhline(bag_us, color="#f85149", ls="--", lw=1, label=f"BAG {bag_us:.0f}us")
    ax[0].set_title(f"AFDX ΔTtx  (mean {res['dt_mean']:.1f}us, P2P {res['p2p']:.1f}us)")
    ax[0].set_xlabel("frame #"); ax[0].set_ylabel("ΔTtx [us]"); ax[0].legend(fontsize=8)
    ax[1].hist(J, bins=40, color="#58a6ff")
    ax[1].axvline(0, color="#f85149", ls="--", lw=1)
    ax[1].set_title(f"Jitter J=ΔT-BAG  (|J|max {res['j_abs_max']:.1f}, RMS {res['j_rms']:.1f}us)")
    ax[1].set_xlabel("J [us]"); ax[1].set_ylabel("count")
    fig.tight_layout(); fig.savefig(png, dpi=110); plt.close(fig)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--dev", default="enxc84d44263ba6")
    ap.add_argument("--vlid", type=int, default=1)
    ap.add_argument("--bag", type=int, default=200, help="x10us (200=2ms)")
    ap.add_argument("--len", dest="length", type=int, default=17)
    ap.add_argument("--count", type=int, default=2000)
    ap.add_argument("--repeat", type=int, default=12)
    ap.add_argument("--wsport", default="8778")
    ap.add_argument("--out", default=None)
    ap.add_argument("--pcap", default="/tmp/afdx_cap.pcap")
    a=ap.parse_args()
    bag_us=a.bag*10.0
    dur=int(a.repeat*0.6+6)
    # tcpdump: setcap(cap_net_raw)로 sudo 없이. 사전 1회:
    #   sudo setcap cap_net_raw,cap_net_admin+eip /usr/bin/tcpdump
    try: os.path.exists(a.pcap) and os.remove(a.pcap)
    except OSError: pass
    tderr=open("/tmp/afdx_td.log","wb")
    cmd=["timeout",str(dur),"tcpdump","-i",a.dev,"-nn",
         "--time-stamp-precision=nano","-w",a.pcap]
    td=subprocess.Popen(cmd, stderr=tderr)
    time.sleep(2.0)
    try:
        asyncio.run(board_seq(a.wsport,a.vlid,a.bag,a.length,a.count,a.repeat))
    finally:
        td.wait()
    try:
        sz=os.path.getsize(a.pcap)
    except OSError: sz=-1
    print(f"[pcap] {a.pcap} size={sz}B"); print("[tcpdump]", open("/tmp/afdx_td.log").read().strip()[-300:])
    analyze(a.pcap, bag_us, a.out)

if __name__=="__main__":
    main()
