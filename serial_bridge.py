#!/usr/bin/env python3
"""
Web serial terminal + KFDX command RPC bridge for the T2080RDB / KFDX AFDX NIC.
  - Serves a browser terminal (xterm.js) at http://HOST:PORT/
  - /kfdx.html : KFDX GUI (VL config, send, live jitter/stat visualization)
  - WebSocket bridges raw console <-> serial, and provides a "cmd" RPC that runs
    one shell command and returns just its output (echo/marker-stripped).
Usage:
  python3 serial_bridge.py --dev /dev/ttyUSB0 --baud 115200 --http 0.0.0.0:8777
"""
import argparse, asyncio, json, os, random, re, sys, threading, time
import serial
import websockets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

class SerialHub:
    def __init__(self, dev, baud):
        self.dev, self.baud = dev, baud
        self.ser = None
        self.clients = set()          # asyncio.Queue per ws client (raw stream)
        self.captures = []            # list of bytearray, fed by reader thread
        self.loop = None
        self.lock = threading.Lock()
        self.cmd_lock = None          # asyncio.Lock, created in loop
        self.status = "closed"

    def open(self):
        with self.lock:
            if self.ser and self.ser.is_open: return
            self.ser = serial.Serial(self.dev, self.baud, timeout=0.05)
            self.status = "open"

    def close(self):
        with self.lock:
            if self.ser and self.ser.is_open: self.ser.close()
            self.status = "closed"

    def set_baud(self, baud):
        with self.lock:
            self.baud = baud
            if self.ser and self.ser.is_open: self.ser.baudrate = baud

    def write(self, data: bytes):
        with self.lock:
            if self.ser and self.ser.is_open: self.ser.write(data)

    def reader_thread(self):
        while True:
            try:
                self.open()
                data = self.ser.read(4096)
                if data:
                    for cap in list(self.captures): cap.extend(data)
                    self._broadcast(data)
                else:
                    time.sleep(0.004)
            except Exception as e:
                self.status = "error: %s" % e
                time.sleep(1.0)
                try: self.close()
                except: pass

    def _broadcast(self, data: bytes):
        if not self.loop: return
        for q in list(self.clients):
            self.loop.call_soon_threadsafe(q.put_nowait, data)

HUB = None

ANSI = re.compile(rb'\x1b\[[0-9;?]*[a-zA-Z]|\x1b[78]|\x1b\][^\x07]*\x07')

async def run_cmd(cmd, timeout=8.0):
    """Send one shell command, capture only its stdout using a unique marker."""
    async with HUB.cmd_lock:
        token = "%08x" % random.getrandbits(32)
        marker = "K@D0NE@" + token          # appears only in real output
        # printf keeps the literal %s in the echo, so echo != real marker line
        full = "%s ; printf 'K@D0NE@%%s\\n' %s\r" % (cmd, token)
        cap = bytearray()
        HUB.captures.append(cap)
        try:
            HUB.write(full.encode("utf-8", "ignore"))
            t0 = time.time()
            mk = marker.encode()
            while time.time() - t0 < timeout:
                if mk in cap: break
                await asyncio.sleep(0.02)
            raw = bytes(cap)
        finally:
            try: HUB.captures.remove(cap)
            except ValueError: pass
        text = ANSI.sub(b'', raw).decode("utf-8", "replace")
        text = text.replace('\r', '')
        # slice between the command echo and the marker line
        idx = text.find(marker)
        body = text[:idx] if idx >= 0 else text
        lines = body.split('\n')
        # drop the first line (the echoed command) and any trailing prompt
        if lines and ('printf' in lines[0] or cmd.split()[0] in lines[0]):
            lines = lines[1:]
        lines = [l for l in lines if 'K@D0NE@' not in l]
        out = '\n'.join(lines).strip('\n')
        return out, (mk in raw)

async def ws_handler(ws):
    q = asyncio.Queue()
    HUB.clients.add(q)
    await ws.send(b"\x00STATUS " + HUB.status.encode())
    async def pump():
        while True:
            data = await q.get()
            try: await ws.send(data)
            except: return
    task = asyncio.ensure_future(pump())
    try:
        async for msg in ws:
            if isinstance(msg, str):
                try: cmd = json.loads(msg)
                except Exception: HUB.write(msg.encode("utf-8","ignore")); continue
                op = cmd.get("op")
                if op == "data":
                    HUB.write(cmd["d"].encode("utf-8","ignore"))
                elif op == "baud":
                    HUB.set_baud(int(cmd["v"]))
                    await ws.send(("\x00STATUS baud=%d" % HUB.baud).encode())
                elif op == "break":
                    with HUB.lock:
                        if HUB.ser: HUB.ser.send_break(0.25)
                elif op == "cmd":
                    out, ok = await run_cmd(cmd["c"], float(cmd.get("t", 8.0)))
                    await ws.send(json.dumps({"op":"cmdresult","id":cmd.get("id"),
                                              "cmd":cmd["c"],"out":out,"ok":ok}))
                elif op == "capture":
                    ob="/tmp/gui_cap"
                    here=os.path.dirname(os.path.abspath(__file__))
                    proc=await asyncio.create_subprocess_exec(
                        sys.executable, os.path.join(here,"capture_jitter.py"),
                        "--dev", str(cmd.get("dev","enp4s0")),
                        "--bag", str(cmd.get("bag",200)),
                        "--len", str(cmd.get("len",17)),
                        "--count", str(cmd.get("count",2000)),
                        "--repeat", str(cmd.get("repeat",10)),
                        "--wsport","8778","--out",ob,"--pcap",ob+".pcap",
                        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                    await proc.wait()
                    try: data=json.load(open(ob+".json"))
                    except Exception as e: data={"error":str(e)}
                    await ws.send(json.dumps({"op":"captureresult","id":cmd.get("id"),"data":data}))
            else:
                HUB.write(msg)
    finally:
        task.cancel()
        HUB.clients.discard(q)

class WebHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/": path = "/index.html"
        fp = os.path.normpath(os.path.join(WEB, path.lstrip("/")))
        if not fp.startswith(WEB) or not os.path.isfile(fp):
            self.send_error(404); return
        ctype = ("text/html" if fp.endswith(".html") else
                 "text/css" if fp.endswith(".css") else
                 "application/javascript" if fp.endswith(".js") else
                 "application/octet-stream")
        with open(fp, "rb") as f: body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

def run_http(host, port):
    ThreadingHTTPServer((host, port), WebHandler).serve_forever()

async def amain(args):
    global HUB
    HUB = SerialHub(args.dev, args.baud)
    HUB.loop = asyncio.get_event_loop()
    HUB.cmd_lock = asyncio.Lock()
    threading.Thread(target=HUB.reader_thread, daemon=True).start()
    host, hport = args.http.split(":")
    threading.Thread(target=run_http, args=(host, int(hport)), daemon=True).start()
    print(f"[bridge] serial {args.dev}@{args.baud}")
    print(f"[bridge] terminal  http://localhost:{hport}/")
    print(f"[bridge] kfdx GUI  http://localhost:{hport}/kfdx.html")
    async with websockets.serve(ws_handler, host, int(args.wsport), max_size=None):
        await asyncio.Future()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", default="/dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--http", default="0.0.0.0:8777")
    ap.add_argument("--wsport", default="8778")
    args = ap.parse_args()
    try: asyncio.run(amain(args))
    except KeyboardInterrupt: print("\n[bridge] bye")

if __name__ == "__main__":
    main()
