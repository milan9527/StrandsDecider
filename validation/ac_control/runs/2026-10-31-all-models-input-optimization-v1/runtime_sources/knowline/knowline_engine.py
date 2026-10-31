"""Decision Index engine for KnowLine (PelaAI): the model repo's `knowline_server.py` front end, in process (Gen5.5: read twice).

One command, no server to start by hand:

    # default: the setting of our submitted runs. Starts SGLang with the flags of serve_knowline.sh (FP8 at load) on a
    # free local port, scores through it, and stops it when the run ends.
    python -m decision_index pipeline --engine knowline_engine:KnowLine \\
        --option model=PelaAI/KnowLine-4B-Gen5.5 --option revision=<commit> --out runs/KnowLine-4B-Gen5.5

    # without SGLang: transformers only, bf16 (slower; not the setting of our runs)
    ... --option backend=hf

Put this file, `knowline_server.py` and `knowline_layout.py` (all in the model repo) on PYTHONPATH, e.g. run from a clone
of the model repo.
Requirements: `transformers` and `requests`; `sglang==0.5.21` for the default backend, `torch` for backend=hf.
Options: model, revision, backend (sglang | hf), gpu (CUDA device for SGLang; default: as CUDA_VISIBLE_DEVICES), mem (0.72), port (free one),
temperature (1.0), workers (16), read_twice (1 = the setting of our runs; 0 = the previous prompts), twice_max_tokens
(3000), startup_timeout (s, 1800), sglang_python (interpreter with SGLang installed, if it is
not the one running the kit), device (backend=hf: torch device or device map, default auto / cuda).
Licence of this file: MIT.
"""

import atexit
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from decision_index.engines.base import Engine, Unsupported

sys.path.insert(0, str(Path(__file__).resolve().parent))
import knowline_server as ks  # noqa: E402

SGLANG_FLAGS = ["--served-model-name", "m", "--tp", "1", "--quantization", "fp8", "--mamba-radix-cache-strategy",
                "extra_buffer", "--enable-fp32-lm-head"]


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class KnowLine(Engine):
    name = "knowline"
    latency = ("In-process request wall time through knowline_server's KnowLine engine (rendering + one prefill per "
               "question), against a local SGLang server for backend=sglang; excludes model loading and server startup.")

    def __init__(self, model, revision=None, backend="sglang", gpu=None, mem=0.72, port=None, temperature=1.0,
                 workers=16, startup_timeout=1800, sglang_python=None, device=None, read_twice=1, twice_max_tokens=3000,
                 **options):
        super().__init__(**options)
        import requests
        import transformers
        from transformers import AutoTokenizer

        path = model
        if not Path(model).exists():  # a Hub repo id: pin the files once so SGLang and the tokenizer read the same ones
            from huggingface_hub import snapshot_download
            path = snapshot_download(model, revision=revision)
        self.model_id, self.backend_name, self.server = model, backend, None
        tok = AutoTokenizer.from_pretrained(path)
        if backend == "sglang":
            port = int(port or _free_port())
            env = dict(os.environ)
            if gpu is not None:
                env["CUDA_VISIBLE_DEVICES"] = str(gpu)
            cmd = [sglang_python or sys.executable, "-m", "sglang.launch_server", "--model-path", path, *SGLANG_FLAGS,
                   "--mem-fraction-static", str(mem), "--port", str(port)]
            self.server = subprocess.Popen(cmd, env=env, start_new_session=True)
            atexit.register(self.close)
            url, deadline = f"http://127.0.0.1:{port}", time.time() + float(startup_timeout)
            while True:
                if self.server.poll() is not None:
                    raise RuntimeError(f"SGLang exited with code {self.server.returncode} before becoming healthy")
                try:
                    if requests.get(f"{url}/health", timeout=3).status_code == 200:
                        break
                except requests.RequestException:
                    pass
                if time.time() > deadline:
                    raise RuntimeError("SGLang did not become healthy in time")
                time.sleep(5)
            back = ks.SGLang(url)
        elif backend == "hf":
            back = ks.HF(path, device=device)
        else:
            raise ValueError("backend must be 'sglang' or 'hf'")
        layout = None
        if int(read_twice):
            from knowline_layout import Layout
            layout = Layout(read_twice=True, twice_max_tokens=int(twice_max_tokens))
        self.engine = ks.KnowLine(tok, back, float(temperature), int(workers), {}, layout)
        self.provenance = {
            "kind": f"knowline_server.KnowLine in process, backend {backend}",
            "repo": model, "revision": revision, "front_end": "knowline_server.py (chat style, label-token softmax, "
            f"temperature {temperature}, {workers} scoring threads, no calibration file, "
            + (f"read twice up to {int(twice_max_tokens)} tokens)" if layout else "read once)"),
            "sglang": " ".join(SGLANG_FLAGS + ["--mem-fraction-static", str(mem)]) if backend == "sglang" else None,
            "transformers": transformers.__version__,
            "policy": f"Unmodified state and questions; up to {ks.MAX_QUESTIONS} questions per request and "
                      f"{ks.MAX_LABELS} options per question, larger requests are unsupported, nothing is truncated.",
        }

    def __call__(self, state, questions):
        if len(questions) > ks.MAX_QUESTIONS:
            raise Unsupported(f"{len(questions)} questions; at most {ks.MAX_QUESTIONS} per request")
        try:
            answers, usage = self.engine.run(state, questions)
        except ValueError as exc:
            if any(k in str(exc) for k in ("criteria", "levels", "options", "questions")):
                raise Unsupported(str(exc)) from exc
            raise
        return {"model": self.model_id, "answers": answers, "usage": usage}, None

    def runtime(self):
        info = {"backend": self.backend_name}
        try:
            import torch
            info.update(torch=torch.__version__, cuda=torch.version.cuda)
            if torch.cuda.is_available():
                info["gpu"] = torch.cuda.get_device_name()
        except ImportError:
            pass
        if self.backend_name == "sglang":
            try:
                import sglang
                info["sglang"] = sglang.__version__
            except Exception:  # noqa: BLE001 - version is informational
                pass
        return info

    def close(self):
        if self.server is not None and self.server.poll() is None:
            try:
                os.killpg(self.server.pid, signal.SIGTERM)
                self.server.wait(timeout=60)
            except Exception:  # noqa: BLE001 - make sure the server does not outlive the run
                try:
                    os.killpg(self.server.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        self.server = None
