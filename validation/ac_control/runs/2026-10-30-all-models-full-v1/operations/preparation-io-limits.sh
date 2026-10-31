set -eu
date -u
cat /sys/fs/cgroup/io.max 2>/dev/null || true
cat /sys/fs/cgroup/system.slice/io.max 2>/dev/null || true
for io_limit in /sys/fs/cgroup/system.slice/*/io.max; do test ! -s "$io_limit" || { echo "$io_limit"; cat "$io_limit"; }; done
cat /sys/block/nvme0n1/queue/read_ahead_kb
cat /proc/2828/cgroup 2>/dev/null || true