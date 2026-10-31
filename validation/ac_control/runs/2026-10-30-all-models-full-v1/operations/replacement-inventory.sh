set -eu
cloud-init status --wait
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
df -h /
systemctl show ac-nine-auto-stop.timer --property=ActiveState,NextElapseUSecMonotonic
test -x /opt/ac-candidate-tests/tools/bin/uv