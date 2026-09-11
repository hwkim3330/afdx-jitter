# KFDX AFDX 툴 — 버그 추적 (순차 정리, 2026-09-11)

상태: ✅ 수정됨 · 🔧 우회 · ⛔ 안전상 회피 · 🔬 구조적 한계(버그 아님) · ⏳ 미해결(수정버전 확인)
분류: [HW]=펌웨어/드라이버/앱 · [측정]=측정계 · [검출]=이상검출기 · [도구]=툴/인프라

| # | 분류 | 증상 | 원인 | 상태 | 조치 |
|---|---|---|---|---|---|
| B01 | [HW] | `--link_down` 시 드라이버가 uninterruptible D-state로 hung, 콘솔 전체 블록 | 드라이버 링크상태 전이 처리 결함 | ⛔ | **절대 사용 금지**. 복구=물리 파워사이클. 진단은 read-only(`--status/--get*/--read_reg/phy`)만 |
| B02 | [HW] | `--send --count=N` 이 N과 무관하게 한 버퍼분만 송신 | tx_buf 단발 | 🔧 | 반복 송신 루프(측정 스크립트가 back-to-back `--send`) |
| B03 | [HW] | `--read_phy0/1 --addr=#` 가 addr 인자 무시 | 앱 인자 파싱 | 🔧 | 우회 불필요(진단용, 고정 addr 읽힘) |
| B04 | [HW] | TX 인터럽트가 특정 값(PHY-A retry 14302 등)에서 정지 → 송신 멈춤 | TX 인터럽트 처리 결함(추정) | ⏳ | 리부트 후 발현. 복구=`rmmod→insmod→VL 재등록→PHY UP 대기`. **수정버전에서 해결 여부 확인 필요** |
| B05 | [측정] | HW 타임스탬프 간격이 14ms·348ms로 garbage | tcpdump `-j adapter_unsynced` 가 RX 필터를 **PTP(1588) 전용**으로 둠 → 비-PTP AFDX 프레임 미타임스탬프 | ✅ | raw 소켓 + `SIOCSHWTSTAMP(rx_filter=ALL)` 강제 (`hwts_jitter.py`). **참지터 110ns 달성** |
| B06 | [측정] | 지터가 재측정마다 3.8~140µs로 요동 | PC C-state 웨이크업 + governor + 코어 경합 | ✅ | `measure_setup.sh` 격리(performance/IRQ 코어고정/`cpu_dma_latency=0`) → SW 1.4µs, HW로 완전제거 |
| B07 | [측정] | 평균 간격이 BAG보다 항상 +ppm 초과 | FPGA↔PC 독립 크리스탈 ~10.4ppm | 🔬 | **버그 아님**(AFDX 비동기, 정상 공차). 참지터는 관측평균 기준으로 재서 분리(`rms_corr`), HW 보정 불필요 |
| B08 | [검출] | 시퀀스 손실 검출 맹점 — 송신경계 SN을 손실로 오판 | 시간게이트 오분류 | ✅ | 시간게이트 제거(SN은 송신경계에서도 연속) |
| B09 | [검출] | Rate 위반 오탐 — 타임스탬프 분할(1451+581≈2×BAG) | 단일 짧은간격만 보고 판정 | ✅ | 이웃 쌍합 검사(`dt+prev_dt<1.5×BAG`)로 면역 |
| B10 | [검출] | 전 VL 혼합 캡처 시 손실 29916건 오탐 | dst[5](VLID) 필터 누락 | ✅ | `b[0]==0x03 and b[5]==vlid` 필터 |
| B11 | [검출] | 단위테스트 E2(Rate) 기대값 오류 | 분할 합을 2×BAG이 아닌 1×BAG로 기대 | ✅ | 테스트 버그(검출기 정상), 기대값 수정 → 10/10 |
| B12 | [도구] | ptp_web.py 포트 충돌(8090/91/92/9099 Address in use) | 별도 HTTP 서버 중복 | ✅ | `phc_logger.py`(phc2sys 파싱→JSON) + 브리지 정적서빙으로 대체 |
| B13 | [도구] | `pkill -f <pat>` 가 자기 셸까지 죽임(exit 144) | 패턴 자기참조 | ✅ | 명시적 PID 타깃 |
| B14 | [HW] | FPGA 내부 단계별 지터(Timestamp A=scheduler, B=MAC TX) 분리 불가 | 내부 타임스탬프 미노출 | 🔬 | **구조적 한계**(버그 아님). fault localization "어느 파이프라인 단계"는 RTL 추가 필요 → NEXT_ACTION E |
| B15 | [HW] | `/proc/kfdx` 를 read 하면 커널 `Bad page map`(page fault, 프로세스 taint) | proc 핸들러가 잘못된 페이지 매핑 노출 | ⏳ | **읽지 말 것**(진단은 dmesg/kfdx_app 로). 수정버전 확인 대상 |
| B16 | [HW] | **미설정 VL을 `--get`하면 커널 paging request 오류로 보드 hang** (예: 설정 안 된 vlid=6) | 드라이버가 미할당 VL 슬롯을 검증 없이 역참조 | ⛔ | **설정된 VL만 `--get`**. 복구=물리 파워사이클. B01·B15와 동일 계열(미검증 접근→커널 fault) |

## 수정버전 도착 시 재확인 우선순위
1. **B04** (TX 인터럽트 정지) — 데모 안정성 직결. 수정됐는지 최우선 확인.
2. **B01** (link_down hung) — 수정됐으면 안전 제약 완화 가능.
3. **B02/B03** (send count·phy addr) — 편의성.
4. baseline 버전 대조표는 `PROBLEMS.md` 참조 (kfdx.ko 1.0.20211209-1 기준).
