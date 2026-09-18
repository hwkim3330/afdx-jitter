#!/usr/bin/env python3
"""D10(Kontron WebStaX) JSON-RPC 프록시 + FRER/AFDX 비교 대시보드 서버.

토폴로지: PC enp4s0(192.168.100.50) ── D10 mgmt(192.168.100.1)
          D10 Gi1/1 ── AFDX eth0 (A망),  Gi1/2 ── AFDX eth1 (B망)

- GET  /            → web/frer.html
- GET  /snapshot    → 포트 상태+RMON 카운터(A/B)+FRER config/status/stats 를 한 번에
- POST /rpc         → D10 json_rpc 로 그대로 포워드(설정 액션용)
- 그 외             → web/ 정적 파일

사용: python3 d10_proxy.py   (기본 8099)
"""
import base64, json, os, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

D10   = os.environ.get("D10_HOST", "192.168.100.1")
USER  = os.environ.get("D10_USER", "admin")
PASS  = os.environ.get("D10_PASS", "")
PORT  = int(os.environ.get("PORT", "8099"))
WEB   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
AUTH  = "Basic " + base64.b64encode(f"{USER}:{PASS}".encode()).decode()
# A/B = AFDX eth0/eth1 이 물린 D10 포트
PORT_A = os.environ.get("D10_PORT_A", "Gi 1/1")
PORT_B = os.environ.get("D10_PORT_B", "Gi 1/2")

def rpc(method, params=None):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": params if params is not None else []}).encode()
    req = urllib.request.Request(f"http://{D10}/json_rpc", data=body,
                                 headers={"Content-Type": "application/json", "Authorization": AUTH})
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            d = json.loads(r.read().decode())
            return d.get("result"), d.get("error")
    except Exception as e:
        return None, {"message": str(e)}

def snapshot():
    out = {"ts": __import__("time").time(), "port_a": PORT_A, "port_b": PORT_B}
    st, _ = rpc("port.status.get")
    out["ports"] = st or []
    ra, ea = rpc("port.statistics.rmon.get", [PORT_A])
    rb, eb = rpc("port.statistics.rmon.get", [PORT_B])
    out["rmon_a"], out["rmon_b"] = ra, rb
    # FRER 인스턴스 1..8 스캔
    frer = []
    for i in range(1, 9):
        cfg, ce = rpc("frer.config.get", [i])
        if not cfg:
            continue
        stt, _ = rpc("frer.status.get", [i])
        entry = {"id": i, "config": cfg, "status": stt}
        frer.append(entry)
    out["frer"] = frer
    return out

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html", "/frer"): path = "/frer.html"
        if path == "/snapshot":
            self._send(200, json.dumps(snapshot())); return
        fp = os.path.normpath(os.path.join(WEB, path.lstrip("/")))
        if fp.startswith(WEB) and os.path.isfile(fp):
            ct = ("text/html" if fp.endswith(".html") else "application/javascript"
                  if fp.endswith(".js") else "text/css" if fp.endswith(".css")
                  else "application/json" if fp.endswith(".json") else "application/octet-stream")
            self._send(200, open(fp, "rb").read(), ct); return
        self._send(404, json.dumps({"error": "not found"}))
    def do_POST(self):
        if self.path.split("?")[0] != "/rpc":
            self._send(404, json.dumps({"error": "use /rpc"})); return
        n = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(n).decode())
            res, err = rpc(req.get("method"), req.get("params"))
            self._send(200, json.dumps({"result": res, "error": err}))
        except Exception as e:
            self._send(200, json.dumps({"result": None, "error": {"message": str(e)}}))

if __name__ == "__main__":
    print(f"[d10_proxy] http://0.0.0.0:{PORT}  → D10 {D10} (A={PORT_A} B={PORT_B})")
    r, e = rpc("port.status.get")
    print("[d10_proxy] D10 연결:", "OK" if r else f"실패 {e}")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
