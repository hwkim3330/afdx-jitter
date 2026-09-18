# Kontron D10 (WebStaX) 설정 백업

- `d10_config_snapshot.json` — JSON-RPC로 뽑은 핵심 설정 스냅샷 (2026-09-18)
  - `port_status` 8포트, `frer` 인스턴스, `mirror_session1`, `vcl_stream`
- WebStaX는 전체 running-config 텍스트를 JSON-RPC로 안 열어줌(웹UI System>Configuration>Download 또는 콘솔 CLI `show running-config` 필요). 이 스냅샷이 API로 가능한 최대 백업.

## 접속
- mgmt: `http://192.168.100.1/json_rpc` (admin / 빈 비번), PC는 D10 Gi1/6 in-band, enp4s0=192.168.100.50/24
- 프록시: `python3 d10_proxy.py` → http://localhost:8099/

## FRER 재구성 (스냅샷 참고)
`d10_frer_setup.py` 로 AFDX A/B(Gi1/1·1/2)용 recovery 인스턴스+스트림 생성.
개별 설정은 JSON-RPC `frer.config.set`/`vcl.config.stream.set` 로 스냅샷 값 주입.

## ⚠ 주의
- 미러 목적지를 관리포트(Gi1/6=PC)로 걸지 말 것 → 관리 끊김(파워사이클만 복구).
