#!/usr/bin/env python3
"""FPGA BAG 페이싱 지터의 미시구조 분석 — HW 타임스탬프 간격의 이산 레벨 분해.
발견: 지터는 랜덤이 아니라 240ns 격자 위 2레벨 디더링(결정론적, 유계).
240ns ≈ 72×(1/300MHz) — 보드 디바이스트리 clk=299970000 방증.
사용: python3 quantum_analysis.py  (results/frames_bag*.json 사용)
"""
import json, statistics as st
from collections import Counter
BAGS=[100,200,400,800,1600]; CLK=299.97e6
rows=[]
for bag in BAGS:
    try: fr=json.load(open(f'results/frames_bag{bag}.json'))
    except FileNotFoundError: continue
    hw=sorted(f[0] for f in fr if f[0]>0); bag_ns=bag*10*1000
    d=[(hw[i]-hw[i-1])*1e9 for i in range(1,len(hw))]
    d=[x for x in d if 0.9*bag_ns<x<1.1*bag_ns]
    mean=st.mean(d); res=[x-mean for x in d]
    b=Counter(round(x/10)*10 for x in res)
    tops=sorted([k for k,v in b.items() if v>len(d)*0.03])
    q=(tops[-1]-tops[0]) if len(tops)>1 else 0
    rows.append(dict(bag=bag, bag_ms=bag*10/1000, n=len(d), levels=tops,
                     quantum_ns=q, cycles_300M=round(q*CLK/1e9,1) if q else 0,
                     split=[round(100*b[t]/len(d),1) for t in tops]))
for r in rows:
    print(f"BAG {r['bag_ms']:>2.0f}ms  n={r['n']:>4}  레벨{r['levels']}ns 비율{r['split']}%  양자={r['quantum_ns']}ns={r['cycles_300M']}×(1/300MHz)")
qmed=st.median([r['quantum_ns'] for r in rows if r['quantum_ns']])
print(f"\n양자 중앙값 {qmed}ns → 스케줄 클록 {1e9/qmed/1e6:.3f}MHz = 300MHz/{300e6/(1e9/qmed):.1f}")
print("결론: 지터는 240ns 격자 2레벨 디더링(결정론적·유계). BAG 단위(10µs)가 240ns의 비정수배라 ±1양자로 진동.")
json.dump(rows, open('results/quantum_levels.json','w'), ensure_ascii=False, indent=1)
# plot
try:
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(7,3.4))
    fr=json.load(open('results/frames_bag200.json')); hw=sorted(f[0] for f in fr if f[0]>0)
    d=[(hw[i]-hw[i-1])*1e9 for i in range(1,len(hw))]; d=[x for x in d if 1.99e6<x<2.01e6]
    m=st.mean(d)
    ax.hist([x-m for x in d],bins=120,color='#2e9e5b',edgecolor='#0e141b')
    ax.set_title('AFDX interval jitter is 2-level (BAG 2ms): 240ns quantum, not random')
    ax.set_xlabel('interval - mean [ns]'); ax.set_ylabel('count'); ax.grid(alpha=.25)
    ax.annotate('240 ns\n(72 cyc @ 300MHz)',xy=(0,1),xytext=(120,max(Counter(round(x-m) for x in d).values())*0.6),
                fontsize=9,color='#0e7f88')
    fig.tight_layout(); fig.savefig('results/quantum_hist.png',dpi=120); print("saved results/quantum_hist.png")
except Exception as e: print("plot skip:",e)
