# KFDX AFDX 측정 툴 — 문제점·한계·baseline 정리 (2026-09-11)

## 0. Baseline 버전 (수정전 — 수정버전과 비교용 기준)
| 구성요소 | 버전/식별 | 확인 방법 |
|---|---|---|
| KFDX 드라이버 kfdx.ko | **1.0.20211209-1** | `dmesg \| grep KFDX` |
| KFDX FPGA (Vendor) | 7014h, Bar0 8000080088d00000 | `dmesg` probe 로그 |
| kfdx_app | `--version` 없음(미지원). 명령: read/write, read_reg/write_reg, read_phy0/1/write_phy0/1, reset_all/tx/rx/stat, add/set/get/del, --send | `./kfdx_app` (인자없이) |
| PC NIC (측정) enp4s0 | Intel **igc**, fw **1038:73a** | `ethtool -i enp4s0` |
| igc HW 타임스탬프 필터 | rx-filter: **none, all** 지원 | `ethtool -T enp4s0` |

> 수정버전 도착 시: 위 표와 대조해 (a)드라이버 버전 (b)kfdx_app 명령 변화 (c)레지스터맵 변화 (d)버그#11(TX 인터럽트 정지) 수정 여부를 비교.

## 1. 해결된 문제 (이번에)
| 문제 | 증상 | 원인 | 해결 |
|---|---|---|---|
| **HW 타임스탬프 garbage** | `-j adapter_unsynced` 간격 14ms·348ms 난장판 | tcpdump/libpcap가 RX 필터를 **PTP(1588) 전용**으로 둠 → AFDX(비-PTP) 프레임 미타임스탬프 | raw 소켓 + `SIOCSHWTSTAMP(filter=ALL)` + `SO_TIMESTAMPING(raw hw)` → **RMS 112ns 달성** (`hwts_jitter.py`) |
| 지터 3.8~140µs 변동 | 재측정마다 값 다름 | PC C-state/governor/코어경합 | `measure_setup.sh` 격리 → SW 1.4µs, HW로 완전제거 |
| 손실검출 맹점 | 송신경계 SN을 손실로 오판 | 시간게이트 오분류 | 게이트 제거(SN 연속성) |
| Rate 오탐 | 타임스탬프 분할 1451+581≈2×BAG | 쌍합 검사로 면역화 |

## 2. 미해결/구조적 한계 (정직)
- **FPGA 내부 단계별 지터 분리 불가**: HW 타임스탬프(238ns)는 NIC 수신점 집계값. FPGA TX스케줄러(Timestamp A)·MAC TX(Timestamp B) 단계 분리는 **FPGA RTL 수정** 필요. → fault localization("어느 파이프라인 단계")은 여전히 불가.
- **CPM/ABM 접근 불가**: ABM은 단방향 탭(브리지 아님). PC에서 ARP/ping/IPv6(4서브넷) 무응답. CPM management 경로 미확인. → 재개조건(콘솔케이블/관리IP/브리지설정/매뉴얼) 충족 전 중단.
- **kfdx PTP ≠ 표준 PTP**: 보드 kfdx PTP는 ptpd 기반이나 AFDX 인캡슐 → 표준 ptp4l과 상호운용 불가. (오늘의 PTP 데모는 **PC 자체 Linux PTP**로 별개.)
- **버그 #11 (baseline)**: TX 인터럽트 정지로 송신이 멈추는 경우 있음(리부트 후 발현). rmmod→insmod→VL 재등록으로 복구. 수정버전에서 해결됐는지 확인 필요.

## 3. 안전 금지사항 (재확인)
- **`--link_down` 절대금지**: KFDX 드라이버 D-state 행 → SysRq 리부트 유발(실제 발생). 
- **미검증 레지스터 write 금지**: read_reg/read_phy/get 등 읽기만 사용. 고장주입은 kfdx_app 정상명령(add/set/send)+pcap 조작으로만.

## 4. 안 해도 되는 것 (포화)
- 정상 BAG 재측정(스위프·다중VL·프레임크기·best-of-N 완료). HW 타임스탬프로 지터도 확정(238ns).
- CPU/IRQ/governor 개별 튜닝(measure_setup.sh 통합, C-state가 지배요인 확인).
