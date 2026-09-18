# AFDX A/B 리던던시 vs FRER(802.1CB) — Kontron D10 실측 리포트

- **일자**: 2026-09-18
- **장비**: KETI KFDX(FPGA AFDX NIC, T2080RDB) · Kontron D10(WebStaX TSN 스위치) · PC(enp4s0)
- **도구**: `d10_proxy.py`(JSON-RPC 프록시+캡처) · `web/frer.html`(실시간 대시보드) · `board_send.py`(보드 송신)

## 1. 목적
AFDX 고유의 **A/B 이중망 리던던시**와 IEEE **802.1CB FRER**(Frame Replication & Elimination)를 한 스위치(D10)에서 나란히 관측·비교하고, 상호 호환 가능성을 실측한다.

## 2. 토폴로지 (실측 확인)
```
PC enp4s0(192.168.100.50) ── D10 mgmt(192.168.100.1)   [JSON-RPC, admin/빈비번]
                     PC는 D10 Gi1/6 에 물림 (핑폭주 RX델타로 특정)
   AFDX 기기(KFDX) ─ A망(eth0) ── D10 Gi1/1
                   ─ B망(eth1) ── D10 Gi1/2
   보드 콘솔 = /dev/ttyUSB0 (FTDI),  ttyUSB1 = ESP(무관)
```
- D10 Gi1/1·Gi1/2: **Link up 1G** (KFDX A/B PHY 활성 확인).
- D10 = vtss WebStaX. 주요 JSON-RPC: `port.status.get`, `port.statistics.rmon.get`, `frer.config/status.get`, `frer.statistics.get[inst,egress_ifindex,0]`, `vcl.config.stream.*`, `mirror.config.session.set`. 전체 스펙 `/json_spec`(1.9MB).

## 3. 결과

### 3.1 AFDX A/B 이중망 리던던시 — 실증 ✅
연속 송신 중 D10 포트 카운터(`port.statistics.rmon.get`):

| 시각 | Gi1/1 (A) RxPkts | Gi1/2 (B) RxPkts | 차이 |
|---|---|---|---|
| t0 | 2 301 | 2 304 | 3 |
| t0+2s | 3 344 | 3 347 | 3 |
| t0+6s | 5 433 | 5 436 | 3 |
| (BAG 100 재시작) | 19 642 | 19 644 | 2 |

- **A와 B가 동일 속도(~525 pkt/s 각)로 증가, 차이 상수(2~3)** → AFDX가 **같은 프레임을 두 망에 동시 송신**하는 이중화가 실시간으로 관측됨. 한 망이 죽어도 반대 망이 무결절 커버하는 구조.

### 3.2 실제 AFDX 프레임 — 와이어샤크급 해부 ✅
D10 포트 미러(Gi1/1+1/2 → PC)로 캡처한 실프레임 271개(`web/data/afdx_frames.json`):
```
Ethernet II — 60 bytes
  Destination : 03:00:00:00:00:01   (AFDX 멀티캐스트, VLID=1)
  Source      : 02:00:00:00:00:20
  EtherType   : 0x0800 (IPv4)          ← R-TAG 없음
IPv4 : 10.0.0.0 → 208.208.0.1, len 46, TTL 128, proto 17(UDP)
UDP  : sport 0, dport 0, len 26
AFDX : Sequence Number = 마지막 바이트 (0,1,2,… 순차, ARINC664 1~255 순환)
페이로드: 01 02 03 … 11 (테스트 패턴)
```
- **SN이 AFDX의 이중화 시퀀스** — A·B 양쪽에 같은 SN으로 실려, 수신 엔드시스템이 SN으로 중복 제거.

### 3.3 FRER(802.1CB) 구성 — D10
- recovery 인스턴스 + VCL 스트림(AFDX DMAC 매칭, ingress Gi1/1·Gi1/2, egress Gi1/3) 구성 성공(OperState active).
- 통계 API: `frer.statistics.get` → `{Passed, Discarded, OutOfOrder, Tagless, Lost, Rogue, ...}`.
- startup-config에 기존 인스턴스 4개(generation/recovery, VLAN35) 잔존.

## 4. 호환성 결론 — AFDX ↔ FRER
**둘은 같은 목적(무결절 이중화)·다른 계층이라 직접 호환되지 않는다.**

| 측면 | AFDX A/B | FRER(802.1CB) |
|---|---|---|
| 표준 | ARINC 664 P7 | IEEE 802.1CB |
| 제거 위치 | 엔드시스템(AFDX NIC) | 브리지/스위치 또는 엔드 |
| 시퀀스 | 페이로드 1바이트 SN | R-TAG 6바이트, 16비트 |
| 복제 | 송신 엔드시스템이 A·B 동시 | generation 노드가 R-TAG 삽입 후 복제 |
| 오버헤드 | 없음 | +6바이트 R-TAG |
| 상호운용 | AFDX 전용 | 표준 TSN, 벤더무관 |

- **실측 근거**: 캡처한 AFDX 프레임은 EtherType 0x0800(IPv4)로 직행 — **R-TAG가 없다.** 따라서 D10 FRER는 SN으로 자동 제거(dedupe)할 수 없다(FRER는 R-TAG 시퀀스 기반).
- **상호연동하려면**: D10이 게이트웨이로 AFDX 스트림에 **R-TAG를 생성/제거**해야 함(FRER generation@ingress / termination@egress). AFDX SN ↔ R-TAG 변환은 표준에 없는 커스텀 매핑 필요.

## 5. 산출물
- `d10_proxy.py` — D10 JSON-RPC 프록시(:8099) + `/snapshot`(포트·RMON·FRER) + `/capture`(pcap 디코드) + `/send`(웹버튼→보드 버스트).
- `web/frer.html` — 리포트급 실시간 대시보드: 토폴로지 패킷방향 애니, A/B 수신율 그래프, 와이어샤크 프레임 해부, 차이표, FRER 실시간, `▶ AFDX 버스트 송신` 버튼.
- `web/data/afdx_frames.json` — 실캡처 271프레임 디코드.
- `board_send.py`/`board_cmd.py`/`board_diag.py` — 보드 시리얼 로그인·송신·진단.

## 6. 한계 · 이슈 (정직)
- **KFDX 드라이버가 연속 송신을 못 버팀**: `while true` 무한 --send 루프가 매번 `/dev/kfdx` open/close 반복 → 커널 Oops(주소 0x12b15c 반복) + OOM-killer → 보드 파워사이클 필요. **유한 버스트만** 사용해야 함.
- **미러 목적지=관리포트 금지**: 미러 dest를 Gi1/6(=PC)로 걸면 그 포트 egress가 미러전용이 돼 D10 관리(TCP) 완전 차단 → 파워사이클만 복구. 캡처는 빈 포트+별도 NIC로.
- **보드 콘솔 무응답(세션 종료 시점)**: 반복 크래시·파워사이클 후 `/dev/ttyUSB0` 콘솔이 U-Boot 배너조차 0바이트. FTDI 어댑터는 PC측 정상 확인(재init·재플러그해도 0). 원인은 (a)콘솔 UART/케이블 또는 (b)초기 부팅 행(DDR 등) — 콘솔 출력이 없어 원격 구분 불가. D10 쪽 Gi1/1·1/2 PHY는 up이라 보드 전원 자체는 인가됨. **추가 진행은 보드 콘솔 복구 후 가능.**

## 7. 재현
```bash
# 프록시+대시보드
python3 d10_proxy.py            # http://localhost:8099/
# (보드 콘솔 정상 시) 웹 버튼 또는:
python3 board_send.py /dev/ttyUSB0 burst 8   # 유한 버스트(무한루프 금지)
# D10 상태
curl -s localhost:8099/snapshot | python3 -m json.tool
```
근거: `web/data/afdx_frames.json`, `[[afdx_jitter_project]]` 메모리, `PROBLEMS.md`.
