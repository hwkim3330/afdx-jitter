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
        await _rpc(ws,f"cd /mnt/flash && ./kfdx_app --del --vlid={vlid} >/dev/null 2>&1; echo x")
        await _rpc(ws,f"cd /mnt/flash && ./kfdx_app --add --vlid={vlid} --bag={bag} --dir=tx "
                     f"--type=queueing --min=64 --max=1518 --tx_buf_size=0x100000 >/dev/null 2>&1; echo ok")
        print(f"[board] send x{repeat}  vlid={vlid} len={length} count={count} (BAG {bag}x10us={bag*10}us)")
        for k in range(repeat):
            await _rpc(ws,f"cd /mnt/flash && ./kfdx_app --send --vlid={vlid} --udp --len={length} "
                         f"--count={count} >/dev/null 2>&1; echo s")

def detect_anomalies(frames, bag_us, rob_std, mad, lmax=1518):
    """AFDX 이상 검출: 시퀀스 손실/중복/재정렬, Rate/Lmax 위반, 간격 이상치, VL 판정."""
    seq_loss=seq_dup=seq_reorder=rate_v=lmax_v=outliers=0
    # 시각순 정렬 (시각, sn, len)
    fs=sorted(frames, key=lambda x:x[0])
    lensmax=max((L for _,_,L in fs), default=0)
    lmax_v=sum(1 for _,_,L in fs if L>lmax)
    med_std=rob_std or 1e9
    prev_t=prev_sn=prev_dt=None
    for t,sn,L in fs:
        if prev_t is not None:
            dt=(t-prev_t)*1e6
            same_burst = dt < 1.3*bag_us            # 같은 버스트(연속 송출)일 때만 판정
            if same_burst:
                # 시퀀스(ARINC664: 1~255 순환, 0 예약/건너뜀)
                if sn==prev_sn: seq_dup+=1
                else:
                    fwd=(sn-prev_sn) if sn>prev_sn else (255-prev_sn+sn)  # 0 건너뛴 순환거리
                    if fwd>64: seq_reorder+=1          # 큰 감소/점프 = 재정렬(또는 경계)
                    elif fwd>1: seq_loss+=fwd-1        # 갭 = 손실
                # Rate 위반: 짧은 간격 + 이웃과 합이 ~2×BAG 아님(=쪼개짐 노이즈 제외, 진짜 빠름만)
                if dt < 0.7*bag_us and prev_dt is not None and (dt+prev_dt) < 1.5*bag_us: rate_v+=1
                # 간격 이상치: |J-0| > 6*robust_std
                if abs(dt-bag_us) > max(6*med_std, 20): outliers+=1
        prev_dt = ((t-prev_t)*1e6) if prev_t is not None else None
        prev_t, prev_sn = t, sn
    # 판정
    if seq_loss or seq_dup or seq_reorder or lmax_v: verdict="FAULT"      # 프레임레벨(타임스탬프무관, 신뢰)
    elif rate_v:                                     verdict="WARNING"     # Rate위반(측정기반)
    else:                                            verdict="NORMAL"
    # (outliers=간격이상치는 PC 측정노이즈 포함 → 판정에 미반영, 참고용)
    return dict(verdict=verdict, seq_loss=seq_loss, seq_dup=seq_dup, seq_reorder=seq_reorder,
                rate_violation=rate_v, lmax_violation=lmax_v, outliers=outliers, frame_len_max=lensmax)

def analyze(pcap, bag_us, out, lmax=1518, vlid=None):
    from scapy.all import rdpcap
    pk=rdpcap(pcap)
    # 프레임별 (시각, SN=마지막바이트, 길이) — 캡처순
    frames=[]
    for p in pk:
        b=bytes(p)
        if b[0:1]==b'\x03' and (vlid is None or b[5]==vlid):
            frames.append((float(p.time), b[-1], len(b)))
    afdx=sorted(t for t,_,_ in frames)
    print(f"\n[analyze] AFDX 프레임 {len(afdx)} / 전체 {len(pk)}")
    if len(afdx)<5:
        print("  프레임 부족 — 배선/송신 확인"); return None
    d_all=[(afdx[i]-afdx[i-1])*1e6 for i in range(1,len(afdx))]
    # 버스트 경계(큰 간격) 제외 → 버스트 내 간격만 지터로
    d=[x for x in d_all if 0.3*bag_us < x < 1.7*bag_us]
    bounds=len(d_all)-len(d)
    J=[x-bag_us for x in d]
    # robust: 중앙값 기준 편차, MAD, 트림. 배경노이즈 스파이크(측정계) 제거해 FPGA 고유지터 추정
    med=st.median(d)
    absdev=sorted(abs(x-med) for x in d)
    mad=absdev[len(absdev)//2]
    rob_std=1.4826*mad                          # MAD 기반 표준편차(정규 등가)
    p=lambda q: sorted(absdev)[min(len(absdev)-1,int(q*len(absdev)))]
    dd=sorted(d); k=max(1,len(dd)//20)          # 상하 5% 트림
    trim=dd[k:-k] if len(dd)>2*k else dd
    trim_rms=(sum((x-bag_us)**2 for x in trim)/len(trim))**.5
    res=dict(frames=len(afdx), used_intervals=len(d), bursts=bounds+1, bag_us=bag_us,
             dt_min=min(d), dt_max=max(d), dt_mean=st.mean(d), dt_median=med,
             j_min=min(J), j_max=max(J), j_mean=st.mean(J),
             j_abs_max=max(abs(x) for x in J), j_rms=(sum(x*x for x in J)/len(J))**.5,
             stdev=st.pstdev(d), p2p=max(d)-min(d),
             rob_std=rob_std, mad=mad, trim_rms=trim_rms,
             j_p95=p(0.95), j_p99=p(0.99))
    res.update(detect_anomalies(frames, bag_us, res.get('rob_std',0), res.get('mad',0), lmax))
    print(f"  버스트 {res['bursts']}개, 지터 유효표본 {res['used_intervals']} (경계 {bounds} 제외)")
    print(f"  ΔTtx us : min {res['dt_min']:.1f}  max {res['dt_max']:.1f}  mean {res['dt_mean']:.2f}  median {res['dt_median']:.2f}")
    print(f"  Jitter  : |J|max {res['j_abs_max']:.1f}  RMS {res['j_rms']:.1f}  P2P {res['p2p']:.1f} us  (전체)")
    print(f"  Robust  : MAD-std {res['rob_std']:.2f}  trimRMS {res['trim_rms']:.2f}  p95 {res['j_p95']:.1f}  p99 {res['j_p99']:.1f} us  ← FPGA 고유지터")
    a=res
    print(f"  이상검출: 판정 [{a['verdict']}]  손실 {a['seq_loss']}  중복 {a['seq_dup']}  재정렬 {a['seq_reorder']}"
          f"  Rate위반 {a['rate_violation']}  Lmax위반 {a['lmax_violation']}  간격이상치 {a['outliers']}")
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
    ap.add_argument("--lmax", type=int, default=1518, help="Lmax(바이트) 초과시 위반")
    ap.add_argument("--hwts", action="store_true", help="NIC 하드웨어 타임스탬프(-j adapter_unsynced); i225/226 등")
    a=ap.parse_args()
    bag_us=a.bag*10.0
    dur=int(a.repeat*0.6+6)
    # tcpdump: setcap(cap_net_raw)로 sudo 없이. 사전 1회:
    #   sudo setcap cap_net_raw,cap_net_admin+eip /usr/bin/tcpdump
    try: os.path.exists(a.pcap) and os.remove(a.pcap)
    except OSError: pass
    tderr=open("/tmp/afdx_td.log","wb")
    cmd=["taskset","-c","9","timeout",str(dur),"tcpdump","-i",a.dev,"-nn",
         "--time-stamp-precision=nano"]
    if a.hwts: cmd+=["-j","adapter_unsynced"]   # NIC PHC 원시 타임스탬프(간격측정엔 OK)
    cmd+=["-w",a.pcap]
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
    analyze(a.pcap, bag_us, a.out, a.lmax, a.vlid)

if __name__=="__main__":
    main()
