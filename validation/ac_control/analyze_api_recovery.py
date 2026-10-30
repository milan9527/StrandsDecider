"""Audit the preserved first segment, explicit capture gap and unattempted remainder."""

import argparse
import base64
import contextlib
import hashlib
import io
import json
from pathlib import Path

from analyze import grade
from analyze_api_ablation import LABELS, decode_receipt, report, summarize_group
from analyze_api_ablation import analyze as analyze_original
from api_ablation_protocol import GPT_MODEL
from run_resident import save, sha


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_binary_encoding(value):
    count = 0
    if isinstance(value, dict):
        if "__sdk_bytes_base64__" in value:
            assert set(value) == {"__sdk_bytes_base64__"}
            base64.b64decode(value["__sdk_bytes_base64__"], validate=True)
            return 1
        count += sum(check_binary_encoding(v) for v in value.values())
    elif isinstance(value, list):
        count += sum(check_binary_encoding(v) for v in value)
    return count


def analyze(run, partial=False):
    with contextlib.redirect_stdout(io.StringIO()):
        original_summary, rows = analyze_original(run, partial=True)
    directory = run / "gpt"
    recovery = json.loads((directory / "recovery_plan.json").read_text())
    for field, path in {
        "original_receipts_sha256": directory / "formal_receipts.jsonl",
        "original_metadata_sha256": directory / "formal_run.json",
        "original_log_sha256": run / "gpt_formal.log",
        "original_plan_sha256": run / "plan.json",
        "runner_sha256": directory / "resume_api_capture.py",
    }.items():
        assert recovery[field] == file_hash(path), field
    assert recovery["runner_sha256"] == file_hash(Path(__file__).with_name("resume_api_capture.py"))
    experiments = json.loads((run / "experiments.json").read_text())
    references = {r["id"]: r for r in json.loads((run / "references.json").read_text())}
    catalog = {c["key"]: c for c in json.loads((run / "command_set.json").read_text())["commandSet"]}
    assert recovery["experiments_sha256"] == sha(experiments)
    assert len(rows) == 750 + 250 + 179
    assert sum(r["provider"] == "gpt" for r in rows) == 179
    index = recovery["lost_observation"]["index_zero_based"]
    assert index == 179 and recovery["remaining_indices"] == list(range(180, 250))
    experiment = experiments[index]
    assert (experiment["case_id"], experiment["variant"], experiment["arm"]) == (
        "M08", "reversed", "criteria_only",
    )
    reference = references[experiment["case_id"]]
    lost = {
        **{k: experiment[k] for k in ("case_id", "dataset", "variant", "arm")},
        "provider": "gpt", "query": reference["query"], "title": reference["title"],
        "category": reference["category"], "expected": reference["expected"],
        "cmdList": [], "status": "capture_error", "client_ms": None, "server_ms": None,
        "http_calls": 1, "baseline_reused": False, "gate_selected_keys": None,
        "unit_completion_correct": False, "raw_response_available": False,
        "capture_error": recovery["lost_observation"]["reason"],
    }
    lost.update(grade(lost["expected"], [], "capture_error"))
    rows.append(lost)
    path = directory / "remainder_receipts.jsonl"
    receipts = [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []
    meta = json.loads((directory / "remainder_run.json").read_text())
    assert meta["recovery_plan_sha256"] == file_hash(directory / "recovery_plan.json")
    assert meta["expected_model"] == GPT_MODEL and meta["automatic_retries"] == 0
    assert meta["concurrency_per_provider"] == 1
    binary_fields = 0
    for row, experiment in zip(receipts, experiments[180:180 + len(receipts)], strict=True):
        assert row["provider"] == "gpt"
        assert all(row[k] == experiment[k] for k in ("case_id", "arm", "variant", "dataset"))
        binary_fields += check_binary_encoding(row)
        rows.append(decode_receipt(row, experiment, references[row["case_id"]], catalog, GPT_MODEL))
    if not partial:
        assert meta["status"] == "complete" and len(receipts) == meta["actual_observations"] == 70
        assert meta["actual_calls"] == sum(len(r["stages"]) for r in receipts)
        assert meta["errors"] == sum(r["status"] != "ok" for r in receipts)
        assert len(rows) == 1250
        for provider in ("jev", "gpt"):
            probe = json.loads((run / provider / "probe_run.json").read_text())
            first_meta = original_summary["api_metadata"][provider]
            assert probe["status"] == "complete" and probe["errors"] == 0
            assert len(probe["observed_models"]) == 1
            assert first_meta["expected_model"] == probe["observed_models"][0]
            assert first_meta["automatic_retries"] == 0 and first_meta["concurrency_per_provider"] == 1
            source = run / provider / "formal_receipts.jsonl"
            first_rows = [json.loads(s) for s in source.read_text().splitlines()]
            assert len(first_rows) == first_meta["actual_observations"]
            assert first_meta["actual_calls"] == sum(len(r["stages"]) for r in first_rows)
            assert first_meta["errors"] == sum(r["status"] != "ok" for r in first_rows)
            assert first_meta["plan_file_sha256"] == file_hash(run / "plan.json")
            if provider == "jev":
                assert first_meta["status"] == "complete" and len(first_rows) == 250
    all_gpt = [r for r in rows if r["provider"] == "gpt"]
    api_meta = original_summary["api_metadata"]
    api_meta["gpt"] = {
        **api_meta["gpt"], "status": "running" if partial else "complete_with_capture_error",
        "actual_observations": len(all_gpt), "actual_calls": sum(r["http_calls"] for r in all_gpt),
        "errors": sum(r["status"] != "ok" for r in all_gpt),
        "captured_observations": len(all_gpt) - 1, "capture_errors": 1,
        "finished_at": meta.get("finished_at"), "source_segments": [
            "gpt/formal_receipts.jsonl", "gpt/remainder_receipts.jsonl", "gpt/recovery_plan.json",
        ],
    }
    summary = {
        "partial": partial, "observations": len(rows),
        "new_api_observations": sum(r["provider"] in {"jev", "gpt"} for r in rows),
        "new_api_calls": sum(r["http_calls"] for r in rows if r["provider"] in {"jev", "gpt"}),
        "models": {p: summarize_group([r for r in rows if r["provider"] == p]) for p in LABELS},
        "api_metadata": api_meta,
        "new_receipts_sha256": {
            "jev": file_hash(run / "jev/formal_receipts.jsonl"),
            "gpt_initial": file_hash(directory / "formal_receipts.jsonl"),
            "gpt_remainder": file_hash(path),
        },
        "capture_gap": recovery["lost_observation"], "remainder_binary_fields": binary_fields,
    }
    print("GPT", len(all_gpt), "/250; capture failures=1; other failures=",
          sum(r["status"] not in {"ok", "capture_error"} for r in all_gpt))
    if partial:
        return summary, rows
    save(run / "five_model_results.json", rows)
    save(run / "five_model_summary.json", summary)
    save(run / "audit.json", {
        "observations": len(rows), "new_api_observations": summary["new_api_observations"],
        "new_api_calls_including_capture_gap": summary["new_api_calls"],
        "errors": sum(r["status"] != "ok" for r in rows), "capture_errors": 1,
        "api_observations_with_raw_evidence": summary["new_api_observations"] - 1,
        "prior_raw_rescoring_matches": True, "prior_evidence_unchanged": True,
        "preserved_failed_run_evidence_unchanged": True, "capture_gap_counted_as_failure": True,
        "capture_gap_response_status_and_timing_unknown": True, "replayed_observations": 0,
        "gpt_model_and_low_effort_verified_for_all_saved_requests": True,
        "frozen_task_and_transport_hashes_verified_for_all_saved_requests": True,
        "all_saved_candidate_ids_and_question_ids_validated": True,
        "second_stage_selected_only_by_model_gate": True, "no_output_repair": True,
        "original_source_sha256": json.loads((run / "plan.json").read_text())["source_sha256"],
        "recovery_runner_sha256": recovery["runner_sha256"],
        "recovery_analyzer_sha256": file_hash(Path(__file__)),
        "new_receipts_sha256": summary["new_receipts_sha256"],
    })
    report(run, summary, rows, references)
    report_path = run / "FIVE_MODELS.zh.md"
    text = report_path.read_text()
    notice = (
        "**采集异常说明：GPT第180条（M08、反转顺序、仅改选项条件）在保存SDK对象时，"
        "因bytes字段无法JSON序列化而丢失结果。该条计采集失败，不判定为模型答错；"
        "原始顺序20题主结果不受影响，换序该组按19/20计。原记录和故障日志保持不变，"
        "只增加二进制字段的无损Base64保存后继续尚未调用的70条，没有重跑丢失题。"
        "该条返回状态、答案与耗时未知；完整返回证据覆盖新增500条中的499条。**\n\n"
    )
    text = text.replace("\n\n", "\n\n" + notice, 1)
    text = text.replace("任何多余、缺失、错值、调用或格式错误都计为失败。",
                        "任何多余、缺失、错值、调用、格式或采集错误都计为失败。")
    text = text.replace("调用/格式失败", "调用/格式/采集失败")
    text = text.replace("格式/调用失败", "格式/调用/采集失败")
    text = text.replace(
        "- [Jev原始调用](jev/formal_receipts.jsonl)、[GPT实际请求及完整SDK返回](gpt/formal_receipts.jsonl)。",
        "- [Jev原始调用](jev/formal_receipts.jsonl)、[GPT前179条](gpt/formal_receipts.jsonl)、"
        "[GPT后70条](gpt/remainder_receipts.jsonl)。",
    )
    text += (
        "\n- [GPT采集故障日志](gpt_formal.log)、[故障与续跑计划](gpt/recovery_plan.json)、"
        "[续跑记录](gpt/remainder_run.json)。原始formal_run.json保留中断时的状态，"
        "最终合并状态见five_model_summary.json。新增调用数含丢失记录对应的1次调用尝试。\n"
        "- [五模型错误定位、缓存用量与M08完整问题选项](DIAGNOSTICS.zh.md)。"
        "后70条SDK bytes字段使用`__sdk_bytes_base64__`标记无损保存；"
        "只改变日志编码，不改变模型请求、effort、解析或评分。\n"
    )
    report_path.write_text(text)
    raw = []
    for path in (run / "jev/formal_receipts.jsonl", directory / "formal_receipts.jsonl",
                 directory / "remainder_receipts.jsonl"):
        raw.extend(json.loads(s) for s in path.read_text().splitlines())
    examples = run / "examples"
    examples.mkdir(exist_ok=True)
    for case in ("S03", "N04"):
        save(examples / (case + ".api_raw.json"),
             [r for r in raw if r["case_id"] == case and r["variant"] == "original"])
        save(examples / (case + ".actual_outputs.json"),
             [r for r in rows if r["case_id"] == case and r["variant"] == "original"])
    print("Final five-model audit complete; one explicitly recorded capture gap.")
    return summary, rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--partial", action="store_true")
    args = parser.parse_args()
    analyze(args.run, args.partial)
