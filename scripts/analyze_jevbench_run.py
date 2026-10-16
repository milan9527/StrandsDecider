"""Audit a saved run and export aggregates without publishing per-item benchmark text."""

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--harness", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    args = parser.parse_args()
    run, harness, out = args.run.resolve(), args.harness.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if (out / "verification.json").exists():
        raise ValueError("Refusing to overwrite an already audited run")
    sys.path.insert(0, str(harness))
    from jevbench.adapters.typesafe import TypeSafeAdapter
    from jevbench.metrics import latency_summary
    from jevbench.scoring import score_task
    from jevbench.summarize import public_export, summarize
    from jevbench.tasks import dataset_hash, load_jsonl

    meta = load(run / "run-meta.json")
    commit = subprocess.check_output(
        ["git", "-C", str(harness), "rev-parse", "HEAD"], text=True,
    ).strip()
    assert commit == meta["jevbench_commit"] == "1bcc55eb6c8cffde2306b3db03ede39b61c6152a"
    assert not subprocess.check_output(
        ["git", "-C", str(harness), "status", "--porcelain", "--untracked-files=no"], text=True,
    ).strip()
    tasks = load_jsonl(str(run / "tasks.jsonl"))
    by_id = {t.id: t for t in tasks}
    results = records(run / "results.jsonl")
    assert len(results) == len(by_id) == 231
    assert len({r["task_id"] for r in results}) == 231
    assert {r["task_id"] for r in results} == set(by_id)
    adapter = TypeSafeAdapter(model=meta["model"], key_env="")
    server_ms = []
    for row in results:
        task = by_id[row["task_id"]]
        path = run / "raw" / (hashlib.sha256(task.id.encode()).hexdigest() + ".json")
        assert digest(path) == row["raw_sha256"]
        raw = load(path)
        assert raw["request"] == adapter.build_request(task)
        assert raw["http_status"] == row["status_code"] == 200
        answer = raw["response"]["answers"]["decision"]
        probabilities = (
            {"yes": answer["noul"], "no": 1 - answer["noul"]}
            if task.question["type"] == "noul" else answer["probabilities"]
        )
        assert probabilities == row["probs_as_returned"]
        scored = score_task(probabilities, task)
        for field in ("correct", "predicted", "strict_valid", "valid"):
            assert scored[field] == row[field]
        assert raw["response"]["model"] == row["model"] == meta["model"]
        server_ms.append(raw["response"]["latency_ms"])
    summary = load(run / "summary.json")
    recomputed = public_export(summarize(tasks, results), tasks, results)
    recomputed["dataset_hash"] = dataset_hash(tasks)
    assert recomputed == summary
    assert summary["complete"] and meta["complete"]
    assert dataset_hash(tasks) == meta["dataset_hash"] == load(run / "manifest.json")["dataset_hash"]
    assert digest(run / "tasks.jsonl") == meta["task_file_sha256"]
    assert load(run / "health-before.json") == load(run / "health-after.json")
    assert len(load(run / "warmups.json")) == meta["warmups_excluded"] == 3
    health = load(run / "health-before.json")
    aws = load(run.parent / "aws-job.json")
    cleanup = load(run.parent / "cleanup.json")
    assert cleanup["benchmark_task_status"] == "STOPPED"
    assert cleanup["task_definition_status"] == "INACTIVE"
    assert cleanup["staging_objects_deleted"] and cleanup["model_task_same_and_running"]
    assert cleanup["gpu_instance_state"] == "running"
    tiers = {}
    for source, tier in (("original", "standard"), ("easy", "easy"), ("hard", "hard")):
        ids = {t.id for t in load_jsonl(str(harness / f"datasets/public/{source}.jsonl"))}
        subset = [r for r in results if r["task_id"] in ids]
        assert len(subset) == len(ids)
        tiers[tier] = {
            "n": len(subset), "correct": sum(bool(r["correct"]) for r in subset),
            "accuracy": sum(bool(r["correct"]) for r in subset) / len(subset),
            "latency": latency_summary([r["latency_s"] for r in subset]),
        }
    reference = {r["task_id"]: r for r in records(args.reference)}
    assert set(reference) == set(by_id)
    changed = [r for r in results if reference[r["task_id"]]["predicted"] != r["predicted"]]
    paired = {
        "reference": "Packaged v19 eval/jevbench-w4096/results.jsonl; upstream historical report, not a new run",
        "reference_sha256": digest(args.reference),
        "reference_correct": sum(bool(r["correct"]) for r in reference.values()),
        "current_correct": summary["n_correct"],
        "same_predicted": len(results) - len(changed),
        "changed_predictions": len(changed),
        "wrong_to_right": sum(not reference[r["task_id"]]["correct"] and r["correct"] for r in changed),
        "right_to_wrong": sum(reference[r["task_id"]]["correct"] and not r["correct"] for r in changed),
        "boundary_changes": [
            {
                "type": by_id[r["task_id"]].question["type"], "family": r["family"],
                "reference_probabilities": reference[r["task_id"]]["probs"],
                "current_probabilities": r["probs"],
            } for r in changed
        ],
    }
    analysis = {
        "model": meta["model"], "engine": "original Strands Decider; not vLLM",
        "instance_type": aws["instance_type"], "region": aws["region"],
        "model_image_digest": aws["model_image_digest"],
        "started_at": meta["started_at"], "finished_at": meta["finished_at"],
        "max_length": health["max_length"], "device": health["device"],
        "concurrency": 1, "warmups_excluded": 3, "retries": 0,
        "tiers": tiers,
        "client_mean_ms": statistics.mean(r["latency_s"] * 1000 for r in results),
        "server_reported_mean_ms": statistics.mean(server_ms),
        "server_reported_latency": latency_summary([v / 1000 for v in server_ms]),
        "input_tokens": {
            "min": min(r["usage"]["input_tokens"] for r in results),
            "max": max(r["usage"]["input_tokens"] for r in results),
            "mean": statistics.mean(r["usage"]["input_tokens"] for r in results),
        },
        "upstream_reference_comparison": paired,
        "cost": "No per-token tariff; EC2 and temporary Fargate costs excluded, not free inference",
        "latency_scope": meta["timing"],
        "candidate_order_test": "Not performed; official task and candidate order retained",
    }
    save(out / "summary.json", summary)
    save(out / "analysis.json", analysis)
    save(out / "verification.json", {
        "verified_at": datetime.now(UTC).isoformat(),
        "jevbench_commit": commit, "harness_source_unmodified": True,
        "dataset_hash": meta["dataset_hash"],
        "task_file_sha256": meta["task_file_sha256"],
        "raw_requests_match_official_adapter": 231, "raw_response_hashes_verified": 231,
        "scores_recomputed": 231, "public_summary_recomputed_and_equal": True,
        "same_model_health_before_and_after": True,
        "results_sha256": digest(run / "results.jsonl"),
        "summary_sha256": digest(out / "summary.json"),
        "analysis_sha256": digest(out / "analysis.json"),
        "private_archive_sha256": digest(run.parent / "results.zip"),
        "cleanup": cleanup,
    })
    print(json.dumps({
        "output": str(out), "correct": summary["n_correct"], "total": summary["n_attempted"],
        "latency": summary["latency"], "paired": paired,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
