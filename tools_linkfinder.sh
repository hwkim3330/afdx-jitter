#!/bin/bash
# AFDX 포트 찾기: 보드 연속송신 중, PC 동글 수신 프레임을 1초마다 카운트.
# 케이블을 보드 RJ45 포트마다 옮기며 카운트가 0->양수로 튀는 포트를 찾는다.
DEV=${1:-enxc84d44263ba6}
echo "[linkfinder] $DEV 에서 수신 감시. 케이블을 보드 포트에 옮겨가며 관찰하세요. Ctrl-C 종료."
echo 1 | sudo -S true 2>/dev/null
while true; do
  c=$(echo 1 | sudo -S timeout 1 tcpdump -i "$DEV" -nn -c 100 2>/dev/null | wc -l)
  car=$(cat /sys/class/net/$DEV/carrier 2>/dev/null)
  printf "%s  carrier=%s  수신 %s pkt/s %s\n" "$(date +%H:%M:%S)" "${car:-?}" "$c" "$([ "$c" -gt 0 ] && echo '  <<< 프레임 도착!')"
done
