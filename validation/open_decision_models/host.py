"""Submit benchmark-container commands and files through the private bridge."""
import argparse
import base64
import io
import json
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTAINER = "open-decision-benchmark-20261029"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--upload", action="append", default=[], help="local_path=relative_path_under_bench")
    parser.add_argument("--shell")
    parser.add_argument("--detach", action="store_true")
    args = parser.parse_args()
    script = ""
    if args.upload:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            for specification in args.upload:
                source, target = specification.split("=", 1)
                if Path(target).is_absolute() or ".." in Path(target).parts:
                    raise ValueError("Upload target must stay inside /bench")
                data = Path(source).read_bytes()
                info = tarfile.TarInfo(target)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        script += f"import base64\ndocker('PUT','/containers/{CONTAINER}/archive?path=/bench',base64.b64decode({base64.b64encode(buffer.getvalue()).decode()!r}))\n"
    if args.shell:
        command = ["bash", "-lc", args.shell]
        if args.detach:
            script += f"eid=docker('POST','/containers/{CONTAINER}/exec',{{'Cmd':{command!r}}})['Id']\ndocker('POST','/exec/'+eid+'/start',{{'Detach':True}})\nprint('Detached',eid)\n"
        else:
            script += f"print('exit_code',execute({CONTAINER!r},{command!r}))\n"
    path = ROOT / ".deployment/open-host-command.py"
    path.write_text(script)
    subprocess.run(["python", str(Path(__file__).with_name("bridge.py")), "--script", str(path)], check=True)


if __name__ == "__main__":
    main()
