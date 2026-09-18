# A2Z 차량 ZONAL 네트워크 실토폴로지 (재구성/78 기준, 2026-09-18)

출처: 산업부-재구성/78 "A2Z 차량 RADAR 연결 테스트 / 설정 사항 정리" (김형래·송현수·이하림).

## 스위치 3대 (ZONAL, 12포트 1G)
| 스위치 | 위치 | 포트 MAC prefix |
|---|---|---|
| **ZONAL_FR** | 앞(우) | FA-AE-C9-26-A4-0X (X=포트) |
| **ZONAL_FL** | 앞(좌) | E6-F4-41-C9-57-0X |
| **ZONAL_REAR** | 뒤 | 02-06-3F-F5-0E-0X |
> ※ 12포트 ZONAL 스위치. 내 앞의 테스트 D10(8포트)와 별개지만 같은 WebStaX 계열이면 JSON-RPC/FRER 동일 적용.

## 스위치 간 연결 = 삼각형 (2 disjoint 경로 확보)
```
        ZONAL_FR ─────(FR.P8 ↔ FL.P8)───── ZONAL_FL
            │                                  │
     (FR.P10 ↔ REAR.P10)              (FL.P9 ↔ REAR.P9)
       = PATH2                            = PATH1
            │                                  │
            └──────────── ZONAL_REAR ──────────┘
                              │ P2
                          ACU_IT LAN1  (컴퓨트/인지)
```
- **REAR P9 = "Fault Injection PATH1"**(FL 경유), **REAR P10 = "Fault Injection PATH2"**(FR 경유) → 이 두 경로가 이중화 대상.
- 삼각형이라 각 앞 스위치→REAR 에 **2경로** 존재:
  - FR→REAR: ①직결(FR.P10→REAR.P10=PATH2) ②FL경유(FR.P8→FL.P8, FL.P9→REAR.P9=PATH1)
  - FL→REAR: ①직결(FL.P9→REAR.P9=PATH1) ②FR경유(FL.P8→FR.P8, FR.P10→REAR.P10=PATH2)

## 노드 배치 (포트별)
### ZONAL_FR
| P | 노드 | | P | 노드 |
|---|---|---|---|---|
| 1 | Hummingbird LIDAR FRONT | | 9 | PANDA 40P LIDAR RIGHT |
| 8 | → ZONAL_FL (P8) | | 10 | → ZONAL_REAR (P10, PATH2) |
| 12 | MCU_FR | | 2~6 | RADAR_FR / RADAR_FRT (연결가능) |
### ZONAL_FL
| P | 노드 | | P | 노드 |
|---|---|---|---|---|
| 8 | → ZONAL_FR (P8) | | 10 | PANDA 40P LIDAR LEFT |
| 9 | → ZONAL_REAR (P9, PATH1) | | 12 | MCU_FL |
| 1~7 | RADAR_FL (연결가능) | | | |
### ZONAL_REAR (ACU 측)
| P | 노드 | | P | 노드 |
|---|---|---|---|---|
| 1 | Hummingbird LIDAR REAR | | 8 | ACU_IT TOTAL I/O (PANDA RIGHT) |
| **2** | **ACU_IT LAN1 (ACU 메인)** | | 9 | → ZONAL_FL (PATH1) |
| 3 | ACU_IT LAN1 (미연결) | | 10 | → ZONAL_FR (PATH2) |
| 11 | ACU_IT TOTAL I/O (PANDA LEFT) | | 12 | MCU_REAR |
- ※ 티켓 note: **REAR P2(ACU LAN1)로 브로드캐스트 전송이 문제없으면 P8·P11 연결 제외 가능.**

## 센서
- **LiDAR**: Hummingbird FRONT(FR.1)·REAR(REAR.1), PANDA 40P RIGHT(FR.9)·LEFT(FL.10)
- **RADAR**: RADAR_FRT·RADAR_FR(FR), RADAR_FL(FL), RADAR_RL(REAR), **RADAR_RR = ZCU 미연결/Local-CAN**
- **MCU**: MCU_FR/FL/REAR (각 P12), CAN A3/A4(REAR)

## FRER(802.1CB) 이중화 설계 — 이 토폴로지 기준
목적: 앞 센서(LiDAR/RADAR) 스트림을 **PATH1·PATH2 두 경로로 ACU까지 무손실 전달**. 단일 스위치/링크(경로) 고장에도 인지 무중단.
- **generation**: ZONAL_FR·ZONAL_FL 이 각자 센서 스트림을 **직결 + 상대 앞스위치 경유** 두 방향으로 복제(R-TAG).
- **recovery**: ZONAL_REAR 가 **P9(PATH1)·P10(PATH2)** 로 온 두 복사본을 dedupe → ACU(P2).
- **fault injection**: PATH1 또는 PATH2 끊고 REAR recovery `{Passed 유지, Lost=0}` 확인 = 무결절 실증. (포트 라벨이 이미 "Fault Injection PATH1/2")
- **스트림 식별**: 센서별 VLAN 또는 src MAC(LiDAR/RADAR MAC)로 VCL 매칭.
- **보너스**: PSFP로 센서 대역 policing, PTP로 시각동기.

> 다음 단계: 각 ZONAL 스위치 mgmt 접속정보(IP/JSON-RPC) 확보 → FR/FL generation + REAR recovery 자동 구성 스크립트.
