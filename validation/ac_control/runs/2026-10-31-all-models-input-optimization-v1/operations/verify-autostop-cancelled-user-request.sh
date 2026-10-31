set -eu
for unit in ac-input-autostop.timer ac-input-autostop.service; do
 if test "$(systemctl show "$unit" -p LoadState --value)" = loaded; then systemctl stop "$unit"; fi
done
shutdown -c || true
if systemctl is-active --quiet ac-input-autostop.timer; then exit 1; fi
if test -e /run/systemd/shutdown/scheduled; then cat /run/systemd/shutdown/scheduled; exit 1; fi
systemctl list-timers --all --no-pager
echo Automatic_shutdown_cancelled