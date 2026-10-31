set -eu
test -z "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)"
python3 - <<'PYCODE'
import json,shutil,hashlib
from pathlib import Path
root=Path('/opt/ac-nine-tests')
source=root/'run/results/knowline'
meta=json.loads((source/'run.json').read_text())
health=json.loads((source/'health_before.json').read_text())
assert meta['calls']==0 and meta['errors']==0
assert not (source/'receipts.jsonl').exists()
assert health['status']=='ok' and health['response']['model']=='m'
target=root/'run/attempts/knowline-health-alias/results/knowline'
assert not target.exists()
target.parent.mkdir(parents=True)
source.rename(target)
record={'reason':'Health returned routing alias m instead of the pinned repository name','decision_calls':0,'warmup_calls':0,'formal_calls':0,'health':health,'run':meta}
(root/'run/attempts/knowline-health-alias/attempt.json').write_text(json.dumps(record,indent=2))
for name in ('knowline-health-startup.json','knowline-nine-models-startup.log','knowline-complete.log'):
 p=root/'logs'/name
 if p.exists():shutil.copy2(p,root/'run/attempts/knowline-health-alias'/name)
server=root/'models/knowline/knowline_server.py'
lines=server.read_text().splitlines()
for i,line in enumerate(lines):
 if 'served_model' in line or 'served-model' in line or '"model"' in line:
  print(f'{i+1}: '+line)
print(json.dumps({'archived':str(target),'decision_calls':meta['calls'],'server_sha256':hashlib.sha256(server.read_bytes()).hexdigest()}))

PYCODE
aws s3 sync /opt/ac-nine-tests/run/attempts/knowline-health-alias s3://strands-decider-vllm-632930644527/output/ac-all-models/2026-10-30-full-v1/attempts/knowline-health-alias --only-show-errors