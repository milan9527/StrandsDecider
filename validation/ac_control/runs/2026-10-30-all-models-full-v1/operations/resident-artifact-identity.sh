set -eu
python3 - <<'READ'
import subprocess,json,pathlib,hashlib
container=json.loads(subprocess.check_output(['docker','inspect','decider-vllm-service']))[0]
print(json.dumps({'image_id':container['Image'],'mounts':container['Mounts']},default=str))
for mount in container['Mounts']:
 if mount['Destination']=='/models/decider-vllm':
  path=pathlib.Path(mount['Source'])/'decider/export.json'
  print(json.dumps({'export_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'export':json.loads(path.read_text())}))
base=pathlib.Path('/opt/decider-open-models/h2o-env/lib/python3.12/site-packages')
packages={}
for package in ('torch','transformers','fastapi','uvicorn'):
 for path in base.glob(package+'-*.dist-info/METADATA'):
  packages[package]=next(line.split(': ',1)[1] for line in path.read_text().splitlines() if line.startswith('Version: '))
print(json.dumps({'resident_liquid_environment_packages':packages}))
READ