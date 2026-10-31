python3 - <<'CHECK'
import json,pathlib
root=pathlib.Path('/opt/ac-input-tests/run')
for p in sorted(root.glob("profiles/*/results/*/run.json")):
 d=json.loads(p.read_text());print(str(p.relative_to(root)),json.dumps({k:d.get(k) for k in ("status","calls","errors","last","started_at","finished_at")},ensure_ascii=False))
CHECK
nvidia-smi --query-gpu=name,memory.used,utilization.gpu --format=csv