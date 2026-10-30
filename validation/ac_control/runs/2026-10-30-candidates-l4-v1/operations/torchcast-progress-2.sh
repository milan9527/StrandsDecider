set -eu
systemctl show ac-candidate-torchcast --property=ActiveState,SubState,ExecMainStatus,MemoryCurrent
journalctl -u ac-candidate-torchcast --no-pager -n 12 -o cat | tr '\r' '\n' | tail -12
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
