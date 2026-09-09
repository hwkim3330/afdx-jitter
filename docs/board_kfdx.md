# KFDX AFDX NIC — 보드 레퍼런스

## 하드웨어
| 항목 | 값 |
|---|---|
| 호스트 보드 | NXP **T2080RDB** (PowerPC e6500 8코어), ppc64 |
| OS | Linux **4.1.35-rt41** (RT 실시간 커널), BusyBox, QorIQ SDK 2.0 (2019 KST 빌드) |
| 로그인 | `root` 무비번 |
| AFDX NIC | **KETI KFDX** — PCIe Xilinx FPGA, Vendor `7014h` |
| KFDX 드라이버 | `kfdx.ko` v1.0.20211209-1 |
| FPGA HW 버전 | **2025.7.30 A1.2** |
| 온보드 NIC | FMan MEMAC ×4 (eth0~3, DPAA/USDPAA) — AFDX와 별개 |
| 시간축 | PTP clock 등록됨(HW timestamp); 구버전 `aero_eth_app --ptp --hwts --kalman` |

## 접속
- 시리얼 콘솔: `/dev/ttyUSB0` @115200 (FTDI FT232)
- 웹 터미널: 이 repo `serial_bridge.py` → http://localhost:8777
- 보드 파일: `/mnt/flash/` = `init.sh`, `init_ring.sh`, `kfdx.ko`, `kfdx_app`

## 드라이버 올리기
```sh
cd /mnt/flash
insmod kfdx.ko          # dmesg에 BAR/버전 출력되면 성공
```

## kfdx_app 명령 (AFDX Virtual Link 관리)

### VL 추가/설정/조회/삭제
```sh
# 송신 VL 추가 (BAG 단위 = 10us → bag=1000 = 10ms)
./kfdx_app --add --vlid=1 --dir=tx --type=queueing \
           --max=1518 --min=64 --tx_buf_size=0x20000 --bag=1000
# dir  : tx | rx | bi
# type : queueing | sampling | sap
# max/min : Lmax / Lmin (프레임 크기 바이트)
# 그 외: --src_port=# --dst_port=# --name=<> --desc=<>

./kfdx_app --get --vlid=1     # 설정 조회
./kfdx_app --del --vlid=1     # 삭제
```

### 송수신
```sh
# 64B 패킷 10000개  (--len 은 페이로드; 17→64B 프레임)
./kfdx_app --send --vlid=1 --udp --len=17    --count=10000
# 1518B 패킷 50000개
./kfdx_app --send --vlid=1 --udp --len=1471  --count=50000

./kfdx_app --read --vlid=1    # 수신
```

### 통계 / 지터  ← 과제 핵심
```sh
./kfdx_app --status --net --hw
```
드라이버/앱이 VL별로 리포트하는 값:
- `Max Jitter`  ← ⚠ 측정값 아님. AFDX 지터 **예산(스펙)** = Σ(Lmax+20)*8/1Gbps. docs/jitter_analysis.md 참조
- `rx_vl_errors`, `rx_vl_errors_co`, `rx_vlid_err_cnt`
- `kfdxTxVlFifoFullIrq/Ish`  ← TX FIFO full (백프레셔/BAG 위반 징후)
- `Received N packets at VLk`

### 레지스터/PHY 직접 접근
```sh
./kfdx_app --read_reg  --addr=#
./kfdx_app --write_reg --addr=# --data=#
./kfdx_app --read_phy0/--write_phy0 --addr=# [--data=#]
./kfdx_app --read_phy1/--write_phy1 --addr=# [--data=#]
```

## 과제(AFDX 지터 측정)와의 매핑
| 과제 개념 | KFDX에서 |
|---|---|
| Virtual Link / BAG / Lmax | `--add --vlid --bag --max/--min` 이미 구현 |
| Timestamp A/B, Jitter | ⚠ **미구현**. `Max Jitter`는 스펙 상한(SW 계산). 실측 Ttx−Tref 없음 → jitter_analysis.md |
| BAG/Rate 위반 | TxVlFifoFull, rx_vl_errors 카운터 |
| 상위 SW 시각화 | 아직 없음 → **이 repo에서 만들 부분** |

즉 FPGA/드라이버엔 VL/BAG/Lmax 설정 + **이론적 Max Jitter 예산(계산값)** + PTP 동기 + 카운터만 있고,
**프레임별 실측 지터 `Ttx−Tref`는 미구현**이다(→ [jitter_analysis.md](jitter_analysis.md)).
이번 개발 = 실제 송출 지터 계측(외부 캡처 `ΔTtx` → `J(n)=ΔT−BAG`) + 통계 + 이상검출 + 실시간 시각화.
