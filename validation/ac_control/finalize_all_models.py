"""Collect read-only final runtime evidence before stopping the dedicated test GPU."""

import json
import shlex

from all_models_infra import BUCKET, PREFIX, REMOTE, submit
from all_models_protocol import PROVIDERS, ROOT, SOURCE_NAMES


def inventory():
    transferred = json.loads((ROOT / "runtime-transfer.json").read_text())
    for provider in PROVIDERS:
        meta = json.loads((ROOT / "results" / provider / "run.json").read_text())
        assert meta["status"] in ("complete", "complete_with_errors") and meta["calls"] == 2049
    code = "\n".join([
        "import hashlib,json,pathlib,subprocess,sysconfig,datetime",
        f"root=pathlib.Path({REMOTE!r})",
        "def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()",
        "def command(args):",
        " p=subprocess.run(args,capture_output=True,text=True,check=True,timeout=30)",
        " return p.stdout",
        "gpu=command(['nvidia-smi','--query-compute-apps=pid,process_name,used_memory','--format=csv,noheader'])",
        "assert not gpu.strip(),'Model still running after benchmark'",
        "assert all(not (root/'run'/name).exists() for name in ('references.json','spec_references.json','spec.md'))",
        "results={}",
        f"for provider in {list(PROVIDERS[2:])!r}:",
        " folder=root/'run/results'/provider",
        " meta=json.loads((folder/'run.json').read_text())",
        " assert meta['status'] in ('complete','complete_with_errors') and meta['calls']==2049",
        " results[provider]={p.name:sha(p) for p in folder.iterdir() if p.is_file()}",
        "models={}",
        "for folder in (root/'models').iterdir():",
        " if folder.name=='decider':",
        "  manifest=json.loads((folder/'decider/export.json').read_text())",
        "  files=[{'path':name,'sha256':value} for name,value in manifest['files_sha256'].items()]",
        " else:",
        "  manifest=json.loads((folder/'manifest.json').read_text()); files=manifest['files']",
        " checked={}",
        " for item in files:",
        "  path=folder/item['path']",
        "  if 'bytes' in item: assert path.stat().st_size==item['bytes'],str(path)",
        "  if path.suffix in ('.py','.sh','.json','.patch','.jinja','.toml') or path.name.endswith('SHA256SUMS'):",
        "   assert sha(path)==item['sha256'],str(path)",
        "   checked[item['path']]=item['sha256']",
        " models[folder.name]={'source_sha256_rechecked':checked}",
        "data={'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),",
        " 'reference_files_absent':True,'gpu_processes':gpu,'results_file_sha256':results,'models':models,",
        f" 'inference_sources':{{name:sha(root/'run'/name) for name in {list(SOURCE_NAMES)!r}}},",
        f" 'runtime_input_files':{{name:sha(root/'run'/name) for name in {list(transferred['files'])!r}}},",
        " 'gpu':command(['nvidia-smi','--query-gpu=name,memory.total,memory.used,driver_version','--format=csv']),",
        " 'disk':command(['df','-h',str(root)]),",
        " 'root_read_ahead_kb':pathlib.Path('/sys/block/nvme0n1/queue/read_ahead_kb').read_text().strip(),",
        " 'maintenance':command(['systemctl','show','apt-daily.service','apt-daily-upgrade.service',",
        " '--property=Id,LoadState,ActiveState,UnitFileState'])}",
        "(root/'logs/final-runtime-inventory.json').write_text(json.dumps(data,indent=2)+'\\n')",
        "print(json.dumps({'verified_models':len(models),'verified_local_runs':len(results),'gpu_empty':True}))",
    ])
    script = "\n".join([
        "set -eu",
        "python3 -c " + shlex.quote(code),
        "aws s3 sync " + REMOTE + "/logs s3://" + BUCKET + "/output/" + PREFIX + "/logs --only-show-errors",
    ])
    return submit("final-runtime-inventory", script, 600)


if __name__ == "__main__":
    print(json.dumps(inventory(), indent=2))
