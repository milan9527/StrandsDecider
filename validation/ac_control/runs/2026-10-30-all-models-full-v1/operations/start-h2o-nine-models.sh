set -eu
test -s /opt/ac-nine-tests/models-verified.json
test -s /opt/ac-nine-tests/logs/pplx-requirements.txt
test -s /opt/ac-nine-tests/logs/h2o-overlay-verification.json
test -z "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)"
systemd-run --unit ac-candidate-h2o --property=Restart=no --property=KillMode=control-group --property=TimeoutStopSec=45 --working-directory=/opt/ac-nine-tests/models/h2o --setenv=PATH=/opt/ac-nine-tests/envs/h2o/bin:/usr/local/cuda-13.0/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin --setenv=OMP_NUM_THREADS=2 --setenv=MKL_NUM_THREADS=2 --setenv=TORCHINDUCTOR_COMPILE_THREADS=1 --setenv=TOKENIZERS_PARALLELISM=false --setenv=TRITON_CACHE_DIR=/opt/ac-nine-tests/cache/h2o/triton --setenv=TORCHINDUCTOR_CACHE_DIR=/opt/ac-nine-tests/cache/h2o/inductor --setenv=CUDA_HOME=/usr/local/cuda-13.0 --setenv=MODEL=/opt/ac-nine-tests/models/h2o --setenv=PORT=18811 --setenv=VLLM_PORT=18802 --setenv=MAX_LEN=4096 --setenv=GPU_UTIL=0.34 --setenv=MAX_IMAGES=1 --setenv=MAX_PIXELS=65536 --setenv=CUDA_GRAPH_MAX_TOKENS=128 --setenv=VLLM_GDN_PREFILL_GRAPH_MAX_TOKENS=0 --setenv=VLLM_GDN_PREFILL_GRAPH_PRECAPTURE=0 --setenv=VLLM_CACHE_ROOT=/opt/ac-nine-tests/cache/h2o/vllm --setenv=SHIM_CACHE_WRITE=all '--setenv=VLLM_ARGS=--max-num-seqs 1 --max-num-batched-tokens 4096 --enforce-eager --quantization fp8' bash /opt/ac-nine-tests/models/h2o/serve.sh
candidate_deadline=$(( $(date +%s) + 1800 ))
trap 'journalctl -u ac-candidate-h2o --no-pager -o short-iso > /opt/ac-nine-tests/logs/h2o-nine-models-startup.log
aws s3 sync /opt/ac-nine-tests/logs s3://strands-decider-vllm-632930644527/output/ac-all-models/2026-10-30-full-v1/logs --only-show-errors' EXIT
until curl -sf -m 5 http://127.0.0.1:18811/health > /opt/ac-nine-tests/logs/h2o-health-startup.json; do
  systemctl is-active --quiet ac-candidate-h2o || exit 1
  test "$(date +%s)" -lt "$candidate_deadline" || exit 2
  sleep 10
done
nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version --format=csv