set -eu
trap 'benchmark_exit=$?
systemctl stop ac-candidate-pplx
journalctl -u ac-candidate-pplx --no-pager -o short-iso > /opt/ac-nine-tests/logs/pplx-complete.log
aws s3 sync /opt/ac-nine-tests/logs s3://strands-decider-vllm-632930644527/output/ac-all-models/2026-10-30-full-v1/logs --only-show-errors
exit "$benchmark_exit"' EXIT
systemctl is-active --quiet ac-candidate-pplx
/opt/ac-nine-tests/runner-env/bin/python -u /opt/ac-nine-tests/run/run_all_models.py --run /opt/ac-nine-tests/run --provider pplx --endpoint http://127.0.0.1:18811 --s3-output s3://strands-decider-vllm-632930644527/output/ac-all-models/2026-10-30-full-v1/results