"""Temporary ECS installer: operate only the named vision container on the selected host."""

import hashlib
import http.client
import json
import os
import socket
import time
import urllib.error
import urllib.request


class Docker(http.client.HTTPConnection):
    def __init__(self):
        super().__init__("localhost", timeout=180)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(180)
        self.sock.connect("/var/run/docker.sock")


def call(method, path, value=None):
    conn = Docker()
    payload = value if isinstance(value, bytes) else json.dumps(value) if value is not None else None
    conn.request(method, "/v1.43" + path, payload, {
        "Content-Type": "application/x-tar" if isinstance(value, bytes) else "application/json",
    })
    response = conn.getresponse()
    data = response.read()
    if response.status >= 300:
        raise RuntimeError(f"Docker {response.status}: {data.decode()[:500]}")
    return json.loads(data) if data else None


name = os.environ["VISION_CONTAINER"]
if any("/" + name in c["Names"] for c in call("GET", "/containers/json?all=true")):
    raise RuntimeError("Named vision container already exists; inspect it before replacing")
with urllib.request.urlopen(os.environ["BUNDLE_URL"], timeout=120) as stream:
    archive = stream.read()
assert hashlib.sha256(archive).hexdigest() == os.environ["BUNDLE_SHA256"]
container = call("POST", "/containers/create?name=" + name, {
    "Image": os.environ["MODEL_IMAGE"], "User": "0", "WorkingDir": "/srv/vision",
    "Entrypoint": ["python", "-u", "/srv/vision/vision_bootstrap.py"], "Cmd": [],
    "Labels": {"project": "StrandsDecider", "component": "vision", "version": name},
    "HostConfig": {
        "Binds": [f"/opt/decider-cache/{name}:/srv/vision"], "NetworkMode": "host",
        "Memory": 8 * 1024**3, "NanoCpus": 2_000_000_000,
        "DeviceRequests": [{"Driver": "nvidia", "Count": -1, "Capabilities": [["gpu"]]}],
        "RestartPolicy": {"Name": "unless-stopped"},
        "LogConfig": {"Type": "json-file", "Config": {"max-size": "20m", "max-file": "2"}},
    },
})["Id"]
print(json.dumps({"event": "created", "container": container}), flush=True)
success = False
try:
    call("PUT", f"/containers/{container}/archive?path=/srv/vision", archive)
    call("POST", f"/containers/{container}/start")
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        state = call("GET", f"/containers/{container}/json")
        if state["RestartCount"] > 1:
            raise RuntimeError("Vision service repeatedly exited during startup")
        try:
            with urllib.request.urlopen("http://127.0.0.1:18123/health", timeout=3) as response:
                health = json.load(response)
            assert health["vision"] and health["model"].endswith("-vision")
            print(json.dumps({"event": "ready", "container": container, "health": health}), flush=True)
            success = True
            break
        except (urllib.error.URLError, TimeoutError):
            time.sleep(5)
    if not success:
        raise TimeoutError("Vision service did not become ready in ten minutes")
finally:
    if not success:
        call("DELETE", f"/containers/{container}?force=true")
