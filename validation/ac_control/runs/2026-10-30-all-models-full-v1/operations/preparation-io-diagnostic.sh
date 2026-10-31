set -eu
date -u
lsblk -o NAME,SIZE,RA,TYPE,MOUNTPOINTS
vmstat 1 3
ps -eo pid,stat,wchan:24,comm | awk '$4 == "decider-vllm" || $4 == "python3" {print}'
ls -l /opt/ac-nine-tests/logs/strands-model-integrity.json /opt/ac-nine-tests/logs/model-verification.json 2>/dev/null || true
cat /proc/pressure/io