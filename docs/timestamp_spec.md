# KFDX FPGA 내부 타임스탬프 명세 초안 (HW/RTL팀 전달용)

**목적**: 현재 PC HW 타임스탬프로 잰 지터(NIC 수신점 집계 240 ns)를 FPGA **파이프라인 단계별로 분리**한다. 그래야 "어느 단계(스케줄러/MAC)에서 지터가 생기는가"를 특정(fault localization)하고, ARINC664 요구 지터를 내부에서 직접 검증할 수 있다.

근거: `docs/fpga_structure.md`(레지스터 블록맵·클록), `docs/measurement_series.md`(240 ns 양자 = 300MHz/72), 측정으로 확정한 결정론적 2레벨 페이싱.

---

## 1. 무엇을 추가하나 — 타임스탬프 2점
| 이름 | 위치 | 정의 | 잡히는 지터 |
|---|---|---|---|
| **Timestamp A** | USER 블록, VL 스케줄러 | VL이 프레임을 "송출 가능"으로 release한 순간 | 스케줄러 지터(BAG 페이싱 정확도) |
| **Timestamp B** | AFDX MAC | 프레임 첫 바이트(SFD) 송출 순간 | MAC 큐잉·직렬화 지터 |

- **A→B 지연** = 내부 파이프라인 지연(release가 실제 송출로 가기까지). 이 지연의 변동 = 내부 지터.
- 현재 PC 관측(240 ns) = (B − PHY − 케이블 − NIC RX) 의 합. A/B가 있으면 **B의 지터 = 순수 MAC**, **A의 지터 = 순수 스케줄러**로 분리.

## 2. 카운터 사양
- **소스 클록**: 인터페이스 클록 **299.97 MHz**(period 3.335 ns). 페이싱 tick은 그 72분주(240 ns)지만, 타임스탬프는 **원 클록(3.335 ns) 분해능**으로 latch할 것 — 240 ns 이하 지터를 봐야 하므로.
- **폭**: free-running **48-bit** 권장. 48-bit @ 300 MHz ≈ 10.6 일 wrap → 측정 세션 내 wrap 무시 가능. 최소 32-bit(≈14.3 s wrap)면 프레임 간격 측정엔 충분.
- **리셋**: reset_all 시 0. wrap 처리를 위해 드라이버가 64-bit로 확장 누적.

## 3. 프레임별 캡처·저장
- 각 송신 프레임에 대해 A, B를 latch → **프레임 메타데이터**로 보관.
- 저장 방식 (택1, RTL 부담 순):
  1. **TS FIFO** (권장): `{seq_no, vlid, ts_A[48], ts_B[48]}` 엔트리를 USER 블록 FIFO에 push. 드라이버가 폴링/IRQ로 드레인. 프레임 데이터패스 무변경.
  2. CDMA 디스크립터 확장: TX 완료 디스크립터에 ts_A/ts_B 필드 추가(디스크립터 포맷 변경 필요).
- FIFO depth ≥ 256 (드레인 지연 흡수). overflow 카운터 노출.

## 4. 드라이버/SW 인터페이스
- **레지스터**(USER 블록 +0x80000 오프셋대, 미사용 영역):
  | 오프셋(예시) | 이름 | R/W | 설명 |
  |---|---|---|---|
  | +0x0400 | TS_CTRL | RW | bit0 enable, bit1 fifo_reset |
  | +0x0404 | TS_STATUS | R | bit0 fifo_empty, bit1 overflow, [15:8] level |
  | +0x0408 | TS_SEQ_VLID | R | pop: [7:0] vlid, [15:8] seq |
  | +0x040C | TS_A_LO / +0x0410 TS_A_HI | R | Timestamp A 48-bit |
  | +0x0414 | TS_B_LO / +0x0418 TS_B_HI | R | Timestamp B 48-bit (읽으면 FIFO advance) |
- **ioctl** (`/dev/kfdx`): `KFDX_TS_READ` → `struct {u8 vlid; u8 seq; u64 ts_a_ns; u64 ts_b_ns;}` 배치 반환. ns 변환은 드라이버(×3.335)나 SW.
- kfdx_app: `--ts_read --vlid=# --count=#` 서브커맨드로 노출.

## 5. 이걸로 가능해지는 측정
- **스케줄러 지터** = Var(A(n) − A(n−1) − BAG). 240 ns 2레벨이 스케줄러 것인지 확증.
- **MAC 지터** = Var(B − A). 직렬화 결정론성 검증.
- **내부 총지터** = B 기준. PC 측정(NIC RX)에서 케이블·NIC를 뺀 순수 FPGA 값.
- **다중 VL 경쟁**: 여러 VL이 동시에 release될 때 A는 같아도 B가 밀리는 양 = 멀티플렉싱 지터(직접 관측).

## 6. 검증 기준
- 단일 VL: A 간격 = BAG ± (관측된 240 ns 양자), B−A = 일정(프레임크기 함수).
- PC HW 타임스탬프(238 ns P2P)와 **B 기반 P2P가 일치**하면 A/B 경로 정합 확인.

## 7. RTL 부담 요약 (최소안)
- free-running 48-bit 카운터 1개(300 MHz).
- 스케줄러 release 스트로브에서 A latch, MAC SFD 스트로브에서 B latch.
- `{seq,vlid,A,B}` FIFO(depth 256) + AXI-Lite 레지스터 4~6개.
- 데이터패스(프레임 자체) 무변경 → 위험 낮음.
