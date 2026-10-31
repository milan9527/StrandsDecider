set -eu
python3 - <<'CHECK'
import json,pathlib,subprocess
base=pathlib.Path('/opt/ac-candidate-tests')
print(json.dumps({'candidate_root':base.exists(),'nine_root':pathlib.Path('/opt/ac-nine-tests').exists(),'models':[p.name for p in (base/'models').iterdir()] if (base/'models').exists() else [],'envs':[p.name for p in (base/'envs').iterdir()] if (base/'envs').exists() else []}))
for cmd in [['nvidia-smi','--query-gpu=name,memory.total,driver_version','--format=csv'],['nvidia-smi','--query-compute-apps=pid,process_name,used_memory','--format=csv'],['df','-h','/'],['systemctl','list-timers','--all','--no-pager'],['docker','images','--format','{{.Repository}} {{.Tag}} {{.ID}}']]:
 p=subprocess.run(cmd,capture_output=True,text=True);print(p.stdout);print(p.stderr)
CHECK
