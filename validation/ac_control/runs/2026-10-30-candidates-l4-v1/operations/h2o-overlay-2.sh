set -eu
/opt/ac-candidate-tests/envs/h2o/bin/python - <<'PYTHON'
import hashlib,sysconfig,urllib.request,json
from pathlib import Path
root=Path('/opt/ac-candidate-tests')
site=Path(sysconfig.get_paths()['purelib'])
verified={}
for line in (root/'models/h2o/engine/vllm_per_request_attention.SHA256SUMS').read_text().splitlines():
 digest,name=line.split()
 url='https://raw.githubusercontent.com/h2oai/vllm/b05cc29ab813895947954c268c4ec41ca0da1306/'+name
 with urllib.request.urlopen(url,timeout=45) as response: data=response.read()
 assert hashlib.sha256(data).hexdigest()==digest,name
 target=site/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);verified[name]=digest
assert len(verified)==30
(root/'logs/h2o-overlay-verification.json').write_text(json.dumps(verified,indent=2))
print('Verified 30 official overlays')
PYTHON
