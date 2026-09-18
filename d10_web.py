#!/usr/bin/env python3
"""D10 웹 REST 액션 도구 — JSON-RPC 밖의 기능(ping/traceroute/config save·download)을 웹 POST로.
검증된 흐름: POST /config/<action> → 302 ?ioIndex=X → GET /config/<action>?ioIndex=X 폴링.

  python3 d10_web.py ping 192.168.100.50 [count]
  python3 d10_web.py traceroute 192.168.100.50
  python3 d10_web.py download                 # running-config → stdout
  python3 d10_web.py save                      # running → startup (영구저장)
"""
import sys, time, urllib.request, urllib.parse, base64, re
D10 = __import__("os").environ.get("D10_HOST", "192.168.100.1")
AUTH = "Basic " + base64.b64encode(b"admin:").decode()

def req(method, path, data=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    r = urllib.request.Request(f"http://{D10}{path}", data=body,
        headers={"Authorization": AUTH, "Content-Type": "application/x-www-form-urlencoded"}, method=method)
    op = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
    try:
        with op.open(r, timeout=20) as x: return x.status, x.read().decode("latin1", "replace"), x.geturl()
    except urllib.error.HTTPError as e: return e.code, e.read().decode("latin1","replace"), path

def _diag(action, params):
    """ping/traceroute: POST → ioIndex → GET 폴링."""
    # POST (리다이렉트 막고 Location 추출)
    body = urllib.parse.urlencode(params).encode()
    r = urllib.request.Request(f"http://{D10}/config/{action}", data=body,
        headers={"Authorization": AUTH, "Content-Type": "application/x-www-form-urlencoded"})
    class NoRedir(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*a,**k): return None
    op = urllib.request.build_opener(NoRedir())
    idx = None
    try: op.open(r, timeout=20)
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location","")
        m = re.search(r"ioIndex=([0-9a-fx]+)", loc); idx = m.group(1) if m else None
    if not idx: return "(ioIndex 없음 — 실패)"
    out = ""
    for _ in range(20):
        s, txt, _ = req("GET", f"/config/{action}?ioIndex={idx}")
        clean = re.sub(r"<[^>]*>", "", txt)
        # JS 부분 제거, 실제 출력만
        for line in clean.splitlines():
            if re.search(r"PING|bytes from|packets? (transmit|received)|packet loss|min/avg|hop|\* \*|completed|traceroute", line, re.I):
                if line.strip() and line.strip() not in out: out += line.strip()+"\n"
        if re.search(r"complete|Error:", txt, re.I): break
        time.sleep(0.6)
    return out or "(출력 없음)"

def ping(ip, count=3):
    return _diag("ping4", {"ip_addr":ip,"count":count,"length":56,"pdata":0,"ttlvalue":64,"src_vid":"","src_portno":"","src_addr":""})
def traceroute(ip):
    return _diag("traceroute4", {"ip_addr":ip,"maxttl":10,"probes":1,"timeout":2,"dscp":0,"firstttl":1,"icmp":1,"numeric":1,"src_addr":"","src_vid":""})
def download():
    s,txt,_ = req("POST","/config/icfg_conf_download",{"file_name":"running-config","file_form":"","sid":1}); return txt
def save():
    s,txt,_ = req("POST","/config/icfg_conf_save",{"save":1}); return f"HTTP {s} (running→startup 저장)"

if __name__=="__main__":
    cmd = sys.argv[1] if len(sys.argv)>1 else "ping"
    if cmd=="ping": print(ping(sys.argv[2], sys.argv[3] if len(sys.argv)>3 else 3))
    elif cmd=="traceroute": print(traceroute(sys.argv[2]))
    elif cmd=="download": print(download())
    elif cmd=="save": print(save())
    else: print(__doc__)
