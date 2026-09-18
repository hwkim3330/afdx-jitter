# Kontron D10 (WebStaX/vtss) 종합 분석 — 기능 · 현재설정 · AFDX 활용

- **일자**: 2026-09-18
- **접속**: `http://192.168.100.1/json_rpc` (admin / 빈 비번), PC enp4s0=192.168.100.50/24 → D10 **Gi 1/6** in-band
- **분석 근거**: `/json_spec`(1172 메서드), `d10_config/d10_full_analysis.json`(실덤프)

## 1. 장비 식별
- **포트 8개**: **Gi 1/1~1/6 (6× 1G RJ45)** + **2.5G 1/1, 2.5G 1/2 (2× 2.5G)**
- MTU **10240(점보)**, **PFC(우선순위 흐름제어)** 지원, 8 QoS 클래스
- 펌웨어: Microsemi/Microchip **WebStaX(vtss)** JSON-RPC. MAC OUI 00:80:82(PEP/Kontron)
- 관리: JSON-RPC(admin/빈비번) + 웹UI. running-config 텍스트는 웹UI/CLI 전용(API 미노출)

## 2. TSN 기능 총람 (capabilities 실측 한계값)
| 기능 | 표준 | 한계/지원 |
|---|---|---|
| **FRER** (무결절 이중화) | 802.1CB | 인스턴스 **127**, member스트림 **512**, compound **256**, egress **최대4포트**, history 2~32, recovery vector/match |
| **PSFP** (스트림 필터·폴리싱·게이트) | 802.1Qci | stream filter **256**, stream gate **256**, flow meter **256** |
| **TAS** (시간인식 셰이퍼) | 802.1Qbv | GCE **256**, 사이클 **256ns~1s**, SDU 64~10240 |
| **Frame Preemption** | 802.1Qbu | **지원**(HasQueueFramePreemption=true) |
| **CBS** (크레딧 셰이퍼) | 802.1Qav | queue shaper(포트별 큐 셰이핑) |
| **PTP** (정밀시각) | 1588/802.1AS | **클록 4개**, HW 클록도메인 |
| **QoS/폴리서** | — | 8클래스, 포트 폴리서 100k~3.27Gbps, QCE 256 |
| **CFM** | 802.1ag | 지원 |
| VLAN/MSTP/LLDP/RMON/sFlow | — | VLAN 4095, FID 63 등 |

→ **AFDX 데모에 필요한 TSN 4대(FRER·PSFP·TAS·프리엠션)를 모두 갖춘 본격 스위치.**

## 3. 현재 설정 상태 (실덤프)
### 포트
| 포트 | Link | 비고 |
|---|---|---|
| Gi 1/6 | **UP 1G** | PC(enp4s0) in-band 관리 |
| Gi 1/1, 1/2 | DOWN | AFDX 보드 A/B — **보드 DRAM 고장으로 down** |
| Gi 1/3~1/5, 2.5G×2 | DOWN | 미사용 |
- 전 포트 autoNeg, MTU 10240, PFC off, FC off.

### FRER (잔재 — 이전 keti-reconfig Pi 데모)
| # | Mode | VLAN | Egress | Stream(DMAC) | Oper |
|---|---|---|---|---|---|
| 1 | generation | 35 | Gi1/4, Gi1/6 | #1 DC:A6:32:17:77:6E | active |
| 2 | recovery | 35 | Gi1/1 | #2 DC:A6:32:B7:A1:77 | active |
| 5 | generation | 35 | Gi1/4, Gi1/6 | #5 DC:A6:32:17:77:11 | active |
| 6 | recovery | 35 | Gi1/1 | #6 DC:A6:32:B7:A1:77 | active |
- DMAC `DC:A6:32:*` = **Raspberry Pi**(3-Pi FRER 무결절 데모 잔재, VLAN35). AFDX와 무관 → 정리 대상.

### 미설정
- **PSFP**(flow meter/filter/gate) 0개, **PTP** 클록 미구성, **미러** off, LLDP 이웃 0.

## 4. AFDX 데모 관점 — D10 활용 방안
1. **FRER로 AFDX A/B 무결절 실증**: AFDX A/B(Gi1/1·1/2)를 member 스트림으로 recovery. 단 AFDX엔 R-TAG 없어 자동 dedupe 불가 → D10이 **generation@ingress로 R-TAG 삽입**하는 게이트웨이 필요(`docs/d10_frer_afdx.md`).
2. **★ PSFP로 AFDX BAG policing**: PSFP flow meter(802.1Qci)는 **스트림별 rate 제한**. AFDX **BAG(대역폭 보장)을 스위치에서 감시/강제** 가능 — VL별 스트림 매칭 + flow meter로 BAG 초과 프레임 drop. 이게 AFDX 모니터링 툴과 직결되는 킬러 기능.
3. **TAS로 시간 슬롯**: VL별 송신 윈도우를 802.1Qbv 게이트로 스케줄(AFDX BAG를 TAS 사이클로 매핑).
4. **PTP로 시각 동기**: 4클록으로 스위치 기준 시각 → 지터/지연 하드웨어 타임스탬프.

## 5. 관리/재현
```bash
python3 d10_proxy.py            # 프록시+대시보드 :8099
python3 /tmp/d10_analyze.py     # 이 분석 재생성 → d10_config/d10_full_analysis.json
# 잔재 FRER 정리(원하면): frer.config.del [1],[2],[5],[6]
```
전체 덤프: `d10_config/d10_full_analysis.json`. 스펙: `/json_spec`(1172 메서드).

## 6. 완전 설정 덤프 (전체 285개 항목, 2026-09-18)
`d10_config/d10_complete_dump.json` — 무인자 `.get` 메서드 전부 호출한 **전체 config/status 덤프**(값 있는 것 285개). 아래는 실제 구성값 핵심:

### 시스템 · 관리
- **관리 IP**: VLAN1 인터페이스 **192.168.100.1/24 (static, DHCP off)**, MAC **00:80:82:B9:64:B3**, 라우팅 off(순수 L2 스위치)
- **SNMP**: 활성(Mode on, EngineId 800019CB03008082B964B3)
- **NTP**: 비활성. **SSH**: 설정있음. 시스템 LED: green solid(정상)
- **MSTP**: 기본값(MaxAge20/Hello2/FwdDelay15, force mstp, BPDU guard off)

### VLAN
- **정의된 VLAN**: **1(기본/관리), 35(FRER Pi데모), 100**
- 전 포트 **hybrid 모드**, AccessVlan 1, 전 VLAN trunk 허용. CustomSPort EtherType 0x88A8

### 미설정/기본 (깨끗)
- PSFP·PTP클록·미러·sFlow·voiceVlan·ACL·portSecurity·DHCP서버·IGMP snooping 등 대부분 기본/미설정.

### 잔재 정리 대상
- FRER #1/2/5/6 (VLAN35, Pi MAC) + VCL 스트림 #1/2/5/6 = 이전 3-Pi 데모. AFDX용으로 쓰려면 `frer.config.del`·`vcl.config.stream.set`으로 정리 후 재구성.

> **결론**: 이 D10은 기본 L2 + SNMP/SSH 관리만 켜진 상태에서, 이전 Pi FRER 데모 설정(VLAN35)만 얹혀 있음. PSFP·PTP·TAS·미러는 백지 → AFDX 데모용으로 새로 구성 가능. 전체 항목은 `d10_complete_dump.json` 참조.
