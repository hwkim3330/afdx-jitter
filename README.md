# afdx-jitter

**FPGA(KETI KFDX / Xilinx) 기반 AFDX Virtual Link 송신 지터 측정 · 이상 검출 데모 툴**

호스트 = NXP T2080RDB, AFDX NIC = PCIe FPGA(KFDX). 웹 GUI로 VL 설정 · 송신 · 실측 지터
측정 · 시각화까지 한 번에. (TSN그룹/224 "AFDX 데모용 툴")

## 빠른 시작
```bash
# 1) 브리지 실행 (보드 시리얼 ↔ 웹)
python3 serial_bridge.py --dev /dev/ttyUSB0 --baud 115200
#    → 웹 터미널  http://localhost:8777
#    → KFDX GUI  http://localhost:8777/kfdx.html

# 2) (선택) 정밀 지터 측정용 시스템 격리 — 없으면 값이 부하따라 튐
sudo ./measure_setup.sh enp4s0 8

# 3) CLI 측정
python3 capture_jitter.py --dev enp4s0 --bag 200 --repeat 12 --out run
#    → run.json(통계) + run.png(ΔT 타임라인 + 지터 히스토그램)
```

## 핵심 결과 (실측, 2026-09-10)
| 항목 | 값 |
|---|---|
| FPGA BAG 페이싱 | 평균 ΔTtx = BAG **완벽 일치** (2000.00µs @BAG200 등) |
| **FPGA 송신 지터** | **RMS ~1.4µs**, P2P ~20µs (격리 측정) |
| 측정 경로 | KFDX AFDX → (ABM 통과) → PC enp4s0(igc), 커널 SW 타임스탬프 |
| 측정 노이즈 제거 | C-state 잠금 + governor + IRQ/tcpdump 코어고정 (`measure_setup.sh`) |

> ⚠ KFDX가 출력하는 `Max Jitter`(get_head)는 **측정값이 아니라 AFDX 스펙 상한**
> `Σ(Lmax+20)×8/1Gbps` 계산값. 실측은 외부 수신 ΔTtx(`J=ΔT−BAG`). → docs/jitter_analysis.md

## 구성
| 경로 | 내용 |
|---|---|
| `serial_bridge.py` | 시리얼 ↔ WebSocket ↔ HTTP 브리지 + KFDX 명령 RPC + 캡처 op |
| `web/kfdx.html` | **KFDX GUI**: VL 설정/송신/상태카운터/지터예산/실측캡처/값읽기/시각화 |
| `web/index.html` | 웹 시리얼 터미널 (xterm.js, 오프라인) |
| `capture_jitter.py` | 실측 지터 캡처/분석 (외부 ΔTtx, 반복송신+버스트필터, PNG) |
| `measure_setup.sh` | 정밀 측정용 시스템 격리 (governor/IRQ/C-state/코어고정) |
| `docs/` | 분석·방법·측정시리즈·보드레퍼런스 (아래) |
| `results/`, `examples/` | 측정 결과 JSON/PNG |
| `board/` | 보드 `/mnt/flash` 원본 스크립트 백업 |

## 문서
- [`docs/jitter_analysis.md`](docs/jitter_analysis.md) — Max Jitter 정체(스펙 상한) A~H 분석
- [`docs/capture_method.md`](docs/capture_method.md) — 외부 ΔTtx 측정 방법
- [`docs/measurement_series.md`](docs/measurement_series.md) — BAG 스위프·비교·격리 결과·결론
- [`docs/board_kfdx.md`](docs/board_kfdx.md) — KFDX 하드웨어·명령 레퍼런스
- [`docs/analysis_report.md`](docs/analysis_report.md) — 현황 리포트

## 로드맵
1. [x] 보드 콘솔 + 웹 터미널
2. [x] KFDX AFDX NIC · 명령셋 파악 (VL/BAG/Lmax)
3. [x] Max Jitter = AFDX 스펙 상한(측정 아님) 확정
4. [x] 실측 지터 파이프라인(외부 ΔTtx) + 시스템 격리로 **신뢰성 확보(RMS 1.4µs)**
5. [x] 웹 GUI (VL/송신/카운터/지터예산/실측캡처/값읽기/시각화)
6. [ ] (선택) 드라이버 소스 확보 → 버그 #1~14 수정(연속 스트림/카운터/reset break)
7. [ ] (선택) 전용 HW-timestamp 캡처(ABM/CPM)로 서브-µs
