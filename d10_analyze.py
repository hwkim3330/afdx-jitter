import json,urllib.request,base64
D10="192.168.100.1"; AUTH="Basic "+base64.b64encode(b"admin:").decode()
def rpc(m,p=None):
    b=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p or []}).encode()
    r=urllib.request.Request(f"http://{D10}/json_rpc",data=b,headers={"Content-Type":"application/json","Authorization":AUTH})
    try:
        with urllib.request.urlopen(r,timeout=6) as x:
            d=json.loads(x.read()); return d.get("result") if not d.get("error") else None
    except Exception: return None
A={}
# 1. 시스템/능력
A["capabilities"]={k:rpc(f"{k}.capabilities.get") for k in
    ["port","mac","vlan","qos","frer","psfp","tsn","ptp","mirror","cfm","mstp","lldp"]}
# 2. 포트 상태/설정
A["port_status"]=rpc("port.status.get")
ports=[e["key"] for e in (A["port_status"] or [])]
A["port_config"]={p:rpc("port.config.get",[p]) for p in ports}
# 3. VLAN
A["vlan_config"]=rpc("vlan.config.interface.get") or rpc("vlan.config.get")
# 4. FRER
A["frer"]={i:{"config":rpc("frer.config.get",[i]),"status":rpc("frer.status.get",[i])} for i in range(1,9) if rpc("frer.config.get",[i])}
# 5. PSFP (802.1Qci)
A["psfp_flowmeter"]=rpc("psfp.config.flowMeter.get") or rpc("psfp.config.flowmeter.get")
A["psfp_streamfilter"]=rpc("psfp.config.streamFilter.get")
A["psfp_streamgate"]=rpc("psfp.config.streamGate.get")
# 6. TAS (802.1Qbv, tsn)
A["tas_params"]={p:rpc("tsn.config.interface.tas.params.get",[p]) for p in ports[:2]}
# 7. QoS/CBS (queue shaper)
A["qos_queueshaper"]={p:rpc("qos.config.interface.queueShaper.get",[p]) for p in ports[:2]}
# 8. PTP
A["ptp_clocks"]=rpc("ptp.status.clock.default.get",[0]) or rpc("ptp.config.clock.default.get",[0])
# 9. VCL 스트림
A["vcl_streams"]={i:rpc("vcl.config.stream.get",[i]) for i in range(1,12) if isinstance(rpc("vcl.config.stream.get",[i]),dict)}
# 10. 미러
A["mirror"]=rpc("mirror.config.session.get",[1])
# 11. MAC 테이블/LLDP/STP
A["lldp_neighbors"]=rpc("lldp.status.neighbors.get")
A["mstp"]=rpc("mstp.status.bridge.get") or rpc("mstp.config.bridge.get")
json.dump(A,open("d10_config/d10_full_analysis.json","w"),ensure_ascii=False,indent=1)
# 요약 출력
def has(x): return "있음" if x else "없음/미설정"
print("=== D10 분석 요약 ===")
print("포트:",len(ports),ports)
print("capabilities 응답:",{k:has(v) for k,v in A["capabilities"].items()})
print("FRER 인스턴스:",list(A["frer"].keys()))
print("VCL 스트림:",list(A["vcl_streams"].keys()))
print("PSFP flowmeter:",has(A["psfp_flowmeter"]),"streamfilter:",has(A["psfp_streamfilter"]),"streamgate:",has(A["psfp_streamgate"]))
print("PTP clock:",has(A["ptp_clocks"]))
print("LLDP 이웃:",len(A["lldp_neighbors"]) if A["lldp_neighbors"] else 0)
print("미러 Mode:",(A["mirror"] or {}).get("Mode"))
