bash -c 'set -euo pipefail
test -d /opt/ac-candidate-tests/models
test ! -d /opt/ac-nine-tests
mkdir -p /opt/ac-nine-tests/run /opt/ac-nine-tests/logs /opt/ac-nine-tests/models
systemctl stop apt-daily.timer apt-daily-upgrade.timer fwupd-refresh.timer update-notifier-download.timer || true
systemctl mask --runtime apt-daily.service apt-daily-upgrade.service fwupd-refresh.service update-notifier-download.service
maintenance_deadline=$(( $(date +%s) + 1800 ))
while systemctl is-active --quiet apt-daily.service || systemctl is-active --quiet apt-daily-upgrade.service; do
 test "$(date +%s)" -lt "$maintenance_deadline" || exit 3
 sleep 10
done
test -z "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)"
ln -s /opt/ac-candidate-tests/envs /opt/ac-nine-tests/envs
ln -s /opt/ac-candidate-tests/cache /opt/ac-nine-tests/cache
cp /opt/ac-candidate-tests/models-verified.json /opt/ac-nine-tests/models-verified.json
cp /opt/ac-candidate-tests/logs/*requirements.txt /opt/ac-nine-tests/logs/
cp /opt/ac-candidate-tests/logs/h2o-overlay-verification.json /opt/ac-nine-tests/logs/
ln -s /opt/ac-candidate-tests/models/pplx /opt/ac-nine-tests/models/pplx
ln -s /opt/ac-candidate-tests/models/knowline /opt/ac-nine-tests/models/knowline
ln -s /opt/ac-candidate-tests/models/torchcast /opt/ac-nine-tests/models/torchcast
ln -s /opt/ac-candidate-tests/models/clef /opt/ac-nine-tests/models/clef
ln -s /opt/ac-candidate-tests/models/h2o /opt/ac-nine-tests/models/h2o
aws s3 cp s3://strands-decider-vllm-632930644527/input/ac-all-models/2026-10-30-full-v1/runtime-input.tar.gz /opt/ac-nine-tests/runtime-input.tar.gz --only-show-errors
python3 - <<'"'"'CHECK'"'"'
import hashlib,tarfile
path='"'"'/opt/ac-nine-tests/runtime-input.tar.gz'"'"'
assert hashlib.sha256(open(path,'"'"'rb'"'"').read()).hexdigest()=='"'"'903095850e64919f670b4b7a4004bcc8b0fce01ee16938a26d03771c3df84a53'"'"'
with tarfile.open(path) as archive:
 assert all(m.isfile() and '"'"'/'"'"' not in m.name for m in archive.getmembers())
 archive.extractall('"'"'/opt/ac-nine-tests/run'"'"', filter='"'"'data'"'"')
CHECK
/opt/ac-candidate-tests/tools/bin/uv venv --python /usr/bin/python3 /opt/ac-nine-tests/runner-env
/opt/ac-candidate-tests/tools/bin/uv pip install --python /opt/ac-nine-tests/runner-env/bin/python boto3 httpx
/opt/ac-candidate-tests/tools/bin/uv pip freeze --python /opt/ac-nine-tests/runner-env/bin/python > /opt/ac-nine-tests/logs/runner-requirements.txt
aws s3 sync s3://strands-decider-vllm-632930644527/input/model/ /opt/ac-nine-tests/models/decider --only-show-errors
aws s3 sync s3://strands-decider-vllm-632930644527/input/ac-all-models/2026-10-30-full-v1/models/liquid/ /opt/ac-nine-tests/models/liquid --only-show-errors
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 632930644527.dkr.ecr.us-east-1.amazonaws.com
docker pull 632930644527.dkr.ecr.us-east-1.amazonaws.com/strands-decider-vllm@sha256:0bd44d374991dc8782b93d58bb41b3aab63fa0d242149578b342cb139f371d07
docker image inspect 632930644527.dkr.ecr.us-east-1.amazonaws.com/strands-decider-vllm@sha256:0bd44d374991dc8782b93d58bb41b3aab63fa0d242149578b342cb139f371d07 --format '"'"'{{.Id}}'"'"' > /opt/ac-nine-tests/logs/strands-image-id.txt
docker logout 632930644527.dkr.ecr.us-east-1.amazonaws.com
docker run --rm --memory=4g -v /opt/ac-nine-tests/models/decider:/models/decider-vllm:ro 632930644527.dkr.ecr.us-east-1.amazonaws.com/strands-decider-vllm@sha256:0bd44d374991dc8782b93d58bb41b3aab63fa0d242149578b342cb139f371d07 verify-artifacts --model /models/decider-vllm > /opt/ac-nine-tests/logs/strands-model-integrity.json
python3 - <<'"'"'VERIFY'"'"'
import hashlib,json,pathlib
base=pathlib.Path('"'"'/opt/ac-nine-tests/models'"'"')
result={}
for name in ['"'"'liquid'"'"','"'"'pplx'"'"','"'"'knowline'"'"','"'"'torchcast'"'"','"'"'clef'"'"','"'"'h2o'"'"']:
 manifest=json.loads((base/name/'"'"'manifest.json'"'"').read_text())
 for item in manifest['"'"'files'"'"']:
  path=base/name/item['"'"'path'"'"']
  h=hashlib.sha256()
  with path.open('"'"'rb'"'"') as f:
   for chunk in iter(lambda:f.read(4*1024*1024),b'"'"''"'"'): h.update(chunk)
  assert h.hexdigest()==item['"'"'sha256'"'"'],str(path)
 result[name]={'"'"'revision'"'"':manifest['"'"'revision'"'"'],'"'"'verified_files'"'"':len(manifest['"'"'files'"'"'])}
pathlib.Path('"'"'/opt/ac-nine-tests/logs/model-verification.json'"'"').write_text(json.dumps(result,indent=2))
VERIFY
/opt/ac-candidate-tests/envs/h2o/bin/python - <<'"'"'OVERLAY'"'"'
import hashlib,json,pathlib,sysconfig
path=pathlib.Path('"'"'/opt/ac-nine-tests/logs/h2o-overlay-verification.json'"'"')
expected=json.loads(path.read_text())
site=pathlib.Path(sysconfig.get_paths()['"'"'purelib'"'"'])
assert len(expected)==30
assert all(hashlib.sha256((site/name).read_bytes()).hexdigest()==sha for name,sha in expected.items())
pathlib.Path('"'"'/opt/ac-nine-tests/logs/h2o-overlay-rechecked.json'"'"').write_text(json.dumps(expected,indent=2))
OVERLAY
docker run --rm --entrypoint /bench/envs/h2o/bin/python -v /opt/ac-nine-tests:/bench -v /opt/ac-candidate-tests:/opt/ac-candidate-tests:ro 632930644527.dkr.ecr.us-east-1.amazonaws.com/strands-decider-vllm@sha256:0bd44d374991dc8782b93d58bb41b3aab63fa0d242149578b342cb139f371d07 -c '"'"'import torch,transformers; print(torch.__version__,transformers.__version__)'"'"' > /opt/ac-nine-tests/logs/liquid-runtime-packages.txt
df -h / > /opt/ac-nine-tests/logs/storage.txt
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv > /opt/ac-nine-tests/logs/gpu.csv
aws s3 sync /opt/ac-nine-tests/logs s3://strands-decider-vllm-632930644527/output/ac-all-models/2026-10-30-full-v1/logs --only-show-errors'