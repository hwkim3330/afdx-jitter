#!/bin/bash
# 정밀 지터 측정용 시스템 격리 (SW 타임스탬프 노이즈 제거). sudo 필요.
# 효과: Jitter RMS ~1.2us (미적용 시 부하따라 4~140us). 근거: docs/measurement_series.md
DEV=${1:-enp4s0}; CORE=${2:-8}
# 1) governor performance (클럭 스케일링 지연 제거)
for c in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do echo performance | sudo tee $c >/dev/null; done
# 2) NIC IRQ 를 전용 코어로 (mask = 1<<CORE, hex)
MASK=$(printf '%x' $((1<<CORE)))
for irq in $(grep "$DEV" /proc/interrupts | awk -F: '{print $1}'); do echo $MASK | sudo tee /proc/irq/$irq/smp_affinity >/dev/null 2>&1; done
# 3) C-state 잠금 (코어가 프레임 사이 깊은잠 안 자게) — fd 유지 필요
sudo python3 -c "import os,time;f=os.open('/dev/cpu_dma_latency',os.O_WRONLY);os.write(f,b'\x00\x00\x00\x00');print('cpu_dma_latency=0 held (pid',os.getpid(),')');time.sleep(100000)" &
echo "격리 완료: $DEV IRQ->cpu$CORE, governor=performance, C-state locked"
echo "측정: python3 capture_jitter.py --dev $DEV --bag 200 (tcpdump는 cpu9 고정됨)"
