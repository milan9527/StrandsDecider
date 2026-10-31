"""Print live benchmark progress while waiting for the final audited report."""

import json
import time

from all_models_protocol import save, stamp
from optimized_all_models_infra import ROOT, REMOTE, status, submit


def main():
    while True:
        final = json.loads((ROOT / "finalization.json").read_text())
        controller = json.loads((ROOT / "gpu-orchestration.json").read_text())
        if final["status"] in ("complete", "failed") or controller["status"] == "failed":
            print(json.dumps({"recorded_at": stamp(), "gpu": controller, "finalization": final},
                             ensure_ascii=False), flush=True)
            return
        if controller["status"] == "complete":
            print(stamp() + "：27/27 组推理已完成，正在审计并生成报告。", flush=True)
            time.sleep(20)
            continue
        operation = "live-progress-" + str(time.time_ns())
        script = "\n".join([
            "python3 - <<'PROGRESS'",
            "import json,pathlib",
            f"root=pathlib.Path({REMOTE + '/run'!r})",
            "rows=[]",
            "for path in sorted(root.glob('profiles/*/results/*/run.json')):",
            " data=json.loads(path.read_text())",
            " rows.append({'path':str(path.relative_to(root)),**{k:data.get(k) for k in "
            "('status','calls','errors','started_at','finished_at','last')}})",
            "print(json.dumps(rows))",
            "PROGRESS",
        ])
        submit(operation, script, 120)
        while True:
            response = status(operation)
            if response["Status"] == "Success":
                break
            if response["Status"] not in ("Pending", "InProgress", "Delayed"):
                raise RuntimeError(response)
            time.sleep(2)
        rows = json.loads(response["StandardOutputContent"])
        completed = 6 + sum(r["status"] in ("complete", "complete_with_errors") for r in rows)
        total = 12294 + sum(r["calls"] for r in rows)
        errors = sum(r["errors"] for r in rows)
        running = [r for r in rows if r["status"] == "running"]
        record = {"recorded_at": stamp(), "completed_groups": completed, "calls": total,
                  "errors": errors, "running": running, "rows": rows}
        save(ROOT / "live-progress.json", record)
        active = "; ".join(r["path"].replace("/run.json", "") + f" {r['calls']}/2049"
                           for r in running)
        print(f"{record['recorded_at']}：已完成 {completed}/27 组，{total}/55323 次调用，"
              f"接口错误 {errors}；{active}", flush=True)
        time.sleep(50)


if __name__ == "__main__":
    main()
