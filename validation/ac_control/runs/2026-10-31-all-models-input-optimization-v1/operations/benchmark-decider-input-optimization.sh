set -eu
trap 'benchmark_exit=$?
systemctl stop ac-nine-decider
docker stop ac-nine-decider >/dev/null 2>&1 || true
journalctl -u ac-nine-decider --no-pager -o short-iso > /opt/ac-input-tests/logs/decider-complete.log
aws s3 sync /opt/ac-input-tests/logs s3://strands-decider-vllm-632930644527/output/ac-input-optimization/2026-10-31-nine-v1/logs --only-show-errors
exit "$benchmark_exit"' EXIT
systemctl is-active --quiet ac-nine-decider
/opt/ac-input-tests/runner-env/bin/python -u /opt/ac-input-tests/run/run_optimized_models.py --run /opt/ac-input-tests/run/profiles/schema_once --provider decider --endpoint http://127.0.0.1:18811 > /opt/ac-input-tests/logs/decider-schema_once-runner.log 2>&1
aws s3 sync /opt/ac-input-tests/run/profiles/schema_once/results/decider s3://strands-decider-vllm-632930644527/output/ac-input-optimization/2026-10-31-nine-v1/profiles/schema_once/results/decider --only-show-errors
/opt/ac-input-tests/runner-env/bin/python -u /opt/ac-input-tests/run/run_optimized_models.py --run /opt/ac-input-tests/run/profiles/baseline --provider decider --endpoint http://127.0.0.1:18811 > /opt/ac-input-tests/logs/decider-baseline-runner.log 2>&1
aws s3 sync /opt/ac-input-tests/run/profiles/baseline/results/decider s3://strands-decider-vllm-632930644527/output/ac-input-optimization/2026-10-31-nine-v1/profiles/baseline/results/decider --only-show-errors
/opt/ac-input-tests/runner-env/bin/python -u /opt/ac-input-tests/run/run_optimized_models.py --run /opt/ac-input-tests/run/profiles/compact_catalog --provider decider --endpoint http://127.0.0.1:18811 > /opt/ac-input-tests/logs/decider-compact_catalog-runner.log 2>&1
aws s3 sync /opt/ac-input-tests/run/profiles/compact_catalog/results/decider s3://strands-decider-vllm-632930644527/output/ac-input-optimization/2026-10-31-nine-v1/profiles/compact_catalog/results/decider --only-show-errors