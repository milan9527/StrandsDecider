#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}"
export TOKENIZERS_PARALLELISM=false
exec uv run --extra model strands-decider serve \
  "${DECIDER_MODEL:-StrandsAgents/strands-decider-2B-hobson-v19}" \
  --device "${DECIDER_DEVICE:-cpu}" \
  --host 127.0.0.1 \
  --port "${DECIDER_PORT:-8099}" \
  --strict-window
