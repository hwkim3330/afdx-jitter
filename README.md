# afdx-jitter

FPGA(KETI KFDX / Xilinx) 기반 AFDX Virtual Link 송신 **지터 측정 · 이상 검출** 도구.
호스트는 NXP T2080RDB 보드, AFDX NIC은 PCIe FPGA(KFDX). 자세한 보드/명령 레퍼런스는
[`docs/board_kfdx.md`](docs/board_kfdx.md).

## 구성
| 경로 | 내용 |
|---|---|
| `serial_bridge.py` | 웹 시리얼 터미널 브리지 (pyserial ↔ WebSocket ↔ HTTP) |
| `web/` | 브라우저 터미널 (xterm.js, 오프라인 동작) |
| `docs/board_kfdx.md` | KFDX AFDX NIC 하드웨어 · 명령 레퍼런스 |
| `board/` | 보드 `/mnt/flash` 원본 스크립트 백업 |
| `capture_jitter.py` | 실측 지터 캡처/분석(외부 ΔTtx, PNG 출력) |

## 웹 터미널 실행
```bash
python3 serial_bridge.py --dev /dev/ttyUSB0 --baud 115200
# → http://localhost:8777
```

## 로드맵 (과제 기준)
1. [x] 보드 콘솔 접속 + 웹 터미널
2. [x] KFDX AFDX NIC 정체 · 명령셋 파악 (VL/BAG/Lmax/Jitter 존재 확인)
3. [x] KFDX Max Jitter = **AFDX 스펙 상한**(측정 아님) 확정 → docs/jitter_analysis.md
4. [x] **실측 지터** 캡처 파이프라인(외부 ΔTtx) 동작 → capture_jitter.py, docs/capture_method.md
5. [~] 시각화: 웹 GUI(카운터/예산) + 캡처 PNG(ΔT/지터). 정밀 실측은 HW타임스탬프 NIC 필요
