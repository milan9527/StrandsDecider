"""Paired sequential HTTP evaluation; test references are never loaded here."""
import argparse
import hashlib
import json
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import torch
import transformers

from worker import Native, adapter_state, load_adapter, merge, request_for, save, sha


def choices(raw):
    return {k: a["choice"] for k, a in raw["answers"].items()}


def serve(root, model_path):
    selection = json.loads((root / "training/selection.json").read_text())
    selected = root / "training" / selection["selected"]["path"]
    assert sha(selected) == selection["selected"]["sha256"]
    models = {"base": Native(model_path), "lora": Native(model_path, lora=True)}
    tuned = models["lora"]
    load_adapter(tuned.model, selected)
    # Newly injected modules default to training=True even under an eval parent.
    # Disable LoRA dropout before checking persisted inference outputs.
    tuned.model.eval()
    template = json.loads((root / "template.json").read_text())
    probes = json.loads((root / "dev.json").read_text())[:8]
    # Fresh process has just loaded the persisted adapter. Check a second load.
    before = [tuned.infer(request_for(template, row)) for row in probes]
    load_adapter(tuned.model, selected)
    after = [tuned.infer(request_for(template, row)) for row in probes]
    assert all(a["answers"] == b["answers"] for a, b in zip(before, after))
    merge(tuned.model)
    for native in models.values():
        native.model.eval()
        native.model.fuse_projections()
    merged = [tuned.infer(request_for(template, row)) for row in probes]
    verification = {
        "reload_equal": True,
        "merge_choice_changes": [
            {"id": row["id"], "unmerged": choices(a), "merged": choices(b)}
            for row, a, b in zip(probes, after, merged) if choices(a) != choices(b)
        ],
        "merge_max_probability_difference": max(
            abs(a["answers"][key]["probabilities"][c] - b["answers"][key]["probabilities"][c])
            for a, b in zip(after, merged) for key in a["answers"]
            for c in a["answers"][key]["probabilities"]),
        "selected": selection["selected"], "dev_probe_ids": [r["id"] for r in probes],
        "note": "All formal tuned results use merged BF16 weights, including any numerical merge changes.",
    }
    save(root / "evaluation/reload-merge.json", verification)
    metadata = {"ready": True, "model": "LiquidAI/d1-2B", "selected": selection["selected"],
                "torch": torch.__version__, "transformers": transformers.__version__, "dtype": "BF16",
                "server_sha256": sha(Path(__file__)), "worker_sha256": sha(Path(__file__).with_name("worker.py")),
                "outer_concurrency": 1, "two_variants_resident": True,
                "model_source_sha256": {p.name: sha(p) for p in model_path.glob("*.py")},
                "weight_sha256": sha(model_path / "model.safetensors"),
                "readout": "Unchanged official system_one; no postprocessing except omit removal offline"}
    save(root / "evaluation/server.json", metadata)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_json(metadata, 200)

        def send_json(self, value, status):
            data = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            try:
                variant = self.path.strip("/")
                assert variant in models
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                started = time.perf_counter()
                raw = models[variant].infer(payload)
                torch.cuda.synchronize()
                raw["sdk_ms"] = (time.perf_counter()-started)*1000
                self.send_json(raw, 200)
            except Exception as e:
                self.send_json({"error": type(e).__name__, "detail": str(e)}, 500)
    print("EVALUATION_SERVER_READY", flush=True)
    HTTPServer(("127.0.0.1", 18821), Handler).serve_forever()


def call(request, variant):
    encoded = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode()
    started = time.perf_counter()
    status, error, raw = "ok", None, None
    try:
        with urllib.request.urlopen(
            urllib.request.Request(f"http://127.0.0.1:18821/{variant}", data=encoded,
                                   headers={"Content-Type": "application/json"}), timeout=180
        ) as response:
            raw = json.load(response)
        got = choices(raw)
        assert set(got) == set(request["questions"])
        assert all(v in request["questions"][k]["criteria"] for k, v in got.items())
    except Exception as e:
        status, error = "error", str(e)
    elapsed = (time.perf_counter()-started)*1000
    return {"input_sha256": hashlib.sha256(encoded).hexdigest(), "started_perf": started,
            "finished_perf": time.perf_counter(), "http_ms": elapsed, "raw": raw,
            "status": status, "error": error}


def run(root):
    out = root / "evaluation"
    out.mkdir(exist_ok=True)
    receipt_path = out / "receipts.jsonl"
    assert not receipt_path.exists(), "Do not repeat evaluation"
    template = json.loads((root / "template.json").read_text())
    heldout = json.loads((root / "test-inputs.json").read_text())
    assert all(set(r) == {"id", "query", "language"} for r in heldout)
    historical = json.loads((root / "historical-cases.json").read_text())
    schedule = []
    for row in heldout:
        for order in ("original", "reversed"):
            req = request_for(template, row, reverse=order == "reversed")
            schedule.append({"id": row["id"], "dataset": "heldout", "language": row["language"],
                             "order": order, "kind": "quality", "layout": "full30", "request": req})
    for row in historical:
        schedule.append({"id": row["case_id"], "dataset": row["dataset"], "order": row["order"],
                         "kind": "quality", "layout": "full30", "request": row["payload"]})
    spec = [r for r in historical if r["dataset"] == "spec" and r["order"] == "original"]
    assert len(spec) == 20
    for repetition in range(3):
        for row in spec:
            layouts = ("serial30", "full30") if (repetition + int(row["case_id"][1:])) % 2 else ("full30", "serial30")
            for layout in layouts:
                schedule.append({"id": row["case_id"], "dataset": "spec", "order": "original",
                                 "kind": "performance", "layout": layout, "repetition": repetition,
                                 "request": row["payload"]})
    save(out / "schedule.json", schedule)
    errors, count = [], 0
    with receipt_path.open("w") as f:
        def execute(job, variant):
            nonlocal count
            req = job["request"]
            record = {k: v for k, v in job.items() if k != "request"}
            record.update(variant=variant, calls=[])
            started = time.perf_counter()
            try:
                if job["layout"] == "serial30":
                    for key, question in req["questions"].items():
                        response = call({"state": req["state"], "questions": {key: question}}, variant)
                        response["key"] = key
                        record["calls"].append(response)
                        if response["status"] != "ok":
                            raise RuntimeError(response["error"])
                else:
                    response = call(req, variant)
                    record["calls"].append(response)
                    if response["status"] != "ok":
                        raise RuntimeError(response["error"])
                record["wall_ms"] = (time.perf_counter()-started)*1000
                record["status"] = "ok"
            except Exception as e:
                record.update(status="error", error=str(e), wall_ms=(time.perf_counter()-started)*1000)
                errors.append({k:v for k,v in record.items() if k != "calls"})
            count += 1
            f.write(json.dumps(record, ensure_ascii=False)+"\n")
            f.flush()
            if count % 20 == 0:
                save(out / "progress.json", {"completed_tasks": count, "errors": len(errors),
                                             "id": job["id"], "kind": job["kind"]})
                print(json.dumps({"completed_tasks": count, "id": job["id"], "kind": job["kind"]}), flush=True)
        for layout in ("serial30", "full30"):
            for variant in ("base", "lora"):
                execute({"id": spec[0]["case_id"], "dataset": "spec", "order": "original",
                         "kind": "warmup", "layout": layout, "request": spec[0]["payload"]}, variant)
        for index, job in enumerate(schedule):
            for variant in (("base", "lora") if index % 2 == 0 else ("lora", "base")):
                execute(job, variant)
    save(out / "complete.json", {"tasks": count, "expected_tasks": len(schedule)*2+4,
                                 "errors": errors, "automatic_retries": 0,
                                 "server_alive": True})
    print("EVALUATION_COMPLETE", count, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["serve", "run"])
    parser.add_argument("--root", type=Path, default=Path("/opt/ac-liquid-lora"))
    parser.add_argument("--model", type=Path, default=Path("/opt/ac-input-tests/models/liquid"))
    args = parser.parse_args()
    serve(args.root, args.model) if args.phase == "serve" else run(args.root)
