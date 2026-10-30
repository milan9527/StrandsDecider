set -eu
journalctl -u ac-candidate-pplx --no-pager -n 18 -o cat
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
ps -eo pid,etime,pcpu,rss,comm --sort=-pcpu | head -8
