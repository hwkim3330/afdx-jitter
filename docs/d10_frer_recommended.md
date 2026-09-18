# D10 FRER(802.1CB) 추천 구성 — 제대로 된 무결절 이중화 데모

목표: **생성(replicate+R-TAG) → 2경로 분리 → 복구(dedupe)** 를 한 D10에서 실증하고, **한 경로를 끊어도 0-loss(무결절)** 를 카운터로 증명. AFDX 보드 없이 **PC + D10 + 루프백 케이블**만으로 완결.

## 0. 먼저 잔재 정리
이전 Pi 데모 설정 제거:
```
frer.config.del [1]; frer.config.del [2]; frer.config.del [5]; frer.config.del [6]
# VCL 스트림 1/2/5/6 도 재사용 or 삭제
```

## 1. ★ 추천 토폴로지 — D10 4대 이중경로 (정석)
D10 4대가 있으면 **물리적으로 분리된 2경로**로 진짜 FRER 네트워크를 구성한다(루프백 불필요).
```
                     ┌───► S2 (경로A 중계) ───┐
Talker ──► S1(gen) ──┤                        ├──► S4(recovery) ──► Listener
(PC enp4s0)          └───► S3 (경로B 중계) ───┘                     (PC USB-랜 or 장치)
```
- **S1 = generation**: Talker 스트림 수신 → R-TAG 삽입 + **S2/S3 두 포트로 복제**.
- **S2, S3 = 중계**: 각자 한 복사본만 나름(VLAN200 trunk 포워딩, FRER 설정 불필요). **물리 분리 = 독립 경로**.
- **S4 = recovery**: S2·S3에서 온 두 복사본을 **vector recovery로 dedupe** → Listener.
- **엔드포인트**: PC 2 NIC(enp4s0=talker@S1, USB-랜=listener@S4) 또는 별도 장치/Pi.

### 링크 (6개) & 포트 배정 예
| 링크 | 용도 |
|---|---|
| Talker ─ S1 Gi1/6 | 입력 |
| S1 Gi1/1 ─ S2 Gi1/1 | 경로A 시작 |
| S1 Gi1/2 ─ S3 Gi1/1 | 경로B 시작 |
| S2 Gi1/2 ─ S4 Gi1/1 | 경로A 끝 |
| S3 Gi1/2 ─ S4 Gi1/2 | 경로B 끝 |
| S4 Gi1/6 ─ Listener | 출력 |

### 설정 요약 (스위치별)
- **공통**: VLAN 200 신설, 관여 포트 200 trunk. 각 스위치 mgmt IP 확인(예 192.168.100.1~.4).
- **S1**: VCL 스트림(talker 매칭, ingress Gi1/6) + `frer generation`(EgressPorts=[Gi1/1,Gi1/2], StreamId0=스트림, vector).
- **S2/S3**: VLAN200 포워딩만(별도 FRER 없음).
- **S4**: VCL 스트림(ingress Gi1/1·Gi1/2 각각) + `frer recovery`(EgressPorts=[Gi1/6], vector, history8).

### 무결절 실증
- 정상: S4 recovery `{Passed↑, Discarded↑}`(중복 제거중), Lost=0.
- **경로A 절단**(S1─S2 또는 S2─S4 케이블 뽑기) → **Passed 계속↑, Lost=0** = 무결절 절체.
- 확장: 4대를 **링(ring)** 으로 묶으면 어느 링크 1개 끊겨도 보호(더 현실적). 단 gen/recovery는 여전히 S1/S4.

---

## 1b. D10 3대 — 삼각형(3노드 링)
4대가 아니면 **3대 삼각형**이 정석. 두 경로 중 하나는 S1→S3 직결, 하나는 S2 경유.
```
Talker ─► S1(gen) ═══════직결(경로A)═══════► S3(recovery) ─► Listener
              │                                  ▲
              └──► S2(중계) ──►──────────────────┘  (경로B)
```
- **S1 = generation**: 복제 → **직결 링크(→S3)** + **S2행 링크** 두 egress.
- **S2 = 중계**: VLAN200 포워딩만.
- **S3 = recovery**: **S1 직결** + **S2 경유** 두 입력을 dedupe → Listener.
- 링크(5개): Talker─S1, S1─S3(경로A 직결), S1─S2·S2─S3(경로B), S3─Listener.
- **무결절**: S1─S3 직결 끊으면 S2 경유로 커버, S2쪽 끊으면 직결로 커버 → 어느 쪽이든 Lost=0.
- 4대와 차이: 경로B가 S2 1홉 더 → 경로 간 스큐 약간 큼(오히려 FRER 정렬 관측엔 더 재밌음).

---

## 2. (참고) 단일 D10 루프백 — 1대만 있을 때
```
                    ┌─────────────── Kontron D10 ───────────────┐
 PC(enp4s0) ─Gi1/6─►│ [수신]                                     │
                    │  FRER generation(#10): R-TAG 삽입 + 복제   │
                    │     ├─► Gi1/1 ══(외부 케이블)══► Gi1/3 ─┐   │
                    │     └─► Gi1/2 ══(외부 케이블)══► Gi1/4 ─┤   │
                    │  FRER recovery(#20): 2경로 dedupe ◄──────┘   │
                    │     └─► Gi1/5 ─► (관측: PC 2번째 NIC or 카운터)
                    └────────────────────────────────────────────┘
```
- **필요 케이블 2개**: Gi1/1↔Gi1/3, Gi1/2↔Gi1/4 (2개의 독립 경로 = A/B).
- 관측은 (a) **카운터만으로 충분**(recovery Passed/Discarded) 또는 (b) Gi1/5에 PC 2번째 NIC(USB-랜) 꽂아 실수신 확인.
- 트래픽 소스: PC가 Gi1/6으로 테스트 스트림 송신(scapy/pktgen).

### VLAN 설계
- **FRER 전용 VLAN 200** 신설(관리 VLAN1과 분리). 관련 포트(Gi1/1~1/6) 200 trunk/access.

### 스트림 정의 (VCL) — 테스트 트래픽 매칭
```
vcl.config.stream.set [10, {destinationMacAddress:"01:00:5e:00:00:0a", destinationMacMask:"ff:...:ff",
                            outerTag:"one", outerTagVidValue:200, protocol:"ANY", ...}]
vcl.config.interface.stream.add ["Gi 1/6", 10]      # 수신 포트에 부착(generation 입력)
vcl.config.stream.set [11, {..동일 DMAC.., outerTagVidValue:200}]  # recovery 입력용
vcl.config.interface.stream.add ["Gi 1/3", 11]      # 경로A 복귀
vcl.config.interface.stream.add ["Gi 1/4", 11]      # 경로B 복귀 (같은 스트림, 2 ingress)
```

### FRER generation 인스턴스 #10
```
frer.config.add [10, {Mode:"generation", FrerVlan:200, Algorithm:"vector",
  EgressPorts:["Gi 1/1","Gi 1/2"],      # 2경로로 복제
  StreamId0:10, AdminActive:true, HistoryLen:8, ResetTimeoutMsec:100}]
```

### FRER recovery 인스턴스 #20
```
frer.config.add [20, {Mode:"recovery", FrerVlan:200, Algorithm:"vector",
  EgressPorts:["Gi 1/5"],               # dedupe 후 출력
  StreamId0:11, AdminActive:true, HistoryLen:8, ResetTimeoutMsec:100,
  TakeNoSequence:false, IndividualRecovery:true}]
```
- **vector recovery** + history 8 = 최근 8시퀀스 창에서 중복 제거. (D10 한계: history 2~32)

## 2. 무결절 실증 시나리오 (핵심)
1. PC에서 스트림 연속 송신(VLAN200, DMAC 매칭). 예: `scapy`로 초당 1000pps, R-TAG는 D10이 붙임.
2. **정상**: `frer.statistics.get[20,"Gi 1/5",0]` → **Passed 증가, Discarded 증가**(=중복 제거중). Gi1/5 egress = 원래 rate(중복 제거됨).
3. **경로A 절단**: Gi1/1↔Gi1/3 케이블 뽑기 → **Passed 계속 증가(0-loss!)**, Discarded만 0으로. = 무결절 절체 실증.
4. 케이블 복구 → Discarded 다시 증가(양경로 복원).
- **관측 지표**: recovery `{Passed, Discarded, OutOfOrder, Lost, Tagless}`. Lost=0 유지가 무결절 증거.

## 3. 토폴로지 B — 2노드 (더 현실적, 장비 추가 시)
- D10 #1 = generation(엔드A), D10 #2 = recovery(엔드B), 사이 2경로.
- 또는 옛 3-Pi 데모 재활용(Pi가 엔드시스템, D10이 FRER 브리지). 잔재 VLAN35 설정이 그 흔적.

## 4. AFDX 연계 (보드 복구 시)
- AFDX A/B(Gi1/1·1/2)는 R-TAG가 없으므로, **D10 generation을 AFDX 수신점에 걸어 R-TAG를 부여**(AFDX→FRER 게이트웨이) 후 recovery. AFDX SN↔R-TAG는 표준 매핑 없어 "이중화 관측"까지가 현실적.
- 또는 **PSFP flow meter로 AFDX BAG policing**(VL별 rate 감시) — FRER와 별개로 강력.

## 5. 관측/자동화
- `d10_proxy.py` 대시보드에 recovery 통계 패널 추가하면 실시간 Passed/Discarded/Lost 그래프로 무결절 절체가 눈에 보임.
- 설정 자동화: `d10_frer_setup.py` 확장(이 문서의 #10/#20 파라미터로).

## 요약 (권장 — D10 4대)
- **4대 이중경로**: S1(gen) → S2/S3(중계 2경로) → S4(recovery). 물리 분리라 진짜 무결절 실증.
- **VLAN 200 전용**, S1 generation(S2·S3로 복제) + S4 recovery(vector, history8, dedupe).
- **엔드포인트**: PC 2 NIC(talker/listener) 또는 장치. 중간 S2/S3는 VLAN200 포워딩만.
- **증명**: 한 경로 케이블 뽑아 **Lost=0 유지** → 무결절 절체. 4대를 링으로 묶으면 링크 보호까지.
- 실제 하실 때 스위치 4대 mgmt IP만 주시면 `d10_frer_setup.py` 확장해 S1/S4 한 방에 구성해드림.
