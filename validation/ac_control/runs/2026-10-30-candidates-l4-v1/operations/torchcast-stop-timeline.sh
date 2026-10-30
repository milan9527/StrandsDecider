set -eu
journalctl -u ac-candidate-torchcast --since '2026-10-30 12:50:00' --no-pager -o short-iso
systemctl list-timers --all --no-pager | grep -E 'candidate|NEXT' || true
journalctl -u amazon-ssm-agent --since '2026-10-30 12:50:00' --no-pager -n 12 -o short-iso
