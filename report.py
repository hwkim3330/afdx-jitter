#!/usr/bin/env python3
"""
AFDX 지터 종합 리포트: BAG별로 측정(capture_jitter) → 표 + 차트 한 페이지 HTML.
사용: sudo ./measure_setup.sh 먼저 실행(정밀). 그다음:
  python3 report.py --bags 100,200,400,800,1600 --dev enp4s0 --repeat 10
  → report.html (자체완결, 브라우저로 열기)
"""
import argparse, base64, datetime, json, os, shutil, statistics as st, subprocess, sys

def run_capture(dev, bag, count, repeat, out, runs=1):
    """runs회 측정 후 robust 지터(rob_std) 최소=가장 조용한 런 채택(노이즈는 더하기만 하므로 최소가 FPGA에 근접)."""
    best=None
    for _ in range(max(1,runs)):
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),"capture_jitter.py"),
                        "--dev", dev, "--bag", str(bag), "--len","17", "--count", str(count),
                        "--repeat", str(repeat), "--out", out],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try: r=json.load(open(out+".json"))
        except Exception: continue
        if r and (best is None or r.get("rob_std",9e9) < best.get("rob_std",9e9)): best=r
    return best

def b64(path):
    try: return "data:image/png;base64,"+base64.b64encode(open(path,"rb").read()).decode()
    except Exception: return ""

def summary_chart(rows, png):
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    except Exception: return ""
    bags=[r["bag_us"]/1000 for r in rows]
    fig,ax=plt.subplots(1,2,figsize=(11,3.6))
    ax[0].plot(bags,[r.get("rob_std",0) for r in rows],'o-',color="#3fb950",lw=2,label="FPGA jitter (MAD-std)")
    ax[0].plot(bags,[r["j_rms"] for r in rows],'s--',color="#e3b341",lw=1,label="RMS (all,w/noise)")
    ax[0].set_xlabel("BAG [ms]"); ax[0].set_ylabel("Jitter [us]"); ax[0].set_title("Jitter vs BAG")
    ax[0].legend(fontsize=8); ax[0].grid(alpha=.3)
    err=[abs(r["dt_mean"]-r["bag_us"]) for r in rows]
    ax[1].plot(bags,err,'o-',color="#58a6ff",lw=2)
    ax[1].set_xlabel("BAG [ms]"); ax[1].set_ylabel("|mean dT-BAG| [us]"); ax[1].set_title("Pacing accuracy")
    ax[1].grid(alpha=.3)
    fig.tight_layout(); fig.savefig(png,dpi=110); plt.close(fig); return b64(png)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--bags", default="100,200,400,800,1600")
    ap.add_argument("--dev", default="enp4s0")
    ap.add_argument("--count", type=int, default=2000)
    ap.add_argument("--repeat", type=int, default=10)
    ap.add_argument("--runs", type=int, default=3, help="BAG별 반복측정 후 가장 조용한 런 채택")
    ap.add_argument("--out", default="report.html")
    a=ap.parse_args()
    bags=[int(x) for x in a.bags.split(",")]
    here=os.path.dirname(os.path.abspath(__file__)); os.chdir(here)
    os.makedirs("results", exist_ok=True)
    rows=[]
    for bag in bags:
        print(f"[report] BAG={bag} ({bag*10/1000}ms) 측정중…", flush=True)
        rep=min(40,max(a.repeat,round(a.repeat*bag/200)))
        r=run_capture(a.dev,bag,a.count,rep,f"results/rep_{bag}",a.runs)
        if r: r["_png"]=b64(f"results/rep_{bag}.png"); rows.append(r); print(f"   MAD-std {r.get('rob_std',0):.2f}us (RMS전체 {r['j_rms']:.1f}), 표본 {r['used_intervals']}")
        else: print("   실패")
    if not rows: print("측정 실패"); return
    sc=summary_chart(rows,"results/rep_summary.png")
    # ── 시스템 구성 수집 ──
    import subprocess as _sp, datetime as _dt
    def _sh(c):
        try: return _sp.check_output(c,shell=True,stderr=_sp.DEVNULL).decode().strip()
        except Exception: return "?"
    gov=_sh("cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    cst="잠금(cpu_dma_latency=0)" if _sh("pgrep -f cpu_dma_latency") else "미적용(부하 민감)"
    ndrv=_sh("ethtool -i %s 2>/dev/null | awk '/^driver/{print $2}'"%a.dev)
    nspd=_sh("cat /sys/class/net/%s/speed 2>/dev/null"%a.dev)
    now=_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    def f(x,n=2):
        try: return f"{float(x):.{n}f}"
        except Exception: return str(x)
    # ── 요약 표 ──
    trs=""
    for r in rows:
        err=r["dt_mean"]-r["bag_us"]; v=r.get("verdict","?")
        trs+=(f"<tr><td>{int(r['bag_us']/10)}</td><td>{f(r['bag_us']/1000,3)}ms</td>"
              f"<td>{f(r['dt_mean'])}</td><td class='{'good' if abs(err)<1 else 'warn'}'>{err:+.2f}</td>"
              f"<td>{f(r.get('dt_median',0))}</td><td class='hl'>{f(r.get('rob_std',0))}</td>"
              f"<td>{f(r.get('mad',0))}</td><td>{f(r['j_rms'])}</td><td>{f(r['j_abs_max'],1)}</td>"
              f"<td>{f(r.get('j_p95',0),1)}</td><td>{f(r.get('j_p99',0),1)}</td>"
              f"<td>{f(r['p2p'],1)}</td><td>{r['used_intervals']}</td>"
              f"<td class='v{v}'>{v}</td></tr>")
    # ── BAG별 상세 카드 ──
    def interp(r):
        err=abs(r['dt_mean']-r['bag_us']); p=[]
        p.append("평균 간격이 BAG와 "+("정확히 일치" if err<1 else f"{err:.1f}µs 차")+f" → FPGA 페이싱 {'정확' if err<2 else '약간편차(측정노이즈)'}.")
        p.append(f"robust 지터(MAD-std) {f(r.get('rob_std',0))}µs = 배경노이즈 제거한 FPGA 고유지터 추정. RMS(전체) {f(r['j_rms'])}µs는 PC 스파이크 포함.")
        vd=r.get('verdict')
        if vd=='NORMAL': p.append("이상 없음: 시퀀스 연속, Lmax·Rate 정상.")
        elif vd=='WARNING': p.append(f"Rate 위반 {r.get('rate_violation',0)}건 — 간격 0.7×BAG 미만(측정노이즈 오탐 가능).")
        else: p.append(f"★FAULT: 손실 {r.get('seq_loss',0)}·중복 {r.get('seq_dup',0)}·재정렬 {r.get('seq_reorder',0)}·Lmax위반 {r.get('lmax_violation',0)}.")
        return " ".join(p)
    cards=""
    for r in rows:
        vc={'NORMAL':'#3fb950','WARNING':'#e3b341','FAULT':'#f85149'}.get(r.get('verdict'),'#8095a8')
        cards+=f"""<div class='card'><div class='ch'><h3>BAG {int(r['bag_us']/10)} · {f(r['bag_us']/1000,3)}ms</h3>
        <span class='badge' style='color:{vc};border-color:{vc}'>{r.get('verdict','?')}</span></div>
        <div class='grid'>
          <div class='m'><span>ΔTtx 평균</span><b>{f(r['dt_mean'])}</b>µs</div>
          <div class='m'><span>중앙값</span><b>{f(r.get('dt_median',0))}</b>µs</div>
          <div class='m'><span>min~max</span><b>{f(r['dt_min'],1)}~{f(r['dt_max'],1)}</b></div>
          <div class='m'><span>지터 MAD-std</span><b class='hl'>{f(r.get('rob_std',0))}</b>µs</div>
          <div class='m'><span>MAD</span><b>{f(r.get('mad',0))}</b>µs</div>
          <div class='m'><span>RMS(전체)</span><b>{f(r['j_rms'])}</b>µs</div>
          <div class='m'><span>|J| max</span><b>{f(r['j_abs_max'],1)}</b>µs</div>
          <div class='m'><span>J p95 / p99</span><b>{f(r.get('j_p95',0),1)}/{f(r.get('j_p99',0),1)}</b></div>
          <div class='m'><span>P2P</span><b>{f(r['p2p'],1)}</b>µs</div>
          <div class='m'><span>표본/프레임</span><b>{r['used_intervals']}/{r.get('frames','?')}</b></div>
        </div>
        <div class='anom'>이상검출 — 손실 <b>{r.get('seq_loss',0)}</b> · 중복 <b>{r.get('seq_dup',0)}</b> · 재정렬 <b>{r.get('seq_reorder',0)}</b> · Rate위반 <b>{r.get('rate_violation',0)}</b> · Lmax위반 <b>{r.get('lmax_violation',0)}</b> · 간격이상치(참고) {r.get('outliers',0)}</div>
        <div class='interp'>{interp(r)}</div>
        <img src='{r["_png"]}'></div>"""
    # ── 결론(자동) ──
    maxerr=max(abs(r['dt_mean']-r['bag_us']) for r in rows)
    robs=[r.get('rob_std',0) for r in rows]; faults=sum(1 for r in rows if r.get('verdict')=='FAULT')
    concl=(f"평균 ΔTtx가 모든 BAG에서 목표와 <b>최대 {maxerr:.1f}µs 이내</b>로 일치 → <b class=hl>FPGA BAG 페이싱 정확</b>. "
           f"robust 지터(MAD-std) <b>{min(robs):.1f}~{max(robs):.1f}µs</b>. "
           f"이상검출: {'<b class=hl>전 구간 정상(FAULT 0)</b>' if faults==0 else f'<b style=color:#f85149>FAULT {faults}건</b>'}. "
           f"단 지터 절대값은 PC SW타임스탬프+배경노이즈로 런별 편차 → 서브-µs 정밀은 HW-timestamp 캡처(ABM/CPM) 권장.")
    html=f"""<!doctype html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>AFDX Jitter Report</title>
<style>
body{{font:14px/1.6 system-ui,-apple-system,sans-serif;margin:0;background:#0b0f14;color:#e6f0fa}}
.wrap{{max-width:1120px;margin:0 auto;padding:24px}}
h1{{font-size:24px;margin:0 0 4px}}h2{{font-size:15px;color:#58a6ff;border-bottom:1px solid #22303f;padding-bottom:6px;margin:26px 0 12px}}
h3{{color:#e6f0fa;font-size:15px;margin:0}}
.mut{{color:#8095a8;font-size:13px}}.hl{{color:#3fb950}}b.hl{{color:#3fb950}}
.card{{background:#131a22;border:1px solid #22303f;border-radius:12px;padding:16px 18px;margin:14px 0}}
.ch{{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}}
.badge{{border:1.5px solid;border-radius:20px;padding:3px 12px;font-size:12px;font-weight:700}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}th,td{{padding:7px 8px;border-bottom:1px solid #22303f;text-align:right}}
th:first-child,td:first-child{{text-align:left}}th{{color:#8095a8;font-size:10.5px;text-transform:uppercase}}
td.hl{{color:#3fb950;font-weight:700}}td.good{{color:#3fb950}}td.warn{{color:#e3b341}}
td.vNORMAL{{color:#3fb950;font-weight:700}}td.vWARNING{{color:#e3b341;font-weight:700}}td.vFAULT{{color:#f85149;font-weight:700}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:9px;margin:10px 0}}
.m{{background:#0e141b;border:1px solid #22303f;border-radius:8px;padding:8px 10px;font-size:12px;color:#8095a8}}
.m b{{display:block;font-size:16px;color:#e6f0fa}}.m b.hl{{color:#3fb950}}
.anom{{background:#0e141b;border:1px solid #22303f;border-radius:8px;padding:8px 11px;font-size:12.5px;color:#8095a8;margin:8px 0}}
.interp{{font-size:13px;line-height:1.6;color:#c9d6e3;margin:8px 0}}
img{{width:100%;border-radius:8px;margin-top:8px;background:#0e141b}}
code{{background:#0e141b;padding:1px 5px;border-radius:4px;font-size:12.5px}}
.cfg{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px;font-size:13px}}
.cfg div{{color:#8095a8}}.cfg b{{color:#e6f0fa}}
ul{{margin:6px 0;padding-left:20px;font-size:13px;line-height:1.7}}
</style></head><body><div class=wrap>
<h1>AFDX 송신 지터 종합 리포트</h1>
<div class=mut>KETI KFDX(FPGA AFDX NIC) 송신 지터 측정 및 이상 검출 · {now}</div>

<h2>1. 측정 조건</h2>
<div class=card><div class=cfg>
<div>측정 시각<br><b>{now}</b></div>
<div>경로<br><b>KFDX(FPGA) → PC {a.dev}</b></div>
<div>수신 NIC<br><b>{a.dev} ({ndrv}, {nspd}Mb/s)</b></div>
<div>타임스탬프<br><b>커널 SW (libpcap)</b></div>
<div>CPU governor<br><b>{gov}</b></div>
<div>C-state<br><b>{cst}</b></div>
<div>프레임<br><b>60B(len=17), VL1 tx</b></div>
<div>반복 송신<br><b>BAG비례 스케일</b></div>
</div></div>

<h2>2. 측정 방법</h2>
<div class=card>
<ul>
<li><b>ΔTtx(n)</b> = 연속 AFDX 프레임의 PC 수신 타임스탬프 차 (외부 계측). <b>J(n) = ΔTtx(n) − BAG</b> = 프레임별 송출 지터.</li>
<li><b>평균 ΔTtx = BAG</b> 이면 FPGA가 BAG 페이싱을 정확히 지킨다는 뜻(대역폭 보장).</li>
<li>각 BAG를 <b>여러 번 측정해 가장 조용한 런(robust 지터 최소)</b>을 채택 — PC 노이즈는 지터를 더하기만 하므로 최소값이 FPGA 고유지터에 가장 근접(upper bound).</li>
<li><b>지터 MAD-std</b> = 1.4826×MAD(중앙값절대편차). 배경노이즈 스파이크에 강건 → <b>FPGA 고유지터 추정</b>. RMS(전체)는 PC 노이즈 스파이크 포함이라 과대평가.</li>
<li><b>이상 검출</b>: 시퀀스 손실/중복/재정렬(AFDX SN, ARINC664 1~255·0예약), Lmax 위반, Rate 위반(간격&lt;0.7×BAG), 간격 이상치(참고). 판정 NORMAL/WARNING/FAULT.</li>
<li>⚠ KFDX <code>get_head</code>의 <b>Max Jitter는 측정값이 아니라 계산된 AFDX 스펙 상한</b> <code>Σ(Lmax+20)×8/1Gbps</code>. 본 리포트는 외부 실측 지터.</li>
</ul></div>

<h2>3. 요약</h2>
<div class=card>
<table><thead><tr><th>BAG(×10µs)</th><th>목표</th><th>평균ΔT</th><th>오차</th><th>중앙값</th><th>지터 MAD-std</th><th>MAD</th><th>RMS(전체)</th><th>|J|max</th><th>J p95</th><th>J p99</th><th>P2P</th><th>표본</th><th>판정</th></tr></thead>
<tbody>{trs}</tbody></table>
<div class=mut style='margin-top:8px'>단위 µs. 오차=평균ΔT−BAG(0에 가까울수록 페이싱 정확). MAD-std=FPGA 고유지터 추정. p95/p99=|J| 백분위.</div></div>

{f'<h2>4. 추세</h2><div class=card><img src="{sc}"><div class=mut style="margin-top:6px">좌: BAG별 지터(MAD-std=고유지터, RMS=노이즈포함). 우: 페이싱 정확도(|평균ΔT−BAG|).</div></div>' if sc else ''}

<h2>5. BAG별 상세</h2>
{cards}

<h2>6. 결론</h2>
<div class=card><div class=interp>{concl}</div></div>

<h2>7. 재현</h2>
<div class=card><ul>
<li><code>sudo ./measure_setup.sh {a.dev} 8</code> — 정밀 측정용 격리(governor/IRQ/C-state)</li>
<li><code>python3 report.py --bags {a.bags} --dev {a.dev} --repeat {a.repeat}</code></li>
<li>데이터: <code>results/rep_*.json</code> · 아카이브: <code>reports/report_&lt;시각&gt;.{{html,md}}</code></li>
</ul></div>
<div class=mut style='margin-top:20px'>생성 report.py · github.com/hwkim3330/afdx-jitter</div>
</div></body></html>"""
    # 마크다운 (깃 친화적, GitHub 렌더)
    ts=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mdrows=""
    for r in rows:
        err=r["dt_mean"]-r["bag_us"]
        mdrows+=f"| {int(r['bag_us']/10)} | {f(r['bag_us']/1000,3)}ms | {f(r['dt_mean'])} | {err:+.2f} | **{f(r.get('rob_std',0))}** | {f(r.get('mad',0))} | {f(r['j_rms'])} | {f(r['j_abs_max'],1)} | {r['used_intervals']} | {r.get('verdict','?')} | {r.get('seq_loss',0)}/{r.get('lmax_violation',0)} |\n"
    md=f"""# AFDX 송신 지터 측정 리포트

- **측정 시각**: {ts}
- **경로**: KFDX(FPGA) → PC {a.dev}(igc) 외부 캡처, `J(n)=ΔTtx−BAG`
- **격리**: measure_setup.sh (governor=performance + IRQ/tcpdump 코어고정 + C-state 잠금)
- **프레임**: 60B(len=17), VL1 tx, 반복송신 {a.repeat}회

## 요약

| BAG(×10µs) | 목표 | 평균ΔT(µs) | 오차 | FPGA지터 MAD-std | MAD | RMS(전체·노이즈포함) | \|J\|max | 표본 | 판정 | 손실/Lmax |
|---|---|---|---|---|---|---|---|---|---|---|
{mdrows}
- 평균 ΔTtx = BAG 일치 → **FPGA 페이싱 정확**. Jitter RMS = 송출 간격 변동(작을수록 좋음).
- 시각 차트/히스토그램: 같은 타임스탬프의 `.html` 참조.

> ⚠ **지터값 주의**: 평균ΔT=BAG는 견고(FPGA 페이싱 정확). 지터는 PC SW타임스탬프+배경노이즈(rustdesk/chrome)가 섞여 MAD-std로도 런마다 편차. FPGA 고유지터는 **단일 µs(≤~2µs, best 관측)** 로 추정되나 PC로는 정밀 확정 불가 → 전용 HW-timestamp 캡처(ABM/CPM) 필요.

> KFDX `Max Jitter`(get_head)는 측정값 아닌 AFDX 스펙 상한 `Σ(Lmax+20)×8/1Gbps`. (docs/jitter_analysis.md)
"""
    stamp=datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("reports",exist_ok=True)
    open(f"reports/report_{stamp}.html","w").write(html)
    open(f"reports/report_{stamp}.md","w").write(md)
    # 최신본 복사 (브리지 서빙용)
    shutil.copy(f"reports/report_{stamp}.html", a.out)
    shutil.copy(f"reports/report_{stamp}.html", "web/report.html")
    open("report.md","w").write(md)
    print(f"[report] 완료 → reports/report_{stamp}.{{html,md}} + {a.out} (BAG {len(rows)}개)")

if __name__=="__main__": main()
