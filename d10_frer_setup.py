#!/usr/bin/env python3
"""D10에 AFDX A/B(Gi1/1·1/2)용 FRER recovery 구성 + 통계 관찰.
목적: R-TAG 없는 AFDX 프레임을 FRER가 어떻게 처리하는지 실측(호환성 경계).
스트림 10=ingress Gi1/1(A), 11=ingress Gi1/2(B), 둘 다 AFDX DMAC 매칭.
FRER recovery 인스턴스 3: member=10,11 → egress Gi1/3.
"""
import base64, json, urllib.request, time, sys
D10="192.168.100.1"; AUTH="Basic "+base64.b64encode(b"admin:").decode()
def rpc(method,params):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    r=urllib.request.Request(f"http://{D10}/json_rpc",data=body,
        headers={"Content-Type":"application/json","Authorization":AUTH})
    try:
        with urllib.request.urlopen(r,timeout=6) as x:
            d=json.loads(x.read()); return d.get("result"),d.get("error")
    except Exception as e: return None,{"message":str(e)}

AFDX_DMAC="03:00:00:00:00:01"   # VLID 1
def stream_conf():
    return {"MulticastDMac":"any","BroadcastDMac":"any",
        "destinationMacAddress":AFDX_DMAC,"destinationMacMask":"ff:ff:ff:ff:ff:ff",
        "sourceMacAddress":"00:00:00:00:00:00","sourceMacMask":"00:00:00:00:00:00",
        "outerTag":"any","outerTagIsSTag":"any","outerTagVidValue":0,"outerTagVidMask":0,
        "outerTagPcpValue":0,"outerTagPcpMask":0,"outerTagDei":"any",
        "innerTag":"any","innerTagIsSTag":"any","innerTagVidValue":0,"innerTagVidMask":0,
        "innerTagPcpValue":0,"innerTagPcpMask":0,"innerTagDei":"any","protocol":"ANY"}

def frer_conf(streams,egress):
    c={"Mode":"recovery","FrerVlan":1,"EgressPorts":egress,"Algorithm":"vector",
       "HistoryLen":8,"ResetTimeoutMsec":100,"TakeNoSequence":True,"IndividualRecovery":True,
       "Terminate":True,"LaErrDetection":False,"LaErrDifference":100,"LaErrPeriodMsec":2000,
       "LaErrPaths":2,"LaErrResetPeriodMsec":30000,"AdminActive":True}
    for i in range(8): c["StreamId%d"%i]=streams[i] if i<len(streams) else 0
    return c

def step(desc,method,params):
    r,e=rpc(method,params); print(f"  {desc}: {'OK' if not e else 'ERR '+str(e.get('message'))[:60]}")
    return r,e

print("=== 스트림 10 (ingress Gi1/1=A) ===")
step("stream.add 10",'vcl.config.stream.add',[10,stream_conf()])
step("stream.set 10",'vcl.config.stream.set',[10,stream_conf()])
step("attach 10→Gi1/1",'vcl.config.interface.stream.add',["Gi 1/1",10])
print("=== 스트림 11 (ingress Gi1/2=B) ===")
step("stream.add 11",'vcl.config.stream.add',[11,stream_conf()])
step("stream.set 11",'vcl.config.stream.set',[11,stream_conf()])
step("attach 11→Gi1/2",'vcl.config.interface.stream.add',["Gi 1/2",11])
print("=== FRER recovery 인스턴스 3 (member 10,11 → egress Gi1/3) ===")
step("frer.add 3",'frer.config.add',[3,frer_conf([10,11],["Gi 1/3"])])
step("frer.set 3",'frer.config.set',[3,frer_conf([10,11],["Gi 1/3"])])
time.sleep(2)
print("=== 상태/통계 (트래픽 흐르는 중) ===")
st,_=rpc("frer.status.get",[3]); print("status:",json.dumps(st)[:200] if st else st)
for _ in range(3):
    time.sleep(2)
    stat,e=rpc("frer.statistics.get",[3,"Gi 1/3",0])
    print("stats:",json.dumps(stat) if stat else e)
