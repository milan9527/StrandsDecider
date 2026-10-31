set -eu
date -u
test "$(findmnt -n -o SOURCE /)" = /dev/nvme0n1p1 || test "$(findmnt -n -o SOURCE /)" = /dev/root
test "$(cat /sys/block/nvme0n1/queue/read_ahead_kb)" = 128
blockdev --setra 4096 /dev/nvme0n1
blockdev --setra 4096 /dev/nvme0n1p1
cat /sys/block/nvme0n1/queue/read_ahead_kb
vmstat 1 4