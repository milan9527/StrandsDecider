bash -c 'set -euo pipefail
test -d /opt/ac-candidate-tests/models
test ! -d /opt/ac-input-tests
mkdir -p /opt/ac-input-tests/run /opt/ac-input-tests/logs /opt/ac-input-tests/models
systemctl stop apt-daily.timer apt-daily-upgrade.timer fwupd-refresh.timer update-notifier-download.timer || true
systemctl mask --runtime apt-daily.service apt-daily-upgrade.service fwupd-refresh.service update-notifier-download.service
shutdown -c || true
systemd-run --unit=ac-input-autostop --on-active=12h /sbin/shutdown -h now
test -z "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)"
ln -s /opt/ac-candidate-tests/envs /opt/ac-input-tests/envs
ln -s /opt/ac-candidate-tests/cache /opt/ac-input-tests/cache
cp /opt/ac-candidate-tests/models-verified.json /opt/ac-input-tests/models-verified.json
cp /opt/ac-candidate-tests/logs/*requirements.txt /opt/ac-input-tests/logs/
cp /opt/ac-candidate-tests/logs/h2o-overlay-verification.json /opt/ac-input-tests/logs/
ln -s /opt/ac-candidate-tests/models/pplx /opt/ac-input-tests/models/pplx
ln -s /opt/ac-candidate-tests/models/knowline /opt/ac-input-tests/models/knowline
ln -s /opt/ac-candidate-tests/models/torchcast /opt/ac-input-tests/models/torchcast
ln -s /opt/ac-candidate-tests/models/clef /opt/ac-input-tests/models/clef
ln -s /opt/ac-candidate-tests/models/h2o /opt/ac-input-tests/models/h2o
aws s3 cp s3://strands-decider-vllm-632930644527/input/ac-input-optimization/2026-10-31-nine-v1/runtime-input.tar.gz /opt/ac-input-tests/runtime-input.tar.gz --only-show-errors
python3 - <<'"'"'CHECK'"'"'
import hashlib,tarfile,pathlib
path='"'"'/opt/ac-input-tests/runtime-input.tar.gz'"'"'
assert hashlib.sha256(open(path,'"'"'rb'"'"').read()).hexdigest()=='"'"'03280f4a8e18c01b8d048f7f8d03298a5e7cac0ef4cc4b4874f174bf582944eb'"'"'
with tarfile.open(path) as archive:
 assert all(m.isfile() and not pathlib.PurePosixPath(m.name).is_absolute() and '"'"'..'"'"' not in pathlib.PurePosixPath(m.name).parts for m in archive.getmembers())
 archive.extractall('"'"'/opt/ac-input-tests/run'"'"',filter='"'"'data'"'"')
CHECK
/opt/ac-candidate-tests/tools/bin/uv venv --python /usr/bin/python3 /opt/ac-input-tests/runner-env
/opt/ac-candidate-tests/tools/bin/uv pip install --python /opt/ac-input-tests/runner-env/bin/python boto3 httpx
aws s3 sync s3://strands-decider-vllm-632930644527/input/model/ /opt/ac-input-tests/models/decider --only-show-errors
aws s3 sync s3://strands-decider-vllm-632930644527/input/ac-all-models/2026-10-30-full-v1/models/liquid/ /opt/ac-input-tests/models/liquid --only-show-errors
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 632930644527.dkr.ecr.us-east-1.amazonaws.com
docker pull 632930644527.dkr.ecr.us-east-1.amazonaws.com/strands-decider-vllm@sha256:0bd44d374991dc8782b93d58bb41b3aab63fa0d242149578b342cb139f371d07
docker logout 632930644527.dkr.ecr.us-east-1.amazonaws.com
docker image inspect 632930644527.dkr.ecr.us-east-1.amazonaws.com/strands-decider-vllm@sha256:0bd44d374991dc8782b93d58bb41b3aab63fa0d242149578b342cb139f371d07 --format '"'"'{{.Id}}'"'"' > /opt/ac-input-tests/logs/strands-image-id.txt
docker run --rm --memory=4g -v /opt/ac-input-tests/models/decider:/models/decider-vllm:ro 632930644527.dkr.ecr.us-east-1.amazonaws.com/strands-decider-vllm@sha256:0bd44d374991dc8782b93d58bb41b3aab63fa0d242149578b342cb139f371d07 verify-artifacts --model /models/decider-vllm > /opt/ac-input-tests/logs/strands-model-integrity.json
python3 - <<'"'"'VERIFY'"'"'
import hashlib,json,pathlib
base=pathlib.Path('"'"'/opt/ac-input-tests/models'"'"')
result={}
for name in ['"'"'liquid'"'"','"'"'pplx'"'"','"'"'knowline'"'"','"'"'torchcast'"'"','"'"'clef'"'"','"'"'h2o'"'"']:
 manifest=json.loads((base/name/'"'"'manifest.json'"'"').read_text())
 for item in manifest['"'"'files'"'"']:
  path=base/name/item['"'"'path'"'"']; h=hashlib.sha256()
  with path.open('"'"'rb'"'"') as f:
   for chunk in iter(lambda:f.read(4*1024*1024),b'"'"''"'"'):h.update(chunk)
  assert h.hexdigest()==item['"'"'sha256'"'"'],str(path)
 result[name]={'"'"'revision'"'"':manifest['"'"'revision'"'"'],'"'"'verified_files'"'"':len(manifest['"'"'files'"'"'])}
 print(name,result[name],flush=True)
pathlib.Path('"'"'/opt/ac-input-tests/logs/model-verification.json'"'"').write_text(json.dumps(result,indent=2))
VERIFY
/opt/ac-candidate-tests/envs/h2o/bin/python - <<'"'"'OVERLAY'"'"'
import hashlib,json,pathlib,sysconfig
expected=json.loads(pathlib.Path('"'"'/opt/ac-input-tests/logs/h2o-overlay-verification.json'"'"').read_text())
site=pathlib.Path(sysconfig.get_paths()['"'"'purelib'"'"'])
assert len(expected)==30
assert all(hashlib.sha256((site/name).read_bytes()).hexdigest()==sha for name,sha in expected.items())
pathlib.Path('"'"'/opt/ac-input-tests/logs/h2o-overlay-rechecked.json'"'"').write_text(json.dumps(expected,indent=2))
OVERLAY
df -h / > /opt/ac-input-tests/logs/storage.txt
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv > /opt/ac-input-tests/logs/gpu.csv
aws s3 sync /opt/ac-input-tests/logs s3://strands-decider-vllm-632930644527/output/ac-input-optimization/2026-10-31-nine-v1/logs --only-show-errors'