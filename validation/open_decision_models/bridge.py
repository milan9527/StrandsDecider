"""Temporary private-S3 command channel to the selected Docker control task."""
import argparse
import contextlib
import io
import json
import time
import uuid
from pathlib import Path

import boto3
from botocore.config import Config
from cloud import ROOT

BUCKET = "strands-decider-tetris-training-632930644527"
STATE = ROOT / ".deployment/open-benchmark-bridge.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--script", type=Path)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    s3 = boto3.client("s3", region_name="us-east-1", config=Config(signature_version="s3v4"))
    if args.start:
        import subprocess
        prefix = "open-decision-models-20261029/control/" + uuid.uuid4().hex
        state = {"command": prefix + "/command.json", "result": prefix + "/result.json"}
        s3.put_object(Bucket=BUCKET, Key=state["command"], Body=b'{"id":"initial","script":"pass"}')
        get = s3.generate_presigned_url("get_object", Params={"Bucket": BUCKET, "Key": state["command"]}, ExpiresIn=86400)
        put = s3.generate_presigned_url("put_object", Params={"Bucket": BUCKET, "Key": state["result"]}, ExpiresIn=86400)
        script = ROOT / ".deployment/open-bridge-worker.py"
        script.write_text(f"""
import urllib.request, contextlib, io, traceback, time
last = None
deadline = time.monotonic() + 14400
while time.monotonic() < deadline:
    try:
        job = json.load(urllib.request.urlopen({get!r}, timeout=20))
        if job['id'] != last:
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                try:
                    if job.get('stop'): break
                    exec(compile(job['script'], '<benchmark-control>', 'exec'), globals())
                    ok = True
                except Exception:
                    traceback.print_exc()
                    ok = False
            last = job['id']
            result = json.dumps({{'id': job['id'], 'ok': ok, 'output': output.getvalue()}}).encode()
            urllib.request.urlopen(urllib.request.Request({put!r}, data=result, method='PUT'), timeout=30).read()
            last = job['id']
    except Exception as exc:
        print(type(exc).__name__, getattr(exc, "code", None), exc.read().decode()[:600] if hasattr(exc, "read") else "", flush=True)
    time.sleep(2)
""")
        STATE.write_text(json.dumps(state, indent=2))
        subprocess.run(["python", str(Path(__file__).with_name("cloud.py")), "--script", str(script)], check=True)
        return
    state = json.loads(STATE.read_text())
    if args.script or args.stop:
        job = {"id": uuid.uuid4().hex, "script": args.script.read_text() if args.script else "",
               "stop": args.stop}
        s3.put_object(Bucket=BUCKET, Key=state["command"], Body=json.dumps(job).encode())
        state["last_job"] = job["id"]
        STATE.write_text(json.dumps(state, indent=2))
        print("Submitted", job["id"])
    if args.status:
        try:
            result = json.loads(s3.get_object(Bucket=BUCKET, Key=state["result"])["Body"].read())
            if result["id"] != state.get("last_job"):
                print("Pending")
            else:
                print("ok:", result["ok"])
                print(result["output"])
        except s3.exceptions.NoSuchKey:
            print("Pending")


if __name__ == "__main__":
    main()
