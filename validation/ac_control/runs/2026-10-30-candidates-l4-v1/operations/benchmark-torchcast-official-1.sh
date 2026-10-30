set -eu
trap 'candidate_exit=$?
systemctl stop ac-candidate-torchcast
journalctl -u ac-candidate-torchcast --no-pager -o short-iso > /opt/ac-candidate-tests/logs/torchcast-official-1-complete.log
aws s3 sync /opt/ac-candidate-tests/logs s3://strands-decider-vllm-632930644527/output/ac-candidates/2026-10-30-l4-v1/logs --only-show-errors
exit "$candidate_exit"' EXIT
systemctl is-active --quiet ac-candidate-torchcast
python3 /opt/ac-candidate-tests/run/run_candidate_benchmark.py --run /opt/ac-candidate-tests/run --provider torchcast --endpoint http://127.0.0.1:18811 --s3-output s3://strands-decider-vllm-632930644527/output/ac-candidates/2026-10-30-l4-v1/results