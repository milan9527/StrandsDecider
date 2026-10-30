set -eu
systemctl show ac-candidate-knowline --property=ActiveState,SubState,ExecMainStatus,MemoryCurrent
journalctl -u ac-candidate-knowline --no-pager -n 20 -o cat
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
