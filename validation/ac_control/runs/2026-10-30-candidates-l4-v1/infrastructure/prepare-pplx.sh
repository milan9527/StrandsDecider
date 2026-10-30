set -eu
candidate_root=/opt/ac-candidate-tests
mkdir -p "$candidate_root/models" "$candidate_root/envs" "$candidate_root/logs"
aws s3 sync s3://strands-decider-vllm-632930644527/input/ac-candidates/2026-10-30-l4-v1/models/ "$candidate_root/models/" --only-show-errors
python3 - <<'VERIFY'
import pathlib,json,hashlib
root=pathlib.Path('/opt/ac-candidate-tests/models')
results={}
for folder in sorted(root.iterdir()):
 manifest=json.loads((folder/'manifest.json').read_text());assert manifest['complete']
 for item in manifest['files']:
  path=folder/item['path'];assert path.stat().st_size==item['bytes']
  with path.open('rb') as stream: assert hashlib.file_digest(stream,'sha256').hexdigest()==item['sha256'],str(path)
 results[folder.name]={'revision':manifest['revision'],'verified_files':len(manifest['files'])}
(root.parent/'models-verified.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results))
VERIFY
export UV_CACHE_DIR="$candidate_root/uv-cache"
"$candidate_root/tools/bin/uv" venv --python /usr/bin/python3 "$candidate_root/envs/pplx"
"$candidate_root/tools/bin/uv" pip install --python "$candidate_root/envs/pplx/bin/python" -r "$candidate_root/models/pplx/requirements-fast.txt" accelerate fastapi uvicorn ninja packaging setuptools
"$candidate_root/tools/bin/uv" pip freeze --python "$candidate_root/envs/pplx/bin/python" > "$candidate_root/logs/pplx-requirements.txt"
"$candidate_root/envs/pplx/bin/python" -c 'import torch,transformers,fla; print(torch.__version__,torch.version.cuda,transformers.__version__); print(torch.cuda.get_device_name())'
