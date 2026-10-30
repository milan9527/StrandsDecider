set -eu
python3 - <<'DATA'
import json
from pathlib import Path
p=Path('/opt/ac-candidate-tests/run/results/torchcast/receipts.jsonl')
rows=[json.loads(x) for x in p.read_text().splitlines()]
print(json.dumps([{'kind':r['kind'],'case':r['case_id'],'client_ms':r['client_ms'],'usage':r.get('response',{}).get('usage'),'timing':r.get('response',{}).get('benchmark_timing')} for r in rows[:7]],indent=2))
DATA
