#!/usr/bin/env python3
"""
AFDX 지터 종합 리포트: BAG별로 측정(capture_jitter) → 표 + 차트 한 페이지 HTML.
사용: sudo ./measure_setup.sh 먼저 실행(정밀). 그다음:
  python3 report.py --bags 100,200,400,800,1600 --dev enp4s0 --repeat 10
  → report.html (자체완결, 브라우저로 열기)
"""
import argparse, base64, json, os, statistics as st, subprocess, sys

def run_capture(dev, bag, count, repeat, out):
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),"capture_jitter.py"),
                    "--dev", dev, "--bag", str(bag), "--len","17", "--count", str(count),
                    "--repeat", str(repeat), "--out", out],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try: return json.load(open(out+".json"))
    except Exception: return None

def b64(path):
    try: return "data:image/png;base64,"+base64.b64encode(open(path,"rb").read()).decode()
    except Exception: return ""

def summary_chart(rows, png):
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    except Exception: return ""
    bags=[r["bag_us"]/1000 for r in rows]
    fig,ax=plt.subplots(1,2,figsize=(11,3.6))
    ax[0].plot(bags,[r["j_rms"] for r in rows],'o-',color="#3fb950",lw=2,label="RMS")
    ax[0].plot(bags,[r["p2p"] for r in rows],'s--',color="#e3b341",lw=1.5,label="P2P")
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
    ap.add_argument("--out", default="report.html")
    a=ap.parse_args()
    bags=[int(x) for x in a.bags.split(",")]
    here=os.path.dirname(os.path.abspath(__file__)); os.chdir(here)
    os.makedirs("results", exist_ok=True)
    rows=[]
    for bag in bags:
        print(f"[report] BAG={bag} ({bag*10/1000}ms) 측정중…", flush=True)
        r=run_capture(a.dev,bag,a.count,a.repeat,f"results/rep_{bag}")
        if r: r["_png"]=b64(f"results/rep_{bag}.png"); rows.append(r); print(f"   RMS {r['j_rms']:.2f}us, 표본 {r['used_intervals']}")
        else: print("   실패")
    if not rows: print("측정 실패"); return
    sc=summary_chart(rows,"results/rep_summary.png")
    # HTML
    def f(x,n=2): return f"{x:.{n}f}"
    trs=""
    for r in rows:
        err=r["dt_mean"]-r["bag_us"]
        trs+=f"<tr><td>{int(r['bag_us']/10)}</td><td>{f(r['bag_us']/1000,3)}ms</td><td>{f(r['dt_mean'])}</td>"\
             f"<td class='{'good' if abs(err)<1 else 'warn'}'>{err:+.2f}</td><td>{f(r['dt_min'],1)}</td><td>{f(r['dt_max'],1)}</td>"\
             f"<td class='hl'>{f(r['j_rms'])}</td><td>{f(r['j_abs_max'],1)}</td><td>{f(r['p2p'],1)}</td><td>{r['used_intervals']}</td></tr>"
    cards=""
    for r in rows:
        cards+=f"""<div class='card'><h3>BAG {int(r['bag_us']/10)} · {f(r['bag_us']/1000,3)}ms</h3>
        <div class='kv'>평균 ΔTtx <b>{f(r['dt_mean'])}µs</b> · Jitter RMS <b class='hl'>{f(r['j_rms'])}µs</b>
         · |J|max {f(r['j_abs_max'],1)}µs · P2P {f(r['p2p'],1)}µs · 표본 {r['used_intervals']}</div>
        <img src='{r["_png"]}'></div>"""
    html=f"""<!doctype html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>AFDX Jitter Report</title>
<style>body{{font:14px/1.5 system-ui,sans-serif;margin:0;background:#0b0f14;color:#e6f0fa}}
.wrap{{max-width:1100px;margin:0 auto;padding:22px}}h1{{font-size:22px}}h3{{color:#58a6ff;font-size:14px;margin:0 0 8px}}
.mut{{color:#8095a8;font-size:13px}}.card{{background:#131a22;border:1px solid #22303f;border-radius:12px;padding:16px;margin:14px 0}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}}th,td{{padding:7px 9px;border-bottom:1px solid #22303f;text-align:right}}
th:first-child,td:first-child{{text-align:left}}th{{color:#8095a8;font-size:11px;text-transform:uppercase}}
td.hl{{color:#3fb950;font-weight:700}}td.good{{color:#3fb950}}td.warn{{color:#e3b341}}
img{{width:100%;border-radius:8px;margin-top:8px;background:#0e141b}}.kv{{color:#8095a8;font-size:12.5px;margin-bottom:4px}}
b{{color:#e6f0fa}}b.hl{{color:#3fb950}}code{{background:#0e141b;padding:1px 5px;border-radius:4px}}</style></head><body><div class=wrap>
<h1>AFDX 송신 지터 종합 리포트</h1>
<div class=mut>KFDX(FPGA) → PC {a.dev}(igc) 외부 캡처 · <code>J(n)=ΔTtx−BAG</code> · 시스템 격리(measure_setup.sh) 적용 · {len(rows)}개 BAG</div>
<div class=card><h3>요약</h3>
<table><thead><tr><th>BAG(×10µs)</th><th>목표</th><th>평균ΔT(µs)</th><th>오차(µs)</th><th>min</th><th>max</th><th>Jitter RMS</th><th>|J|max</th><th>P2P</th><th>표본</th></tr></thead>
<tbody>{trs}</tbody></table>
<div class=mut style='margin-top:8px'>· 평균 ΔTtx가 BAG와 일치 = FPGA 페이싱 정확 · Jitter RMS = 송출 간격 변동(작을수록 좋음)</div></div>
{f'<div class=card><h3>추세</h3><img src="{sc}"></div>' if sc else ''}
{cards}
<div class=mut style='margin-top:20px'>생성: report.py · 데이터 results/rep_*.json</div>
</div></body></html>"""
    open(a.out,"w").write(html)
    print(f"[report] 완료 → {a.out}  (BAG {len(rows)}개)")

if __name__=="__main__": main()
