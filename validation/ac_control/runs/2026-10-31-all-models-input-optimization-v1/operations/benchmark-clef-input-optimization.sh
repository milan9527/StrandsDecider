set -eu
trap 'benchmark_exit=$?
systemctl stop ac-candidate-clef
journalctl -u ac-candidate-clef --no-pager -o short-iso > /opt/ac-input-tests/logs/clef-complete.log
aws s3 sync /opt/ac-input-tests/logs s3://strands-decider-vllm-632930644527/output/ac-input-optimization/2026-10-31-nine-v1/logs --only-show-errors
exit "$benchmark_exit"' EXIT
systemctl is-active --quiet ac-candidate-clef
/opt/ac-input-tests/runner-env/bin/python -u /opt/ac-input-tests/run/run_optimized_models.py --run /opt/ac-input-tests/run/profiles/compact_catalog --provider clef --endpoint http://127.0.0.1:18811 > /opt/ac-input-tests/logs/clef-compact_catalog-runner.log 2>&1
aws s3 sync /opt/ac-input-tests/run/profiles/compact_catalog/results/clef s3://strands-decider-vllm-632930644527/output/ac-input-optimization/2026-10-31-nine-v1/profiles/compact_catalog/results/clef --only-show-errors
/opt/ac-input-tests/runner-env/bin/python -u /opt/ac-input-tests/run/run_optimized_models.py --run /opt/ac-input-tests/run/profiles/schema_once --provider clef --endpoint http://127.0.0.1:18811 > /opt/ac-input-tests/logs/clef-schema_once-runner.log 2>&1
aws s3 sync /opt/ac-input-tests/run/profiles/schema_once/results/clef s3://strands-decider-vllm-632930644527/output/ac-input-optimization/2026-10-31-nine-v1/profiles/schema_once/results/clef --only-show-errors
/opt/ac-input-tests/runner-env/bin/python -u /opt/ac-input-tests/run/run_optimized_models.py --run /opt/ac-input-tests/run/profiles/baseline --provider clef --endpoint http://127.0.0.1:18811 > /opt/ac-input-tests/logs/clef-baseline-runner.log 2>&1
aws s3 sync /opt/ac-input-tests/run/profiles/baseline/results/clef s3://strands-decider-vllm-632930644527/output/ac-input-optimization/2026-10-31-nine-v1/profiles/baseline/results/clef --only-show-errors