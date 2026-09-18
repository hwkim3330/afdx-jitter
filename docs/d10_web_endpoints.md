# D10 웹 REST 엔드포인트 — 전체 기능 맵 (227 페이지)

**핵심**: WebStaX 웹UI의 모든 기능은 **HTTP POST `/config/<page>`** 로 스크립트 가능(JSON-RPC 밖의 기능도 전부). 인증 basic admin/빈비번. 전체 페이지 목록: `d10_config/d10_web_pages.txt`.

## 접근 패턴
- **설정/액션**: `POST http://192.168.100.1/config/<핸들러>` + form data
- **running-config 다운로드**: `POST /config/icfg_conf_download` `file_name=running-config` → 텍스트 config (검증됨)
- 페이지 소스: `/navbar.htm`(메뉴 227페이지), `/lib/json.js`(95KB), `/lib/dynforms.js`

## 진단 (사용자 지적 — ping/traceroute 다 됨)
| 기능 | 페이지 | POST 핸들러 | 파라미터 |
|---|---|---|---|
| **Ping IPv4** | ping4.htm | `/config/ping4` | ip_addr, count, length, ttlvalue, src_vid, src_portno |
| Ping IPv6 | ping6.htm | `/config/ping6` | 〃 |
| **Traceroute** | traceroute4/6.htm | `/config/traceroute4` | ip_addr, ... |
| **VeriPHY(케이블진단)** | veriphy.htm | JSON-RPC `port.control.veriphy.start.set`+`port.status.veriphy.result.get` | 페어 A/B/C/D 상태·길이 |
| CPU 부하 | perf_cpuload.htm | `/stat/perf_cpuload` | |

## TSN (AFDX/A2Z 핵심)
| 기능 | 페이지 |
|---|---|
| FRER 제어/상태/통계 | frer_ctrl / frer_status / frer_statistics.htm |
| TAS(802.1Qbv) | tsn_port_tas_config / _max_sdu / _status.htm |
| Frame Preemption(802.1Qbu) | tsn_port_fp_config / _status.htm |
| PSFP(802.1Qci) 흐름미터/필터/게이트 | tsn_psfp_fmi_config / sfi_config / sgi_config (+ _status/_statistics).htm |
| VCL 스트림 | vcl_stream_ctrl / vcl_port_stream_config.htm |
| PTP | ptp_config / ptp.htm / ptp_as_statistics.htm |

## 이중화 프로토콜 (A2Z 관련!)
- **FRER**(frer_*) — 스트림 복제/제거
- **ERPS**(erps_ctrl/status) — 이더넷 링 보호(G.8032)
- **IEC-MRP**(iec_mrp_ctrl/status) — Media Redundancy Protocol(링)
- **APS**(aps_config/status) — 선형 보호절체
- **MSTP**(mstp_*) — 스패닝트리
→ A2Z 삼각형에서 FRER 외에 **ERPS/MRP 링 보호**도 선택지.

## 설정관리
- icfg_conf_download / upload / save / activate / delete.htm — **config 백업/복원/저장**
- factory.htm(공장초기화), wreset.htm(웜리셋), upload.htm(펌웨어)

## 기타 대분류 (227페이지 요약)
- L2: vlan_*, mac*, mstp_*, gvrp/mvrp, loop, aggr/lacp, mirror
- L3/IP: ip_config, ip_status, ip_routing_info_base, dhcp_*, arp_inspection
- QoS: qos_port_*(classification/policers/schedulers/shapers/tag_remarking), qos_queue_policers, wred, dscp_*
- 보안: acl_*, psec_*, nas(802.1X), auth_radius/tacacs, ip_source_guard, ssh/https
- 모니터: rmon_*, sflow, lldp_*, stat_ports/detailed, syslog, snmp/snmpv3_*
- 진단/시스템: sys, sysinfo, ntp, thermal_protect, fan, ddmi(SFP), sys_led

전체 목록: `d10_config/d10_web_pages.txt` (227). 각 페이지명 = `/config/<페이지>` POST 핸들러(대부분).
