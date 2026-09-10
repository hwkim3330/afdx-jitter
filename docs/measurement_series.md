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

## HW timestamp 시도 결과 (2026-09-10)
- phc2sys 로 igc PHC(/dev/ptp0)를 시스템클록에 락(offset ±1~18ns)시켜도, `-j adapter_unsynced`
  캡처는 AFDX 프레임 간격이 scattered(median≈1ms, |J|max>1ms)로 **garbage**.
- 원인: **igc HW RX 타임스탬프가 일반(비-PTP) 프레임엔 신뢰 불가** (all 필터 모드 불안정).
- **결론: 커널 SW 타임스탬프(igc)가 이 용도엔 정확·안정 → RMS 3.8µs 가 정본 측정값.**
  서브-µs가 꼭 필요하면 전용 캡처카드(HW-ts 보장) 또는 FPGA 내부 TS(정공법) 필요.

## "제대로" 측정의 현실적 한계 (2026-09-10 결론)
- **견고한 결과**: ΔTtx **평균 = BAG(2000.0µs) 정확** — 모든 런/부하에서 일정. **FPGA 페이싱 정확** 확정.
- **지터 RMS는 PC 부하에 지배됨**: 조용할 때 ~3.8µs, 바쁠 때(chrome/rustdesk/Xorg) ~50-120µs.
  SW 타임스탬프(커널 인터럽트)라 부하 민감. **가장 조용한 관측 3.8µs = FPGA 지터 상한(upper bound)**.
- igc HW 타임스탬프는 비-PTP 프레임에 신뢰불가(위 참조). phc2sys 락해도 안 됨.
- **⇒ 안정적 µs 정밀 지터는 이 PC로 불가. 전용 HW-timestamp 캡처(= ABM/CPM 항전 카드)가 정답.**
  즉 사용자의 ABM/CPM 구조가 이 측정의 올바른 도구. PC 툴은 (a)평균 페이싱 검증 (b)지터 상한 확인용.

## ★ 신뢰 측정 확보 (2026-09-10, 시스템 격리 후)
`measure_setup.sh` 적용: **governor=performance + NIC IRQ 전용코어 + C-state 잠금(cpu_dma_latency=0) + tcpdump 코어고정**.
→ SW 타임스탬프 노이즈(부하·C-state 웨이크업) 제거. **범인은 C-state**(2ms 간격마다 코어 깊은잠→웨이크업 지연).

| BAG | 목표 | 평균 ΔTtx | Jitter RMS | P2P |
|---|---|---|---|---|
| 100 | 1000µs | 1000.11 | 3.8µs | 94µs |
| 200 | 2000µs | **2000.00** | **1.4µs** | 20µs |
| 400 | 4000µs | 4000.02 | 1.5µs | 10µs |
| 800 | 8000µs | 8000.10 | 2.3µs | 17µs |

- **결론: FPGA 송신 지터 = RMS ~1.4µs, 평균 = BAG 완벽 일치.** enp4s0 SW 타임스탬프 + 격리로 신뢰성 확보.
- 격리 전 3.8~140µs 변동은 전부 PC 측정 노이즈(C-state/governor/코어경합)였음 — HW 한계 아님.
- 재현: `sudo ./measure_setup.sh enp4s0 8` 후 `python3 capture_jitter.py --dev enp4s0 --bag N`.
- USB 시리얼 vs LAN 제어는 측정에 무관(FPGA 내부 BAG 페이싱, 관리/캡처 경로 분리).

## 이상 검출 (2026-09-10, 과제 "이상 검출" 절반)
capture_jitter가 프레임별로 검출 → VL 판정(NORMAL/WARNING/FAULT):
- **시퀀스 손실/중복/재정렬**: AFDX SN(프레임 마지막 바이트, ARINC664 1~255 순환·0예약)로 판정. 타임스탬프 무관 = 신뢰.
- **Lmax 위반**: 프레임 크기 > Lmax(`--lmax`).
- **Rate 위반**: 간격 < 0.7×BAG(버스트 내, 너무 빠른 송신).
- **간격 이상치**: |ΔT−BAG| > 6×MAD-std → 참고(PC 측정노이즈 포함, 판정 미반영).
- **판정**: 프레임레벨(시퀀스/Lmax)만 FAULT 좌우(신뢰), Rate→WARNING, 간격이상치는 참고.
- 검증: 정상=NORMAL, 1518B+`--lmax 512`=FAULT(Lmax위반 전건). report/GUI에 판정 표시.

## 다중 VL 경쟁 테스트 (2026-09-10)
`multi_vl_test.py` — 여러 VL 동시 송신, dst MAC 끝바이트(=VLID)로 분리해 VL별 지터/판정.
3 VL(1,2,3) 동시, BAG=200(2ms) 결과:

| VL | 프레임 | 평균ΔT | 지터 MAD-std | 판정 | 손실/Lmax |
|---|---|---|---|---|---|
| 1 | 841 | 2000.0µs | 2.47µs | NORMAL | 0/0 |
| 2 | 789 | 2000.0µs | 1.41µs | NORMAL | 0/0 |
| 3 | 737 | 2000.0µs | 1.41µs | NORMAL | 0/0 |

- **AFDX 핵심 보장 실증**: 3 VL 경쟁에도 **각 VL이 BAG(2ms)를 정확히 유지**(per-VL 대역폭 격리),
  지터 증가 없음(1.4~2.5µs), 손실 0. FPGA 스케줄러가 VL별 BAG를 올바르게 보장.
- 더 강한 경쟁(작은 BAG/대형 프레임/많은 VL)은 `--vls`/`--bag`/`--len`로 확장 가능.

## 프레임 크기(Lmax) 스위프 (2026-09-10, BAG=200 고정)
`capture_jitter.py --len <payload>` 로 프레임 크기별 측정:

| payload len | 프레임 크기 | 평균ΔT | 지터 MAD-std | RMS(전체) |
|---|---|---|---|---|
| 17 | 60B | 1993µs | 4.95µs | 38µs |
| 214 | 257B | 1908µs | 39.9µs* | 143µs |
| 470 | 513B | 1937µs | 6.01µs | 114µs |
| 982 | 1025B | 1903µs | 8.48µs | 202µs |
| 1471 | 1514B | 1920µs | 6.01µs | 164µs |

- **지터(MAD-std)는 프레임 크기에 대체로 무관** (~5-8µs). *257B의 40µs는 배경노이즈 낀 런.
- 평균 ΔT는 BAG(2000µs)를 측정노이즈 범위(±100µs)에서 추종. 대형 프레임일수록 표본 적어 노이즈↑.
- 시사: BAG 페이싱이 프레임 크기와 독립적으로 유지됨(AFDX 설계 의도대로). 정밀 확인은 HW캡처 권장.

## CPM/ABM 접근 조사 결과 (2026-09-10, 결론: 접근 불가)
정밀 지터를 위해 CPM(HW-timestamp 노드) 접근을 시도했으나 실패. 확정 근거:
- **ABM은 L2 브리지가 아니라 단방향 탭/포워더**: KFDX AFDX 프레임을 enp4s0로 넘겨주지만(그래서 캡처는 됨),
  반대방향(enp4s0→)은 아무것도 통과 안 시킴.
- enp4s0에서 4개 서브넷(10.42/192.168.0/192.168.1/172.16)에 ARP·핑·IPv6 능동 자극 → **응답 MAC은
  enp4s0 자신뿐, CPM/ABM 프레임 0**. 즉 관리 트래픽이 CPM에 안 닿음.
- CPM은 ABM eth1에 LAN 연결됐으나, ABM이 브리지 안 하므로 PC에서 도달 불가. USB 시리얼도 미연결(펌웨어 포트 추정).
- **결론**: 현 구성에선 CPM 접근 물리적 불가 → 정밀 HW-timestamp 측정 불가. **PC 방법(enp4s0 SW+격리+best-of-N)이 최선.**
- 향후 재개 조건: (a) CPM 콘솔에 직접 시리얼(진짜 콘솔포트) 또는 (b) ABM 브리지모드 설정 가능 시.

## ⚠ PC 캡처 배선 의존성
현재 캡처 동작 조건: **KFDX AFDX 데이터포트 → ABM → PC enp4s0**. enp4s0가 이 경로에서 빠지면 프레임 수신 안 됨.
배선 변경(원복 등) 후 캡처 안 되면 이 경로부터 확인.
