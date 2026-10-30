set -eu
journalctl -u ac-candidate-knowline --no-pager -n 14 -o cat
ps -eo pid,etime,pcpu,rss,comm --sort=-pcpu | head -7
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
