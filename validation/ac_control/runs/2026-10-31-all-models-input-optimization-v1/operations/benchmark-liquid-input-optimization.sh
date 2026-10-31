set -eu
trap 'benchmark_exit=$?
systemctl stop ac-nine-liquid
docker stop ac-nine-liquid >/dev/null 2>&1 || true
journalctl -u ac-nine-liquid --no-pager -o short-iso > /opt/ac-input-tests/logs/liquid-complete.log
aws s3 sync /opt/ac-input-tests/logs s3://strands-decider-vllm-632930644527/output/ac-input-optimization/2026-10-31-nine-v1/logs --only-show-errors
exit "$benchmark_exit"' EXIT
systemctl is-active --quiet ac-nine-liquid
/opt/ac-input-tests/runner-env/bin/python -u /opt/ac-input-tests/run/run_optimized_models.py --run /opt/ac-input-tests/run/profiles/baseline --provider liquid --endpoint http://127.0.0.1:18801 > /opt/ac-input-tests/logs/liquid-baseline-runner.log 2>&1
aws s3 sync /opt/ac-input-tests/run/profiles/baseline/results/liquid s3://strands-decider-vllm-632930644527/output/ac-input-optimization/2026-10-31-nine-v1/profiles/baseline/results/liquid --only-show-errors
/opt/ac-input-tests/runner-env/bin/python -u /opt/ac-input-tests/run/run_optimized_models.py --run /opt/ac-input-tests/run/profiles/compact_catalog --provider liquid --endpoint http://127.0.0.1:18801 > /opt/ac-input-tests/logs/liquid-compact_catalog-runner.log 2>&1
aws s3 sync /opt/ac-input-tests/run/profiles/compact_catalog/results/liquid s3://strands-decider-vllm-632930644527/output/ac-input-optimization/2026-10-31-nine-v1/profiles/compact_catalog/results/liquid --only-show-errors
/opt/ac-input-tests/runner-env/bin/python -u /opt/ac-input-tests/run/run_optimized_models.py --run /opt/ac-input-tests/run/profiles/schema_once --provider liquid --endpoint http://127.0.0.1:18801 > /opt/ac-input-tests/logs/liquid-schema_once-runner.log 2>&1
aws s3 sync /opt/ac-input-tests/run/profiles/schema_once/results/liquid s3://strands-decider-vllm-632930644527/output/ac-input-optimization/2026-10-31-nine-v1/profiles/schema_once/results/liquid --only-show-errors