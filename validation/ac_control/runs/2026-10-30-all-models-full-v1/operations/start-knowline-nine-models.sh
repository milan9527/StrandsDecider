set -eu
test -s /opt/ac-nine-tests/models-verified.json
test -s /opt/ac-nine-tests/logs/pplx-requirements.txt
test -s /opt/ac-nine-tests/logs/h2o-overlay-verification.json
test -z "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)"
systemd-run --unit ac-candidate-knowline --property=Restart=no --property=KillMode=control-group --property=TimeoutStopSec=45 --working-directory=/opt/ac-nine-tests/models/knowline --setenv=PATH=/opt/ac-nine-tests/envs/knowline/bin:/usr/local/cuda-13.0/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin --setenv=OMP_NUM_THREADS=2 --setenv=MKL_NUM_THREADS=2 --setenv=TORCHINDUCTOR_COMPILE_THREADS=1 --setenv=TOKENIZERS_PARALLELISM=false --setenv=TRITON_CACHE_DIR=/opt/ac-nine-tests/cache/knowline/triton --setenv=TORCHINDUCTOR_CACHE_DIR=/opt/ac-nine-tests/cache/knowline/inductor --setenv=CUDA_HOME=/usr/local/cuda-13.0 bash -c 'set -euo pipefail
/opt/ac-nine-tests/envs/knowline/bin/python -m sglang.launch_server --model-path /opt/ac-nine-tests/models/knowline --served-model-name m --tp 1 --quantization fp8 --mem-fraction-static 0.72 --mamba-radix-cache-strategy extra_buffer --enable-fp32-lm-head --host 127.0.0.1 --port 18812 &
engine_pid=$!
trap '"'"'kill "$engine_pid" 2>/dev/null || true'"'"' EXIT
until curl -sf -m 3 http://127.0.0.1:18812/health >/dev/null; do sleep 5; kill -0 "$engine_pid"; done
/opt/ac-nine-tests/envs/knowline/bin/python /opt/ac-nine-tests/models/knowline/knowline_server.py --model /opt/ac-nine-tests/models/knowline --backend sglang --url http://127.0.0.1:18812 --served-model-name m --temperature 1 --workers 16 --host 127.0.0.1 --port 18811'
candidate_deadline=$(( $(date +%s) + 1800 ))
trap 'journalctl -u ac-candidate-knowline --no-pager -o short-iso > /opt/ac-nine-tests/logs/knowline-nine-models-startup.log
aws s3 sync /opt/ac-nine-tests/logs s3://strands-decider-vllm-632930644527/output/ac-all-models/2026-10-30-full-v1/logs --only-show-errors' EXIT
until curl -sf -m 5 http://127.0.0.1:18811/health > /opt/ac-nine-tests/logs/knowline-health-startup.json; do
  systemctl is-active --quiet ac-candidate-knowline || exit 1
  test "$(date +%s)" -lt "$candidate_deadline" || exit 2
  sleep 10
done
nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version --format=csv