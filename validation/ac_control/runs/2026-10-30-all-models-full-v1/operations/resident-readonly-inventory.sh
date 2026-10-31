set -eu
systemctl show decider-vllm decider-liquid decider-h2o --property=Id,ActiveState,NRestarts,ExecMainStartTimestamp
python3 - <<'READ'
import json,subprocess,os
from pathlib import Path
for item in json.loads(subprocess.check_output(['docker','ps','--format','{{json .}}']).decode().replace('}\n{','},{').join(['[',']'])):
 print(json.dumps({k:item.get(k) for k in ('Names','Image','Status')}))
for name in ['decider-vllm:service']:
 info=json.loads(subprocess.check_output(['docker','image','inspect',name]))[0]
 print(json.dumps({'image':name,'id':info['Id'],'size':info['Size']}))
for base in ['/opt/decider-vllm','/opt/decider-open-models','/opt/strands-decider']:
 p=Path(base)
 if p.exists(): print(base, sorted(x.name for x in p.iterdir()))
READ
