# D10 FRER(802.1CB) 추천 구성 — 제대로 된 무결절 이중화 데모

목표: **생성(replicate+R-TAG) → 2경로 분리 → 복구(dedupe)** 를 한 D10에서 실증하고, **한 경로를 끊어도 0-loss(무결절)** 를 카운터로 증명. AFDX 보드 없이 **PC + D10 + 루프백 케이블**만으로 완결.

## 0. 먼저 잔재 정리
이전 Pi 데모 설정 제거:
```
frer.config.del [1]; frer.config.del [2]; frer.config.del [5]; frer.config.del [6]
# VCL 스트림 1/2/5/6 도 재사용 or 삭제
```

## 1. 추천 토폴로지 A — 단일 D10 루프백 (권장, 케이블만 있으면 됨)
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

## 요약 (권장)
- **토폴로지 A(단일 D10 루프백) + 카운터 관측** 이 가장 간단·확실. 케이블 2개면 됨.
- VLAN 200 전용, generation#10(Gi1/1·1/2 복제) + recovery#20(Gi1/3·1/4→Gi1/5 dedupe).
- **케이블 하나 뽑아 Lost=0 유지**를 보여주면 무결절 증명 끝.
