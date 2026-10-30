"""Run short Docker-control tasks on the existing non-vLLM GPU host."""
import argparse
import json
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".deployment/open-decision-host.json"
INSTANCE = "i-0daca64f56056aa1c"
CLUSTER = "strands-decider-demo"
REGION = "us-east-1"

PRELUDE = '''
import http.client, json, socket
class Docker(http.client.HTTPConnection):
    def __init__(self):
        super().__init__("localhost", timeout=180)
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(180)
        self.sock.connect("/var/run/docker.sock")
def docker(method, path, value=None):
    c = Docker()
    raw = value if isinstance(value, bytes) else json.dumps(value).encode() if value is not None else None
    c.request(method, "/v1.43" + path, raw, {
        "Content-Type": "application/x-tar" if isinstance(value, bytes) else "application/json"})
    r = c.getresponse(); data = r.read()
    if r.status >= 300:
        raise RuntimeError(f"Docker {r.status}: {data.decode()[:800]}")
    try: return json.loads(data) if data else None
    except (ValueError, UnicodeDecodeError): return data
def execute(container, command):
    eid = docker("POST", f"/containers/{container}/exec", {
        "AttachStdout": True, "AttachStderr": True, "Tty": True, "Cmd": command})["Id"]
    data = docker("POST", f"/exec/{eid}/start", {"Detach": False, "Tty": True})
    print(data.decode(errors="replace") if isinstance(data, bytes) else json.dumps(data), flush=True)
    return docker("GET", f"/exec/{eid}/json")["ExitCode"]
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", type=Path)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    ecs = boto3.client("ecs", region_name=REGION)
    if args.status:
        state = json.loads(STATE.read_text())
        task = ecs.describe_tasks(cluster=CLUSTER, tasks=[state["task"]])["tasks"][0]
        print(json.dumps({"status": task["lastStatus"], "stop": task.get("stoppedReason"),
                          "containers": [{k: c.get(k) for k in ["name", "exitCode", "reason"]}
                                         for c in task["containers"]]}))
        logs = boto3.client("logs", region_name=REGION)
        stream = "open-decisions/control/" + state["task"].split("/")[-1]
        try:
            for e in logs.get_log_events(logGroupName=state["log_group"],
                                        logStreamName=stream, startFromHead=True)["events"]:
                print(e["message"])
        except logs.exceptions.ResourceNotFoundException:
            print("Log stream not ready")
        return
    if not args.script:
        parser.error("--script required")
    source = ecs.describe_task_definition(
        taskDefinition="strands-decider-demo-gpu-model:3")["taskDefinition"]
    original = source["containerDefinitions"][0]
    definition = ecs.register_task_definition(
        family="strands-open-decision-control", networkMode="host",
        requiresCompatibilities=["EC2"], executionRoleArn=source["executionRoleArn"],
        volumes=[{"name": "docker", "host": {"sourcePath": "/var/run/docker.sock"}}],
        containerDefinitions=[{
            "name": "control", "image": original["image"], "cpu": 64, "memory": 256,
            "user": "0", "essential": True, "entryPoint": ["python", "-u", "-c"],
            "command": [PRELUDE + "\n" + args.script.read_text()],
            "mountPoints": [{"sourceVolume": "docker", "containerPath": "/var/run/docker.sock"}],
            "logConfiguration": {**original["logConfiguration"], "options": {
                **original["logConfiguration"]["options"],
                "awslogs-stream-prefix": "open-decisions"}},
        }],
    )["taskDefinition"]["taskDefinitionArn"]
    response = ecs.run_task(
        cluster=CLUSTER, taskDefinition=definition, launchType="EC2", count=1,
        placementConstraints=[{"type": "memberOf", "expression": f"ec2InstanceId == {INSTANCE}"}],
        startedBy="open-decision-validation",
    )
    if response.get("failures"):
        raise RuntimeError(response["failures"])
    state = {"instance": INSTANCE, "task": response["tasks"][0]["taskArn"],
             "task_definition": definition, "image": original["image"],
             "log_group": original["logConfiguration"]["options"]["awslogs-group"]}
    STATE.write_text(json.dumps(state, indent=2))
    print(json.dumps(state))


if __name__ == "__main__":
    main()
