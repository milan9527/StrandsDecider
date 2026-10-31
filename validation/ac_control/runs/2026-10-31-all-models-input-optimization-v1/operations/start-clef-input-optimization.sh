set -eu
test -s /opt/ac-input-tests/models-verified.json
test -s /opt/ac-input-tests/logs/pplx-requirements.txt
test -s /opt/ac-input-tests/logs/h2o-overlay-verification.json
test -z "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)"
/opt/ac-input-tests/envs/clef/bin/python -c 'from transformers import AutoProcessor; p=AutoProcessor.from_pretrained('"'"'/opt/ac-input-tests/models/clef'"'"'); print(type(p).__name__)'
systemd-run --unit ac-candidate-clef --property=Restart=no --property=KillMode=control-group --property=TimeoutStopSec=45 --working-directory=/opt/ac-input-tests/models/clef --setenv=PATH=/opt/ac-input-tests/envs/clef/bin:/usr/local/cuda-13.0/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin --setenv=OMP_NUM_THREADS=2 --setenv=MKL_NUM_THREADS=2 --setenv=TORCHINDUCTOR_COMPILE_THREADS=1 --setenv=TOKENIZERS_PARALLELISM=false --setenv=TRITON_CACHE_DIR=/opt/ac-input-tests/cache/clef/triton --setenv=TORCHINDUCTOR_CACHE_DIR=/opt/ac-input-tests/cache/clef/inductor --setenv=CUDA_HOME=/usr/local/cuda-13.0 /opt/ac-input-tests/envs/clef/bin/python /opt/ac-input-tests/run/candidate_server.py --provider clef --model /opt/ac-input-tests/models/clef --cases /opt/ac-input-tests/run/cases.json --metadata /opt/ac-input-tests/logs/clef-runtime.json --port 18811
candidate_deadline=$(( $(date +%s) + 1800 ))
trap 'journalctl -u ac-candidate-clef --no-pager -o short-iso > /opt/ac-input-tests/logs/clef-input-optimization-startup.log
aws s3 sync /opt/ac-input-tests/logs s3://strands-decider-vllm-632930644527/output/ac-input-optimization/2026-10-31-nine-v1/logs --only-show-errors' EXIT
until curl -sf -m 5 http://127.0.0.1:18811/health > /opt/ac-input-tests/logs/clef-health-startup.json; do
  systemctl is-active --quiet ac-candidate-clef || exit 1
  test "$(date +%s)" -lt "$candidate_deadline" || exit 2
  sleep 10
done
nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version --format=csv