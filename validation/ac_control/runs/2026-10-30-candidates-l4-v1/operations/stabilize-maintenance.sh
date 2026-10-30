set -eu
systemctl stop apt-daily.timer apt-daily-upgrade.timer fwupd-refresh.timer update-notifier-download.timer
candidate_deadline=$(( $(date +%s) + 1800 ))
while systemctl is-active --quiet apt-daily-upgrade.service || systemctl is-active --quiet apt-daily.service; do
 test "$(date +%s)" -lt "$candidate_deadline"
 sleep 10
done
systemctl mask --runtime apt-daily.service apt-daily-upgrade.service fwupd-refresh.service update-notifier-download.service
systemctl is-active ac-candidate-torchcast.service || true
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
mkdir -p /opt/ac-candidate-tests/logs
cp /var/log/apt/history.log /opt/ac-candidate-tests/logs/apt-history-after-maintenance.log
journalctl -u apt-daily-upgrade --no-pager -o short-iso > /opt/ac-candidate-tests/logs/apt-upgrade-journal.log
dpkg-query -W > /opt/ac-candidate-tests/logs/system-packages-after-maintenance.txt
