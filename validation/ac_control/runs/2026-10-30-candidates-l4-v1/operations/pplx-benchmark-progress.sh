set -eu
cat /opt/ac-candidate-tests/run/results/pplx/run.json
journalctl -u ac-candidate-pplx --no-pager -n 8 -o cat
