#!/usr/bin/env python3
"""AFDX 보드(ttyUSB0) 로그인 후 임의 명령 실행 → 정제 출력. sudo 필요.
  board_cmd.py <port> '<command>'
"""
import serial, time, sys, re
PORT = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyUSB0'
CMD  = sys.argv[2] if len(sys.argv) > 2 else 'true'
ANSI = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]|\x1b[78=>]|\x1b\][^\x07]*\x07?')
s = serial.Serial(PORT, 115200, timeout=1)
def clean(x): return ANSI.sub('', x)
def rd(w=1.0): time.sleep(w); return clean(s.read(20000).decode('latin1', 'replace'))
def snd(c, w=1.0): s.write(c.encode() + b'\r'); return rd(w)
s.write(b'\r\n'); o = rd(0.9)
if 'login' in o.lower(): o = snd('root', 1.2)
if 'assword' in o.lower(): o = snd('', 1.2)
snd('true', 0.6)
out = snd(CMD, float(sys.argv[3]) if len(sys.argv) > 3 else 2.0)
# 프롬프트/에코 정리해서 본문만
print(out)
s.close()
