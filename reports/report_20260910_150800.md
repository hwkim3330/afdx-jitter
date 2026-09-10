# AFDX 송신 지터 측정 리포트

- **측정 시각**: 2026-09-10 15:08:00
- **경로**: KFDX(FPGA) → PC enp4s0(igc) 외부 캡처, `J(n)=ΔTtx−BAG`
- **격리**: measure_setup.sh (governor=performance + IRQ/tcpdump 코어고정 + C-state 잠금)
- **프레임**: 60B(len=17), VL1 tx, 반복송신 10회

## 요약

| BAG(×10µs) | 목표 | 평균ΔT(µs) | 오차 | FPGA지터 MAD-std | MAD | RMS(전체·노이즈포함) | \|J\|max | 표본 | 판정 | 손실/Lmax |
|---|---|---|---|---|---|---|---|---|---|---|
| 100 | 1.000ms | 1000.05 | +0.05 | **2.47** | 1.67 | 77.88 | 412.6 | 591 | WARNING | 0/0 |
| 200 | 2.000ms | 2000.01 | +0.01 | **3.53** | 2.38 | 74.71 | 515.1 | 476 | NORMAL | 0/0 |
| 400 | 4.000ms | 4000.10 | +0.10 | **3.53** | 2.38 | 88.05 | 481.9 | 487 | NORMAL | 0/0 |
| 800 | 8.000ms | 8000.00 | -0.00 | **16.97** | 11.44 | 136.35 | 437.4 | 490 | NORMAL | 0/0 |

- 평균 ΔTtx = BAG 일치 → **FPGA 페이싱 정확**. Jitter RMS = 송출 간격 변동(작을수록 좋음).
- 시각 차트/히스토그램: 같은 타임스탬프의 `.html` 참조.

> ⚠ **지터값 주의**: 평균ΔT=BAG는 견고(FPGA 페이싱 정확). 지터는 PC SW타임스탬프+배경노이즈(rustdesk/chrome)가 섞여 MAD-std로도 런마다 편차. FPGA 고유지터는 **단일 µs(≤~2µs, best 관측)** 로 추정되나 PC로는 정밀 확정 불가 → 전용 HW-timestamp 캡처(ABM/CPM) 필요.

> KFDX `Max Jitter`(get_head)는 측정값 아닌 AFDX 스펙 상한 `Σ(Lmax+20)×8/1Gbps`. (docs/jitter_analysis.md)
