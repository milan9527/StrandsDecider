set -eu
trap 'benchmark_exit=$?
systemctl stop ac-candidate-knowline
journalctl -u ac-candidate-knowline --no-pager -o short-iso > /opt/ac-nine-tests/logs/knowline-complete.log
aws s3 sync /opt/ac-nine-tests/logs s3://strands-decider-vllm-632930644527/output/ac-all-models/2026-10-30-full-v1/logs --only-show-errors
exit "$benchmark_exit"' EXIT
systemctl is-active --quiet ac-candidate-knowline
/opt/ac-nine-tests/runner-env/bin/python -u /opt/ac-nine-tests/run/run_all_models.py --run /opt/ac-nine-tests/run --provider knowline --endpoint http://127.0.0.1:18811 --s3-output s3://strands-decider-vllm-632930644527/output/ac-all-models/2026-10-30-full-v1/results