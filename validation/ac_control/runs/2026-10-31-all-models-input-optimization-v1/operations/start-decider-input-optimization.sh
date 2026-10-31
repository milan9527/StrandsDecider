set -eu
test -s /opt/ac-input-tests/logs/model-verification.json
test -z "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)"
systemd-run --unit ac-nine-decider --property=Restart=no --property=KillMode=control-group --property=TimeoutStopSec=60 docker run --rm --name ac-nine-decider --gpus all --network host --shm-size=2g --memory=6g --cpuset-cpus=0-3 --cap-drop=ALL --security-opt=no-new-privileges:true -v /opt/ac-input-tests/models/decider:/models/decider-vllm:ro -v /opt/ac-input-tests/decider-cache:/root/.cache 632930644527.dkr.ecr.us-east-1.amazonaws.com/strands-decider-vllm@sha256:0bd44d374991dc8782b93d58bb41b3aab63fa0d242149578b342cb139f371d07 serve --model /models/decider-vllm --host 127.0.0.1 --port 18811 --max-num-seqs 1 --max-inflight-questions 1 --max-pending-requests 32 --max-num-batched-tokens 8192 --gpu-memory-utilization 0.26 --timeout-seconds 25
candidate_deadline=$(( $(date +%s) + 1800 ))
until curl -sf -m 5 http://127.0.0.1:18811/health > /opt/ac-input-tests/logs/decider-health-startup.json; do
 systemctl is-active --quiet ac-nine-decider || exit 1
 test "$(date +%s)" -lt "$candidate_deadline" || exit 2
 sleep 10
done
aws s3 sync /opt/ac-input-tests/logs s3://strands-decider-vllm-632930644527/output/ac-input-optimization/2026-10-31-nine-v1/logs --only-show-errors