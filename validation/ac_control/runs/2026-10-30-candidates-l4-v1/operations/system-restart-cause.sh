set -eu
journalctl --since '2026-10-30 12:51:45' --until '2026-10-30 12:53:30' --no-pager -o short-iso | grep -Ei 'upgrade|apt|restart|candidate|systemd\[1\]|reboot|reexecut|needrestart' | tail -100
tail -60 /var/log/apt/history.log
systemctl list-timers --all --no-pager
uptime
