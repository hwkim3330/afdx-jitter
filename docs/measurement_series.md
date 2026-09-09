# 실측 지터 측정 시리즈 (외부 캡처 ΔTtx)

장비: 보드 KFDX(FPGA AFDX) → PC USB NIC(r8152, SW 타임스탬프). 프레임 60B(len=17), VL1 tx.
방법: `capture_jitter.py` (반복송신 + 버스트경계 제외). → `results/bag*.json|png`.

| BAG(×10µs) | 목표 간격 | 평균 ΔTtx | 중앙값 | Jitter RMS | \|J\|max | P2P |
|---|---|---|---|---|---|---|
| 100 | 1000 µs | **999.68** | 999.93 | 56.5 | 407 | 771 |
| 200 | 2000 µs | **1999.90** | 1999.86 | 38.5 | 363 | 707 |
| 400 | 4000 µs | **4000.12** | 4000.19 | 59.9 | 408 | 701 |

## 해석
1. **평균 ΔTtx = BAG 정확히 일치**(오차 <0.4µs) → FPGA의 BAG 페이싱은 정확.
2. **Jitter RMS(≈40–60µs)·|J|max(≈400µs)가 BAG에 무관하게 거의 일정** →
   측정 지터는 **부하/BAG에 따라 변하는 FPGA 지터가 아니라, 고정된 측정계(USB) 노이즈 바닥**.
   실제 FPGA 송출 지터는 이 바닥 아래에 가려져 있어 이 방법으론 분리 불가.
3. 결론: **정밀 FPGA 지터엔 HW 타임스탬프 NIC(i225/i226) 또는 FPGA 내부 Timestamp A/B 필요.**
   (→ [capture_method.md](capture_method.md), [jitter_analysis.md](jitter_analysis.md))

내일 계획: `enp4s0`(Intel igc, HW 타임스탬프) 를 보드로 재배선 후 동일 측정 → USB 바닥 제거.
