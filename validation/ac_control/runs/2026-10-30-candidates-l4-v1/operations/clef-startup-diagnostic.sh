nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
journalctl -u ac-candidate-clef -n 8 --no-pager -o cat