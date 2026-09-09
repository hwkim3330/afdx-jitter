# AFDX FPGA Jitter 측정 기능 분석 (현황 리포트)

AFDX(ARINC 664 Part 7)의 Virtual Link(VL), BAG, Lmax, Jitter 관련 기존 기능을 분석하였다.

NXP T2080RDB 호스트 + PCIe Xilinx FPGA AFDX NIC(KFDX)에서 VL 생성, BAG 설정,
Lmax/Lmin 설정, Queueing/Sampling 방식, TX/RX 기능이 구현되어 있음을 확인하였다.

## Max Jitter 분석 (핵심 결론)
기존 출력 **Max Jitter는 실제 송신 프레임의 시간 편차 측정값이 아니라, 구성된 VL들의
최대 프레임 크기를 기준으로 계산되는 AFDX 기술 Jitter 상한값**임을 확인.

    Max Jitter = Σ(Lmax + 20) × 8 / Link Rate      (1Gbps, ns)

VL의 Lmax 변경 시 계산 결과가 동일 비율로 변화(1518↔512B → 정확히 8048ns 차이)하여 검증됨.

**프레임별 실측 Jitter(FPGA 내부 송신기준시각 ↔ 실제 송출시각 비교)는 미구현.**
PTP HW Timestamp는 IEEE 1588 시간동기용이며 데이터 VL 프레임 송신 Jitter 측정과 구분됨.

## 외부 수신 기반 실측 시험
BAG 2ms에서 평균 패킷 간격 ≈ 2ms 확인. 단 현재 USB Ethernet NIC의 SW Timestamp에
수십µs 변동이 포함되어 이를 FPGA 자체 송신 Jitter로 판단하기는 어려움.

## ⚠ 확인된 드라이버 취약점 (2026-09-09)
- `--send`는 tx_buf 한 버퍼분만 송출(count 무관) → 반복 송신 필요.
- **`--link_down` 실행 시 드라이버가 uninterruptible(D) hung → 콘솔 블록 → 물리 파워사이클 필요.**
  링크/TX 상태변경 명령은 피하고 read-only 진단만 사용할 것.
- 사용자가 본 "PHY-A retry 14302"는 retry가 아니라 TX 정지(hung) 누적값.

## 향후 검토 (내일 이후)
1. CPM/ABM 장비의 AFDX 송수신 및 측정 가능 여부 확인
2. USB 기반 측정 경로 제외 구성 검토
3. Ethernet Hardware Timestamp 지원 여부 확인 (i225/i226 = enp4s0, `ethtool -T`)
4. FPGA 내부 Timestamp(A: scheduler release, B: MAC TX) 추가 가능 여부 검토
5. 실제 TX Packet Interval 및 Jitter 정밀 측정
6. VL/BAG/Lmax 설정값과 실측 Timing 결과 비교 (USB 결과 RMS~24µs vs HW timestamp)
7. 측정 결과 실시간 시각화 및 이상 검출 기능 개발

## 내일 첫 스텝 (복구)
보드가 `--link_down` hung → SysRq 리부트 후 무음 상태. **물리 파워사이클** 후:
`root 로그인 → cd /mnt/flash && insmod kfdx.ko → 브리지 재시작(python3 serial_bridge.py)`.
관련 파일: capture_jitter.py, serial_bridge.py, docs/{jitter_analysis,capture_method,measurement_series}.md
