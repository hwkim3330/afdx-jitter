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
