set -eu
systemctl show ac-candidate-pplx --property=ActiveState,SubState,ExecMainStatus,MemoryCurrent
journalctl -u ac-candidate-pplx --no-pager -n 22 -o cat
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
