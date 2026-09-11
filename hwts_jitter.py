#!/usr/bin/env python3
"""KFDX AFDX 송신 지터 정밀 측정 — NIC 하드웨어 RX 타임스탬프 (필터 강제 ALL).

어제의 발견: tcpdump -j adapter_unsynced 는 RX 타임스탬프 필터를 PTP(1588) 전용으로
두어 비-PTP AFDX 프레임에 타임스탬프가 안 찍혔다(간격 난장판). igc 는 rx-filter 'all'
을 지원하므로, SIOCSHWTSTAMP 로 HWTSTAMP_FILTER_ALL 을 강제하고 raw AF_PACKET 소켓의
SO_TIMESTAMPING(raw hardware) 으로 받으면 PC 커널/C-state 노이즈가 통째로 제거된
FPGA 송신 지터(≤수백 ns)를 직접 측정할 수 있다.

사용: sudo python3 hwts_jitter.py --iface enp4s0 --vlid 1 --bag-us 2000 --dur 8 --out results/hwts.json
(프레임 송신은 외부에서 kfdx_app --send 로 동시에 흘려야 함)
"""
import socket, struct, ctypes, fcntl, time, json, argparse, statistics as st

SIOCSHWTSTAMP=0x89b0; ETH_P_ALL=3; SO_TIMESTAMPING=37; SCM_TIMESTAMPING=37
HWTSTAMP_FILTER_ALL=1
# SOF_TIMESTAMPING: RX_HARDWARE(1<<2)|SOFTWARE(1<<4)|RAW_HARDWARE(1<<6)
SOF=4|16|64

class hwtstamp_config(ctypes.Structure):
    _fields_=[("flags",ctypes.c_int),("tx_type",ctypes.c_int),("rx_filter",ctypes.c_int)]
class ifreq(ctypes.Structure):
    _fields_=[("ifr_name",ctypes.c_char*16),("ifr_data",ctypes.c_void_p)]

def set_filter_all(iface):
    cfg=hwtstamp_config(0,0,HWTSTAMP_FILTER_ALL)
    ifr=ifreq(iface.encode(), ctypes.cast(ctypes.pointer(cfg),ctypes.c_void_p))
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try: fcntl.ioctl(s,SIOCSHWTSTAMP,ifr); ok=(cfg.rx_filter==HWTSTAMP_FILTER_ALL)
    finally: s.close()
    return ok

def capture(iface, vlid, dur):
    s=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(ETH_P_ALL))
    s.bind((iface,0)); s.setsockopt(socket.SOL_SOCKET,SO_TIMESTAMPING,SOF); s.settimeout(dur)
    hw=[]; sw=[]; t0=time.time()
    while time.time()-t0<dur:
        try: data,anc,_,_=s.recvmsg(2048,1024)
        except socket.timeout: break
        if len(data)<14 or data[0]!=0x03 or (vlid is not None and data[5]!=vlid): continue
        for lvl,typ,cd in anc:
            if lvl==socket.SOL_SOCKET and typ==SCM_TIMESTAMPING:
                v=struct.unpack("qqqqqq",cd[:48])
                if v[0]: sw.append(v[0]+v[1]*1e-9)
                if v[4]: hw.append(v[4]+v[5]*1e-9)
    s.close(); return hw, sw

def metrics(ts, bag_us):
    ts=sorted(ts)
    if len(ts)<10: return None
    d=[(ts[i]-ts[i-1])*1e6 for i in range(1,len(ts))]
    lo,hi=0.5*bag_us,1.5*bag_us
    inb=[x for x in d if lo<x<hi]
    if len(inb)<10: return dict(n=len(ts), inband=len(inb), note="표본부족")
    med=st.median(inb); mad=sorted(abs(x-med) for x in inb)[len(inb)//2]
    j=[x-bag_us for x in inb]  # 지터 = 간격 - BAG
    return dict(n=len(ts), inband=len(inb), mean_us=round(st.mean(inb),3),
                mad_std_us=round(1.4826*mad,4), rms_us=round((sum(x*x for x in j)/len(j))**0.5,4),
                min_us=round(min(inb),3), max_us=round(max(inb),3),
                pp_us=round(max(inb)-min(inb),3), neg=sum(1 for x in d if x<0))

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--iface",default="enp4s0"); ap.add_argument("--vlid",type=int,default=1)
    ap.add_argument("--bag-us",type=float,default=2000); ap.add_argument("--dur",type=float,default=8)
    ap.add_argument("--out",default=None)
    a=ap.parse_args()
    if not set_filter_all(a.iface): print("경고: rx-filter ALL 설정 실패(권한/드라이버)")
    hw,sw=capture(a.iface,a.vlid,a.dur)
    r=dict(iface=a.iface,vlid=a.vlid,bag_us=a.bag_us,ts=round(time.time()),
           hw=metrics(hw,a.bag_us), sw=metrics(sw,a.bag_us))
    print(json.dumps(r,ensure_ascii=False,indent=2))
    if a.out:
        json.dump(r,open(a.out,"w"),ensure_ascii=False,indent=2); print("saved",a.out)
