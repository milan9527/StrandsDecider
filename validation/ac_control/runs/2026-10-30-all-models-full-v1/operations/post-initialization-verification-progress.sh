set -eu
date -u
vmstat 1 2
cat /sys/fs/cgroup/system.slice/snap.amazon-ssm-agent.amazon-ssm-agent.service/io.max
cat /sys/fs/cgroup/system.slice/snap.amazon-ssm-agent.amazon-ssm-agent.service/memory.high
cat /sys/fs/cgroup/system.slice/snap.amazon-ssm-agent.amazon-ssm-agent.service/memory.max
ls -l /proc/2828/fd 2>/dev/null | tail -n 2
ls -l /opt/ac-nine-tests/logs/model-verification.json 2>/dev/null || true