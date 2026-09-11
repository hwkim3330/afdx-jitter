# KFDX FPGA · 리눅스 구조 분석 (2026-09-11)

보드 오프라인 상태에서 캡처해둔 dmesg·디바이스트리·측정 결과로 역설계한 KFDX(Xilinx FPGA AFDX NIC) 내부 구조. 정본 근거는 부팅 dmesg + `results/quantum_levels.json`.

## 1. FPGA 식별 · PCIe
- **KETI KFDX Network Driver v1.0.20211209-1**, PCIe **Vendor 7014h** (SubVendor FFFFFFFFh).
- Xilinx 기반 설계 — AXI INTC + AXI CDMA + 커스텀 AFDX user 로직 (아래 블록맵).

## 2. 레지스터 블록 맵 (Bar0 = 8000080088d00000)
dmesg `kfdx_probe` 로그 기준. 오프셋은 Bar0 기준.

| 블록 | 물리주소 | Bar0 오프셋 | 역할 (추정) |
|---|---|---|---|
| **Bar0 (control)** | `…88d00000` | +0x00000 | 제어/상태 레지스터 베이스 |
| **INTC** | `…88d20000` | +0x20000 | Xilinx AXI Interrupt Controller |
| **CDMA** | `…88d30000` | +0x30000 | Xilinx AXI Central DMA (프레임 전송) |
| **USER** | `…88d80000` | +0x80000 | AFDX user 로직(VL 스케줄러·MAC·카운터) |

- kfdx_app의 `--read_reg --addr=#` 는 이 공간을 읽는다(단, PHY read는 addr 인자 무시 = B03).
- CDMA 존재 = 프레임을 DMA로 밀어 넣는 구조. TX 인터럽트 정지(B04)는 INTC/CDMA 완료 인터럽트 경로 결함으로 추정.

## 3. 클록 도메인
디바이스트리/`time_init` dmesg:

| 클록 | 주파수 | 용도 |
|---|---|---|
| 네트워크/FPGA 인터페이스 | **299.97 MHz** (`clk=299970000`, 4블록) | AFDX MAC·페이싱 |
| e6500 CPU | 1799.82 MHz | 호스트 |
| decrementer | 37.496 MHz | 커널 타이머 |

### ★ BAG 페이싱 양자 = 300MHz의 72클록
측정(`quantum_analysis.py`)으로 확정: 프레임 간격이 **240 ns 격자 위 2레벨**로만 움직임.
- **240 ns = 72 × (1/299.97 MHz)** — 인터페이스 클록의 72분주.
- AFDX BAG 단위(10 µs) = 41.67 × 240 ns (비정수) → 프레임 릴리스가 인접 격자점 ±1 양자로 진동 = **결정론적·유계 지터**(랜덤 아님, 최악 ±240 ns).
- 즉 FPGA VL 스케줄러는 **240 ns tick 카운터**로 BAG를 센다(추정). USER 블록 내부.

## 4. AFDX 프레임 구조 (실측)
- dst MAC `03:00:00:00:00:<VLID>` — VLID = 6번째 바이트(`b[5]`).
- 시퀀스번호(SN) = 프레임 **마지막 바이트**(`b[-1]`), ARINC664 1~255 순환·0 예약.
- 최소 프레임 60 B(len=17 UDP). Lmax = VL별 `--max`.

## 5. 리눅스/드라이버 구조
- 보드: NXP T2080RDB, ppc64 e6500, **RT 커널 4.1.35-rt41**, BusyBox, root 무비번. rootfs=ramdisk(휘발), `/mnt/flash`=jffs2(영속, 여기 kfdx.ko/kfdx_app/init.sh).
- char dev `/dev/kfdx`, `/proc/kfdx*`.
- **위험 접근점**(전부 커널 fault → 보드 hang, 물리 파워사이클 필요):
  - `--link_down` → 드라이버 D-state hung (B01)
  - `/proc/kfdx` read → Bad page map (B15)
  - 미설정 VL `--get` → paging request 오류 (B16)
  - 공통 원인 추정: **미검증 포인터/슬롯 역참조** — 드라이버가 상태·경계 검사를 안 함.

## 6. 내부 지터 분리를 위해 필요한 것 (D/E)
현재 240 ns는 NIC 수신점 집계값. FPGA **내부 단계별** 분리엔 USER 블록에 타임스탬프 카운터 2개 필요:
- **Timestamp A** = VL 스케줄러 release 시점(240 ns tick 카운터 스냅샷)
- **Timestamp B** = MAC TX SFD 시점
- 드라이버가 이 둘을 프레임별로 노출(레지스터/ioctl) → release↔MAC 지연, MAC 지터를 각각 관측 가능.
- 이게 있으면 "어느 파이프라인 단계 지터"까지 localization(연구축 D/E).

## 7. 요약 도식
```
PCIe(7014h) ─ Bar0 ┬ +0x20000 AXI INTC ── (TX 완료 IRQ; B04 정지 지점 추정)
                    ├ +0x30000 AXI CDMA ── 프레임 DMA
                    └ +0x80000 USER ────── VL 스케줄러(240ns tick=300MHz/72) → AFDX MAC → PHY
                                            └ [필요] Timestamp A(release) / B(MAC TX)
클록: 299.97MHz 인터페이스 → BAG tick 240ns
```
