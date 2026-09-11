#!/usr/bin/env python3
"""
이상 검출 오프라인 유닛테스트 — 합성 프레임 시퀀스로 detect_anomalies 를 엄격 검증.
보드/배선 불필요. 다양한 고장 + 경계케이스로 검출기 강건성 확인.
  python3 test_detection.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from capture_jitter import detect_anomalies

BAG=2000.0  # us

def frames(sns, dts=None, lens=None):
    """sns: 시퀀스번호 리스트. dts: 각 프레임 직전 간격(us, 첫프레임은 무시). lens: 길이."""
    n=len(sns); dts=dts or [BAG]*n; lens=lens or [60]*n
    t=0.0; out=[]
    for i in range(n):
        if i>0: t+=dts[i]/1e6
        out.append((t, sns[i]&0xFF, lens[i]))
    return out

def run(name, fr, lmax, expect_verdict, expect_flags):
    """expect_flags: {'seq_loss':>0, ...} 형태로 검증할 필드 조건."""
    r=detect_anomalies(fr, BAG, 2.0, 1.35, lmax)  # rob_std/mad 임의(판정엔 무관)
    ok = r['verdict']==expect_verdict
    detail=""
    for k,cond in expect_flags.items():
        v=r.get(k,0)
        good = (v>0) if cond=='>0' else (v==0) if cond=='==0' else (v==cond)
        ok = ok and good
        detail+=f" {k}={v}"
    print(f"  {'✅' if ok else '❌'} {name}: 판정 {r['verdict']}(기대 {expect_verdict}){detail}")
    return ok

def main():
    print("=== 이상 검출 유닛테스트 (합성 프레임) ===")
    R=[]
    # U0 정상: SN 연속, 간격=BAG
    R.append(run("U0 정상", frames(list(range(1,51))), 1518, 'NORMAL',
                 {'seq_loss':'==0','seq_dup':'==0','rate_violation':'==0','lmax_violation':'==0'}))
    # U1 손실: SN 5개 중 1개 빠짐(gap) + 시간갭도 2×BAG
    sns=list(range(1,26)); del sns[12]  # SN 13 빠짐
    dts=[BAG]*len(sns); dts[12]=2*BAG   # 손실지점 간격 2×BAG
    R.append(run("U1 손실", frames(sns,dts), 1518, 'FAULT', {'seq_loss':'>0'}))
    # U2 중복: 같은 SN 두번
    sns=[1,2,3,3,4,5,6,7,8,9,10]; dts=[BAG]*11; dts[3]=5  # 중복은 거의 동시
    R.append(run("U2 중복", frames(sns,dts), 1518, 'FAULT', {'seq_dup':'>0'}))
    # U3 재정렬: SN 큰 감소(순환거리>64)
    sns=[1,2,3,80,4,5,6,7,8]  # 3->80 큰점프(재정렬/이상)
    R.append(run("U3 재정렬", frames(sns), 1518, 'FAULT', {'seq_reorder':'>0'}))
    # U4 Lmax 초과: 프레임 하나 1500B, 정책 512
    lens=[60]*20; lens[10]=1500
    R.append(run("U4 Lmax초과", frames(list(range(1,21)),lens=lens), 512, 'FAULT', {'lmax_violation':'>0'}))
    # U5 Rate 위반: 지속적으로 0.5×BAG(1ms) 간격 = 2배속 송신
    sns=list(range(1,31)); dts=[BAG/2]*30
    R.append(run("U5 Rate위반", frames(sns,dts), 1518, 'WARNING', {'rate_violation':'>0'}))
    # U6 다중 동시고장: 손실 + Lmax
    sns=list(range(1,21)); del sns[10]; dts=[BAG]*len(sns); dts[10]=2*BAG
    lens=[60]*len(sns); lens[5]=1500
    R.append(run("U6 다중동시(손실+Lmax)", frames(sns,dts,lens), 512, 'FAULT',
                 {'seq_loss':'>0','lmax_violation':'>0'}))
    # --- 경계 케이스 (오탐 없어야) ---
    print("  --- 경계(오탐 없어야) ---")
    # E1 SN wrap 255→1 (0 예약): 정상, 손실/재정렬 아님
    sns=[253,254,255,1,2,3,4]
    R.append(run("E1 SN wrap 255→1", frames(sns), 1518, 'NORMAL', {'seq_loss':'==0','seq_reorder':'==0'}))
    # E2 타임스탬프 쪼개짐: 한 간격이 1451+581(합≈2×BAG) — Rate 오탐 없어야
    sns=list(range(1,21)); dts=[BAG]*20; dts[10]=2900; dts[11]=1100  # 합4000=2×BAG(진짜 쪼개짐)
    R.append(run("E2 타임스탬프 쪼개짐", frames(sns,dts), 1518, 'NORMAL', {'rate_violation':'==0'}))
    # E3 송신 경계(큰 시간갭이지만 SN 연속): 손실 오탐 없어야
    sns=list(range(1,21)); dts=[BAG]*20; dts[10]=300000  # 0.3s RPC 갭, SN은 연속
    R.append(run("E3 송신경계(SN연속)", frames(sns,dts), 1518, 'NORMAL', {'seq_loss':'==0'}))
    print(f"\n=== {sum(R)}/{len(R)} PASS ===")
    import json; json.dump({"pass":sum(R),"total":len(R)}, open("results/detection_unittest.json","w"))
    return 0 if all(R) else 1

if __name__=="__main__": sys.exit(main())
