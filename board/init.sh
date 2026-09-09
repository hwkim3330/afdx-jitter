#!/bin/sh
# /mnt/flash/init.sh (T2080RDB) — aero.ko + PTP HW timestamp 버전
rmmod aero; sleep 2
ifconfig eth0 192.168.7.113; sleep 2
mount -t nfs 192.168.7.202:/volume1/Shared /mnt/nfs; sleep 2
cd /mnt/nfs; sleep 2
insmod aero.ko; sleep 2
echo 1 > /proc/sys/net/ipv6/conf/aero0/disable_ipv6; sleep 2
ifconfig aero0 hw ether 00:00:00:00:00:03; sleep 2
ifconfig aero0 192.168.3.83; sleep 2
./aero_eth_app --ptp --start --slave --hwts --mode="auto" --interval=1000000 \
               --addr=4 --maxadjoffset=4000000 --maxadjfrq=520000 --kalman; sleep 2
./aero_eth_app --ptp --monitor
