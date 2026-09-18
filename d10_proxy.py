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

def _u16(b, o): return (b[o] << 8) | b[o+1]
def decode_afdx(b):
    """AFDX 프레임 바이트 → 와이어샤크급 필드."""
    d = {"len": len(b), "hex": b.hex()}
    d["eth"] = {"dst": ':'.join(f'{x:02x}' for x in b[0:6]),
                "src": ':'.join(f'{x:02x}' for x in b[6:12]),
                "type": f'0x{_u16(b,12):04x}',
                "vlid": b[5] if b[0] == 0x03 else None}
    et = _u16(b, 12)
    if et == 0x0800 and len(b) >= 34:
        ip = b[14:]; ihl = (ip[0] & 0xf) * 4
        d["ip"] = {"src": '.'.join(str(x) for x in ip[12:16]),
                   "dst": '.'.join(str(x) for x in ip[16:20]),
                   "proto": ip[9], "total_len": _u16(ip, 2), "ttl": ip[8]}
        if ip[9] == 17 and len(ip) >= ihl + 8:
            u = ip[ihl:]
            d["udp"] = {"sport": _u16(u, 0), "dport": _u16(u, 2), "len": _u16(u, 4)}
    d["afdx"] = {"sn": b[-1]}  # AFDX 시퀀스번호 = 마지막 바이트
    return d

def _parse_pcap(raw):
    if len(raw) < 24: return []
    import struct
    magic = raw[:4]
    le = magic in (b'\xd4\xc3\xb2\xa1', b'\x4d\x3c\xb2\xa1')
    end = '<' if le else '>'
    off = 24; pkts = []
    while off + 16 <= len(raw):
        _, _, incl, _ = struct.unpack(end + 'IIII', raw[off:off+16])
        off += 16
        if off + incl > len(raw): break
        pkts.append(raw[off:off+incl]); off += incl
    return pkts

def capture_afdx(iface, dur=2.0, maxf=24):
    import subprocess, tempfile, os as _os
    f = tempfile.mktemp(suffix='.pcap')
    try:
        subprocess.run(['tcpdump', '-i', iface, '-c', str(maxf), '-w', f,
                        '--time-stamp-precision=micro', 'ether[0:2]=0x0300'],
                       timeout=dur + 1.5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    try:
        raw = open(f, 'rb').read()
    except Exception:
        return {"frames": [], "count": 0}
    finally:
        try: _os.unlink(f)
        except Exception: pass
    pk = _parse_pcap(raw)
    frames = [decode_afdx(b) for b in pk if len(b) >= 14 and b[0] == 0x03]
    sns = [fr["afdx"]["sn"] for fr in frames]
    uniq = len(set(sns))
    return {"frames": frames[:12], "count": len(frames),
            "sn_seq": sns[:40], "uniq_sn": uniq,
            "dup": len(sns) - uniq}

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
        if path == "/capture":
            self._send(200, json.dumps(capture_afdx(os.environ.get("CAP_IF", "enp4s0")))); return
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
