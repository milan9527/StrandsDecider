set -eu
cat /opt/ac-candidate-tests/run/results/torchcast/run.json
journalctl -u ac-candidate-torchcast --no-pager -n 4 -o cat | tr '\r' '\n' | tail -4
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
