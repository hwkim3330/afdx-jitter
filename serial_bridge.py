#!/usr/bin/env python3
"""
Web serial terminal bridge for the T2080RDB console (or any UART).
  - Serves a browser terminal (xterm.js) at http://HOST:PORT/
  - Bridges the WebSocket at /ws  <->  the serial port
  - Single owner of the serial port; multiple browsers share the same session
Usage:
  python3 serial_bridge.py --dev /dev/ttyUSB0 --baud 115200 --http 0.0.0.0:8777
"""
import argparse, asyncio, json, os, sys, threading, queue, time
import serial
import websockets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

class SerialHub:
    """Owns the serial port. Reader thread -> broadcasts to all ws clients."""
    def __init__(self, dev, baud):
        self.dev, self.baud = dev, baud
        self.ser = None
        self.clients = set()          # asyncio.Queue per client
        self.loop = None
        self.lock = threading.Lock()
        self.status = "closed"

    def open(self):
        with self.lock:
            if self.ser and self.ser.is_open:
                return
            self.ser = serial.Serial(self.dev, self.baud, timeout=0.05)
            self.status = "open"

    def close(self):
        with self.lock:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.status = "closed"

    def set_baud(self, baud):
        with self.lock:
            self.baud = baud
            if self.ser and self.ser.is_open:
                self.ser.baudrate = baud

    def write(self, data: bytes):
        with self.lock:
            if self.ser and self.ser.is_open:
                self.ser.write(data)

    def reader_thread(self):
        while True:
            try:
                self.open()
                data = self.ser.read(4096)
                if data:
                    self._broadcast(data)
                else:
                    time.sleep(0.005)
            except Exception as e:
                self.status = "error: %s" % e
                self._broadcast_status()
                time.sleep(1.0)
                try: self.close()
                except: pass

    def _broadcast(self, data: bytes):
        if not self.loop: return
        for q in list(self.clients):
            self.loop.call_soon_threadsafe(q.put_nowait, data)

    def _broadcast_status(self):
        if not self.loop: return
        msg = ("\x00STATUS " + self.status).encode()
        for q in list(self.clients):
            self.loop.call_soon_threadsafe(q.put_nowait, msg)

HUB = None  # set in main

async def ws_handler(ws):
    q = asyncio.Queue()
    HUB.clients.add(q)
    # send current status
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
                # control channel as JSON
                try:
                    cmd = json.loads(msg)
                except Exception:
                    HUB.write(msg.encode()); continue
                op = cmd.get("op")
                if op == "data":
                    HUB.write(cmd["d"].encode("utf-8","ignore"))
                elif op == "baud":
                    HUB.set_baud(int(cmd["v"]))
                    await ws.send(("\x00STATUS baud=%d" % HUB.baud).encode())
                elif op == "break":
                    with HUB.lock:
                        if HUB.ser: HUB.ser.send_break(0.25)
                elif op == "signal":
                    with HUB.lock:
                        if HUB.ser:
                            if "dtr" in cmd: HUB.ser.dtr = bool(cmd["dtr"])
                            if "rts" in cmd: HUB.ser.rts = bool(cmd["rts"])
            else:
                HUB.write(msg)   # raw binary keystrokes
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
    srv = ThreadingHTTPServer((host, port), WebHandler)
    srv.serve_forever()

async def amain(args):
    global HUB
    HUB = SerialHub(args.dev, args.baud)
    HUB.loop = asyncio.get_event_loop()
    threading.Thread(target=HUB.reader_thread, daemon=True).start()
    host, hport = args.http.split(":")
    threading.Thread(target=run_http, args=(host, int(hport)), daemon=True).start()
    print(f"[bridge] serial {args.dev}@{args.baud}")
    print(f"[bridge] open  http://{host if host!='0.0.0.0' else 'localhost'}:{hport}/")
    async with websockets.serve(ws_handler, host, int(args.wsport), max_size=None):
        await asyncio.Future()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", default="/dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--http", default="0.0.0.0:8777")
    ap.add_argument("--wsport", default="8778")
    args = ap.parse_args()
    try:
        asyncio.run(amain(args))
    except KeyboardInterrupt:
        print("\n[bridge] bye")

if __name__ == "__main__":
    main()
