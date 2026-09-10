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

## enp4s0(igc) vs USB 비교 — 2026-09-10 (BAG=200, 2ms)
| NIC / 타임스탬프 | ΔT평균 | Jitter RMS | \|J\|max | P2P | 표본 |
|---|---|---|---|---|---|
| USB 동글 r8152 (SW) | 1999.9µs | 38.5µs | 363µs | 707µs | 493 |
| **enp4s0 Intel igc (SW)** | **2000.00µs** | **3.8µs** | **44.7µs** | **88.5µs** | 571 |

- **enp4s0 커널 SW 타임스탬프가 USB 대비 ~10배 정밀** (RMS 38.5→3.8µs). USB 배칭 노이즈 제거.
- **FPGA BAG 페이싱 실측**: 평균 2000.00µs(정확), 지터 **RMS 3.8µs / P2P 88µs**. 이게 현재 최선 측정.
- ⚠ HW timestamp(`-j adapter_unsynced`)는 igc PHC(/dev/ptp0)가 **ptp4l/phc2sys로 규율 안 돼** 원시값이 비단조(garbage) → 못 씀. 서브-µs 측정 원하면 PHC 규율 필요(향후).
- 배선 교훈: 리부트(내 --link_down 여파)로 **VL 소실 + TX 인터럽트 버그(#11)로 송신 정지**였던 게 "프레임 0" 원인. `rmmod→insmod→--add VL→PHY UP 대기` 로 복구.
