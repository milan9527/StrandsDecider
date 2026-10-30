set -eu
systemctl show ac-candidate-torchcast --property=ActiveState,SubState,Result,ExecMainCode,ExecMainStatus,MemoryPeak
journalctl -u ac-candidate-torchcast --no-pager -n 18 -o cat | tr '\r' '\n' | tail -18
journalctl -k --since '2026-10-30 12:50:00' --no-pager -o cat | grep -Ei 'oom|out of memory|killed process|NVRM|Xid' || true
free -m
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
