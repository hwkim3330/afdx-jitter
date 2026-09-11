#!/usr/bin/env python3
"""phc2sys 파싱 → web/ptp_data.json (브리지 8777이 정적 서빙). SUDO_PASS=1 필요."""
import json, os, re, subprocess, time
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"web","ptp_data.json")
LINE=re.compile(r'offset\s+(-?\d+)\s+s(\d)\s+freq\s+([+-]?\d+)(?:\s+delay\s+(-?\d+))?')
HIST=[]
pw=os.environ.get("SUDO_PASS")
p=subprocess.Popen(["sudo","-S","phc2sys","-s","CLOCK_REALTIME","-c","enp4s0","-O","0","-m"],
                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                   bufsize=1, universal_newlines=True)
if pw:
    try: p.stdin.write(pw+"\n"); p.stdin.flush()
    except Exception: pass
for line in p.stdout:
    m=LINE.search(line)
    if m:
        HIST.append(dict(t=round(time.time(),3), offset_ns=int(m.group(1)), state=int(m.group(2)),
                         freq_ppb=int(m.group(3)), delay_ns=int(m.group(4) or 0)))
        if len(HIST)>400: HIST.pop(0)
        tmp=OUT+".tmp"
        with open(tmp,"w") as f: json.dump(HIST[-300:], f)
        os.replace(tmp, OUT)
