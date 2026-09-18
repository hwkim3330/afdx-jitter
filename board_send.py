#!/usr/bin/env python3
"""AFDX 보드(ttyUSB0) 로그인 + AFDX 송신 제어. sudo 필요.
  board_send.py <port> start   → 연속 송신 백그라운드 시작(A/B 계속 흐름)
  board_send.py <port> stop    → 연속 송신 중지
  board_send.py <port> burst N → N회 송신
  board_send.py <port> status  → VL/링크 상태
"""
import serial, time, sys, re
PORT = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyUSB0'
MODE = sys.argv[2] if len(sys.argv) > 2 else 'burst'
ARG  = sys.argv[3] if len(sys.argv) > 3 else '6'
ANSI = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]|\x1b[78=>]|\x1b\][^\x07]*\x07?')
s = serial.Serial(PORT, 115200, timeout=1)
def clean(x): return ANSI.sub('', x)
def rd(w=1.0): time.sleep(w); return clean(s.read(9000).decode('latin1', 'replace'))
def snd(c, w=1.0): s.write(c.encode() + b'\r'); return rd(w)

# --- 로그인 보장 ---
s.write(b'\r\n'); o = rd(1.0)
if 'login' in o.lower():
    o = snd('root', 1.2)
if 'assword' in o.lower():
    o = snd('', 1.2)
o = snd('true', 0.8)              # 프롬프트 유도
if '#' not in o and '$' not in o:
    # 재시도 로그인
    s.write(b'\r'); r = rd(0.8)
    if 'login' in r.lower(): snd('root', 1.0)
    if 'assword' in r.lower(): snd('', 1.0)
    o = snd('true', 0.8)
if '#' not in o and '$' not in o:
    print('LOGIN_FAIL', repr(o[-120:])); s.close(); sys.exit(1)
print('LOGIN_OK  prompt:', repr(o.strip().splitlines()[-1] if o.strip() else o))

s.write(b'cd /mnt/flash\r'); rd(0.5)
if MODE == 'status':
    print(snd('./kfdx_app --get --vlid=1 2>&1 | grep -iE "vlid|bag|dir"', 1.8).strip()[-300:])
elif MODE == 'stop':
    snd('kill $(cat /tmp/afdxsend.pid 2>/dev/null) 2>/dev/null; pkill -f afdxloop 2>/dev/null; echo STOPPED', 1.5)
    print('연속 송신 중지')
elif MODE == 'start':
    # VL 없으면 추가
    o = snd('./kfdx_app --get --vlid=1 2>&1 | grep -iE "vlid"', 1.5)
    if 'VLID' not in o.upper():
        snd('./kfdx_app --add --vlid=1 --bag=200 --dir=tx --type=queueing --min=64 --max=1518', 2.0)
    # 연속 송신 백그라운드 (afdxloop 마커로 나중에 kill)
    snd('kill $(cat /tmp/afdxsend.pid 2>/dev/null) 2>/dev/null; true', 0.8)
    s.write(b"nohup sh -c 'while true; do /mnt/flash/kfdx_app --send --vlid=1 --udp --len=17 --count=3000 >/dev/null 2>&1; done' >/dev/null 2>&1 & echo $! > /tmp/afdxsend.pid; echo STARTED_$(cat /tmp/afdxsend.pid)\r")
    print(rd(1.5).strip()[-120:])
    print('연속 송신 시작(백그라운드)')
else:  # burst
    n = int(ARG)
    o = snd('./kfdx_app --get --vlid=1 2>&1 | grep -iE "vlid"', 1.5)
    if 'VLID' not in o.upper():
        snd('./kfdx_app --add --vlid=1 --bag=200 --dir=tx --type=queueing --min=64 --max=1518', 2.0)
    for i in range(n):
        snd('./kfdx_app --send --vlid=1 --udp --len=17 --count=3000 >/dev/null 2>&1; echo s', 1.1)
    print(f'{n}회 송신 완료')
s.close()
