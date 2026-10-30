nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
journalctl -u ac-candidate-h2o -n 12 --no-pager -o cat