#!/bin/bash
# afdx-jitter 데모 실행: 브리지 시작 + URL 안내
cd "$(dirname "$0")"
DEV=${1:-/dev/ttyUSB0}
pkill -f 'serial_bridge.py' 2>/dev/null; sleep 1
setsid python3 serial_bridge.py --dev "$DEV" >/tmp/afdx_bridge.log 2>&1 </dev/null &
sleep 2
echo "브리지 시작 (dev=$DEV)"
echo "  웹 터미널 : http://localhost:8777"
echo "  KFDX GUI  : http://localhost:8777/kfdx.html"
echo "정밀 측정 원하면: sudo ./measure_setup.sh enp4s0 8"
