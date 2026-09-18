#!/usr/bin/env python3
"""한 세션에서 KFDX 드라이버 재로드→즉시검증→송신. 드라이버가 언제 죽는지 추적."""
import serial, time, sys, re
PORT='/dev/ttyUSB0'
ANSI=re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]|\x1b[78=>]|\x1b\][^\x07]*\x07?')
s=serial.Serial(PORT,115200,timeout=1)
def rd(w=1.0): time.sleep(w); return ANSI.sub('',s.read(20000).decode('latin1','replace'))
def snd(c,w=1.5): s.write(c.encode()+b'\r'); return rd(w)
s.write(b'\r\n'); o=rd(0.9)
if 'login' in o.lower(): o=snd('root',1.2)
if 'assword' in o.lower(): o=snd('',1.2)
snd('true',0.6)
def show(t,c,w=2.0): print(f'\n### {t}'); print(snd(c,w).replace(c,'').strip()[:600])
show('송신루프 중지','kill $(cat /tmp/afdxsend.pid) 2>/dev/null; pkill kfdx_app 2>/dev/null; sleep 1; echo done')
show('lsmod','lsmod | grep kfdx || echo NOT_LOADED')
show('dmesg 최근 kfdx','dmesg | grep -iE "kfdx|oops|fault|BUG" | tail -8')
show('드라이버 재로드','cd /mnt/flash; rmmod kfdx 2>/dev/null; sleep 1; insmod ./kfdx.ko 2>&1 | tail -3; sleep 2; lsmod|grep kfdx; ls -la /dev/kfdx',5)
show('즉시 --get vl1','cd /mnt/flash && ./kfdx_app --get --vlid=1 2>&1 | head -6')
show('VL1 add','cd /mnt/flash && ./kfdx_app --add --vlid=1 --bag=200 --dir=tx --type=queueing --min=64 --max=1518 2>&1 | head -4',3)
show('단일 send','cd /mnt/flash && ./kfdx_app --send --vlid=1 --udp --len=17 --count=2000 2>&1 | head -6',3)
show('send 직후 재-get(드라이버 살아있나)','cd /mnt/flash && ./kfdx_app --get --vlid=1 2>&1 | head -4')
s.close()
