set -eu
systemctl restart ac-input-autostop.timer
python3 - <<'PYREMOTE'
import json,pathlib
root=pathlib.Path('/opt/ac-input-tests/run')
for path in sorted(root.glob("profiles/*/results/*/run.json")):
 data=json.loads(path.read_text());print(str(path.relative_to(root)),json.dumps({k:data.get(k) for k in ("status","calls","errors","last")}))
PYREMOTE
nvidia-smi --query-gpu=name,memory.used,utilization.gpu --format=csv
systemctl list-timers ac-input-autostop.timer --no-pager