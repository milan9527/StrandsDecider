set -eu
trap 'benchmark_exit=$?
systemctl stop ac-candidate-knowline
journalctl -u ac-candidate-knowline --no-pager -o short-iso > /opt/ac-input-tests/logs/knowline-complete.log
aws s3 sync /opt/ac-input-tests/logs s3://strands-decider-vllm-632930644527/output/ac-input-optimization/2026-10-31-nine-v1/logs --only-show-errors
exit "$benchmark_exit"' EXIT
systemctl is-active --quiet ac-candidate-knowline
/opt/ac-input-tests/runner-env/bin/python -u /opt/ac-input-tests/run/run_optimized_models.py --run /opt/ac-input-tests/run/profiles/schema_once --provider knowline --endpoint http://127.0.0.1:18811 > /opt/ac-input-tests/logs/knowline-schema_once-runner.log 2>&1
aws s3 sync /opt/ac-input-tests/run/profiles/schema_once/results/knowline s3://strands-decider-vllm-632930644527/output/ac-input-optimization/2026-10-31-nine-v1/profiles/schema_once/results/knowline --only-show-errors
/opt/ac-input-tests/runner-env/bin/python -u /opt/ac-input-tests/run/run_optimized_models.py --run /opt/ac-input-tests/run/profiles/baseline --provider knowline --endpoint http://127.0.0.1:18811 > /opt/ac-input-tests/logs/knowline-baseline-runner.log 2>&1
aws s3 sync /opt/ac-input-tests/run/profiles/baseline/results/knowline s3://strands-decider-vllm-632930644527/output/ac-input-optimization/2026-10-31-nine-v1/profiles/baseline/results/knowline --only-show-errors
/opt/ac-input-tests/runner-env/bin/python -u /opt/ac-input-tests/run/run_optimized_models.py --run /opt/ac-input-tests/run/profiles/compact_catalog --provider knowline --endpoint http://127.0.0.1:18811 > /opt/ac-input-tests/logs/knowline-compact_catalog-runner.log 2>&1
aws s3 sync /opt/ac-input-tests/run/profiles/compact_catalog/results/knowline s3://strands-decider-vllm-632930644527/output/ac-input-optimization/2026-10-31-nine-v1/profiles/compact_catalog/results/knowline --only-show-errors