# 실측 지터 캡처 방법 (외부 수신 ΔTtx)

KFDX가 per-frame `Ttx−Tref`를 노출하지 않으므로(→ [jitter_analysis.md](jitter_analysis.md)),
1차 실측은 **PC 수신 측에서 프레임 도착 타임스탬프**로 한다.

```
Ttx(n)   Ttx(n+1)       ΔTtx(n) = Ttx(n+1) − Ttx(n)   (PC NIC 타임스탬프)
  └──ΔTtx──┘            J(n)    = ΔTtx(n) − BAG        (프레임별 송출 지터)
```
PTP 불필요: 간격(ΔT)은 PC 단일 시계로 재므로 클록 오프셋에 불변.
(보드↔PC **절대** 지연 `Ttx−Trx`를 보려면 PTP 동기 필요 — 별도 과제.)

## 검증된 사실 (실측)
- **배선**: PC USB NIC(`enxc84d44263ba6`) ↔ 보드 **FPGA AFDX 포트**로 연결됨.
  수동 캡처 시 무트래픽(브로드캐스트조차 0) = 조용한 point-to-point = FPGA 포트.
- **FPGA PHY**: `--status --phy` → SPEED 1G / FULL / **LINK UP** / AN COMPLETE.
- **프레임**: `02:00:00:00:00:20 → 03:00:00:00:00:01`(AFDX dst MAC, VLID 인코딩),
  ethertype IPv4/UDP.
- **평균 간격 = BAG**: BAG=200(2ms) 설정 시 ΔTtx 평균 **1999.7µs** = 2000µs. FPGA 평균 페이싱 정확.
- **`--send` 1회 = tx_buf 한 버퍼분만** 송출(count 무관) → `--repeat`로 반복 송신해 표본 확보.

## ⚠ 측정 정밀도 한계
- USB NIC(r8152)는 **SW 타임스탬프**(하드웨어 PHC 없음) → USB 배칭으로 **±수백µs 노이즈**.
  실측 예: RMS ~110µs, P2P ~1250µs. 이는 **NIC 노이즈 바닥**이지 FPGA 지터가 아님
  (평균이 BAG에 정확히 맞는 것이 근거).
- 정밀 측정 경로:
  1. **HW 타임스탬프 NIC**(Intel i225/i226 = `enp4s0`, `ethtool -T`에 hardware-*) 사용 → ns급.
     단 현재 연구원망에 물려 있어 물리 재배선 필요.
  2. 보드 PTP(`--ptp --hwts`)로 보드·PC 시계 동기 후 `Ttx−Trx` 절대 측정.
  3. FPGA RTL에 Timestamp A(scheduler release)+B(MAC TX) 추가(정공법, 펌웨어 작업).

## 사용법
```bash
# 브리지가 떠 있어야 함(웹소켓 RPC로 보드 송신 트리거)
SUDO_PASS=1 python3 capture_jitter.py --dev enxc84d44263ba6 \
    --vlid 1 --bag 200 --len 17 --count 2000 --repeat 12 --out results_run
# -> results_run.json (통계), results_run.png (ΔT 타임라인 + 지터 히스토그램)
```
결과 예시: `examples/example_jitter.png`
