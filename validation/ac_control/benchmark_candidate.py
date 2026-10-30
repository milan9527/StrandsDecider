"""Run one completed native-runtime startup through the frozen serial benchmark."""

import argparse
import json
import shlex

from remote_candidates import BUCKET, PREFIX, REMOTE, ROOT, status, submit


def benchmark(provider, attempt, startup_attempt=None):
    startup = "start-" + provider + "-" + (startup_attempt or attempt)
    assert status(startup)["Status"] == "Success"
    operation = "benchmark-" + provider + "-" + attempt
    unit = "ac-candidate-" + provider
    cleanup = "\n".join([
        # Preserve the original benchmark exit status even if cleanup has a problem.
        "candidate_exit=$?",
        "systemctl stop " + unit,
        "journalctl -u " + unit + " --no-pager -o short-iso > "
        + REMOTE + "/logs/" + provider + "-" + attempt + "-complete.log",
        "aws s3 sync " + REMOTE + "/logs s3://" + BUCKET + "/output/" + PREFIX + "/logs --only-show-errors",
        'exit "$candidate_exit"',
    ])
    script = "\n".join([
        "set -eu",
        "# Verified successful startup operation: " + startup,
        "trap " + shlex.quote(cleanup) + " EXIT",
        "systemctl is-active --quiet " + unit,
        shlex.join(["python3", REMOTE + "/run/run_candidate_benchmark.py", "--run", REMOTE + "/run",
                    "--provider", provider, "--endpoint", "http://127.0.0.1:18811", "--s3-output",
                    "s3://" + BUCKET + "/output/" + PREFIX + "/results"]),
    ])
    return submit(operation, script, 7200)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=tuple(json.loads((ROOT / "models.json").read_text())))
    parser.add_argument("--attempt", default="official-1")
    parser.add_argument("--startup-attempt")
    args = parser.parse_args()
    print(benchmark(args.provider, args.attempt, args.startup_attempt))
