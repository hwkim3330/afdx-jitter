# KFDX "Jitter" 구현 추적 결과 (read-only 분석)

대상: `/mnt/flash/kfdx.ko` (v1.0.20211209-1, ppc64, GCC 4.9.2 -O2), `/mnt/flash/kfdx_app` (50KB),
FPGA HW 2025.7.30 A1.2, Vendor 7014h. 소스/헤더는 파일시스템 어디에도 없음(바이너리만).

## 핵심 결론
KFDX의 **`Max Jitter`(get_head)는 측정값이 아니라, 설정된 VL 집합으로부터 SW가 계산한
AFDX 최대 기술지터 "예산/한계"(spec bound)** 이다. 과제가 원하는
`Ttx(실제 MAC 송출) − Tref(내부 송신기준)` **per-frame 실측 지터는 현재 펌웨어에 구현/노출되어 있지 않다.**

## 근거
1. **트래픽·BAG·carrier 무관, VL 설정에만 반응**
   - BAG 1/10/100/1000, 송신 유무와 무관하게 값 고정.
   - carrier=0(링크 없음)에서도 값 나옴 → 측정이 아님.
2. **바이너리 구조**: `Max Jitter`는 `VL Head` 구조체 필드(개수 통계 Total/Tx/Rx/Bi 옆),
   `print_vl_head_cfg()`가 출력. add/set 옵션에 jitter 파라미터 없음.
3. **계산식 실증(리버서블 재설정)**: VL1의 Lmax만 바꿔 관측
   | VL1 Lmax | Max Jitter |
   |---|---|
   | 1518 | 37440 ns |
   | 512  | 29392 ns |
   - 관측 델타 (1518→512) = **8048 ns**, 이론 `(1518-512)×8bit / 1e9 = 8048 ns` → **정확히 일치**.
   - 확정 공식: **`Max Jitter = Σ_over_VLs (Lmax_i + 20) × 8 / R`,  R = 1 Gbps, 단위 ns.**
     `20` = AFDX 프레임 오버헤드(IFG 12 + preamble/SFD 8 byte). 즉 모든 VL의 최대프레임이
     back-to-back 직렬화되는 최악 지연 = AFDX 기술지터 상한.
4. **전체 함수맵(/proc/kallsyms [kfdx])에 TX 타임스탬프 diff 함수 없음**:
   TX=build_vl_pkt/kfdx_transmit_pkt/tx_task/cdma_start_tx_wait,
   PTP=kfdx_ptp_*/handleDelayResp/updateClock/kalman/fromInternalTime(=클록 동기 전용).
   `sof/mac_tx/scheduler_release/expected/actual/deadline` 같은 심볼은 kfdx에 없음.
5. **PTP 하드웨어 타임스탬프는 존재하지만 용도가 다름**: `add_timestamp`, `so_timestamping`,
   `t3 (hw): %ld.%09ld`(ns), `kfdx_timestamp_compare`, syncSend/Recieve(t1/t2), delayReq/Resp →
   전부 **1588 슬레이브 클록 동기**(offset-from-master, Kalman 필터)용. 데이터 VL 프레임의
   송출 시각을 per-frame 기록·비교하지 않음.

## A~H 답
- **A. Jitter 정의**: (현재 값) AFDX 최대 기술지터 상한 = 구성 VL들의 최대프레임 직렬화시간 합.
  (과제가 원하는) 실측 송신지터 `Ttx−Tref`는 **미구현**.
- **B. Timestamp A (내부 송신기준)**: **없음.** scheduler release/BAG expiry 시각을 기록하는 지점 부재.
- **C. Timestamp B (실제 MAC TX)**: **데이터 프레임엔 없음.** HW 타임스탬프는 PTP 메시지(t1/t3)에만.
- **D. 계산식**: `Max Jitter = Σ (Lmax_i + 20)·8 / 1e9` [ns] (SW 계산, 측정 아님).
- **E. 관련 register 주소**: 해당 값은 **RTL 레지스터가 아니라 드라이버 SW 계산**(VL Head 구조체).
  BAR0=0x…88d00000, USER=…88d80000, INTC=…88d20000, CDMA=…88d30000 (probe 로그).
  cdma_read_reg/cdma_write_reg 로 FPGA 접근하나, jitter 전용 레지스터는 확인 안 됨.
- **F. 단위**: **나노초(ns)**. (BAG는 별개로 ×10µs 단위: bag=1000 → 10ms.)
- **G. carrier 필요 여부**: **불필요** (스펙 계산값이므로). 단 이는 "측정이 아니라서" 무관한 것.
- **H. 현재 장비 실측 명령**: **없음.** `--get_head`는 스펙 상한만 출력.
  실측하려면 (1) PC raw 캡처로 출력 프레임 간격 ΔTtx(외부 지터, 링크 필요),
  (2) FPGA RTL/드라이버에 Timestamp A(release)+B(MAC TX) 기록 추가(펌웨어 작업),
  (3) PTP hwts 경로를 데이터 프레임까지 확장 — 중 하나가 필요.

## 시사점
- 대시보드에서 `Max Jitter`를 "측정 지터"로 표기하면 오해. **"AFDX 지터 예산(스펙)"** 으로 표기해야 함.
- 실시간 실측 지터는 과제의 개발 대상(미구현). 가장 빠른 경로는 (H-1) PC 캡처 ΔTtx.
