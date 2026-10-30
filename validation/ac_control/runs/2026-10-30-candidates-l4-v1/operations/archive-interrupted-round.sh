set -eu
test -z "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)"
mkdir -p /opt/ac-candidate-tests/run/attempts/pre-maintenance
test ! -e /opt/ac-candidate-tests/run/attempts/pre-maintenance/results
mv /opt/ac-candidate-tests/run/results /opt/ac-candidate-tests/run/attempts/pre-maintenance/results
cp -a /opt/ac-candidate-tests/logs /opt/ac-candidate-tests/run/attempts/pre-maintenance/logs
aws s3 sync /opt/ac-candidate-tests/run/attempts/pre-maintenance s3://strands-decider-vllm-632930644527/output/ac-candidates/2026-10-30-l4-v1/attempts/pre-maintenance --only-show-errors
cat > /etc/systemd/system/ac-candidate-fixed-stop.service <<'SERVICE'
[Unit]
Description=Stop the temporary L4 at the original benchmark deadline
[Service]
Type=oneshot
ExecStart=/usr/sbin/shutdown -h now
SERVICE
cat > /etc/systemd/system/ac-candidate-fixed-stop.timer <<'TIMER'
[Unit]
Description=Fixed UTC deadline for the temporary L4 benchmark
[Timer]
OnCalendar=2026-10-30 18:01:37 UTC
AccuracySec=1s
Persistent=false
Unit=ac-candidate-fixed-stop.service
TIMER
systemctl daemon-reload
systemctl start ac-candidate-fixed-stop.timer
systemctl is-active --quiet ac-candidate-fixed-stop.timer
systemctl stop ac-candidate-auto-stop.timer
systemctl show ac-candidate-fixed-stop.timer --property=ActiveState,NextElapseUSecRealtime
