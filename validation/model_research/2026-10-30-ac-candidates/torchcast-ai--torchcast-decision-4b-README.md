---
license: apache-2.0
base_model: Qwen/Qwen3.5-4B
base_model_relation: finetune
library_name: transformers
language:
- en
tags:
- typed-decisions
- jevbench
---

# Torchcast Decision 4B (v1.3.1)

A text-based decision model developed by **Torchcast AI**, based on Qwen3.5-4B. It returns yes/no probabilities
(`noul`), choice distributions (`choice`) and ordinal score distributions (`score`) through a TypeSafe-compatible API.
Each decision reads the option letters at the answer position in one forward pass (choice lists with more than
26 options are decided in a few passes over groups of options); nothing is generated.

Use the bundled `torchcast_decision` serving package with the bundled `decision_config.json`. Generic Hub
text-generation examples and causal-attention runtimes (vLLM, llama.cpp, MLX) do not reproduce the evaluated
interface: in this version the full-attention layers attend to the whole prompt in both directions (see below).

[Serving instructions](https://github.com/Torchcast-AI/torchcast-decision-4b/tree/v1.3.1#run-for-evaluation)

## What changed in v1.3

- **Weights:** a new full fine-tune of `Qwen/Qwen3.5-4B` on an expanded training mix of public datasets (official
  training splits) and synthetic decision data covering choice, yes/no and score questions. The
  architecture, tokenizer, prompt format (`jev_render_v3`) and attention mode are the same as in v1.2.
- **Speed:** the bundled server now uses CUDA graphs; median latency per request is about half that of v1.2
  (67.9 ms to 31.9 ms on one A40), with the same probabilities as the eager path.
- **Memory:** about 1.2 GiB less GPU memory after loading.
- **Serving settings:** updated in `decision_config.json`.

**v1.3.1** (serving package only): the weights and `decision_config.json` are those of v1.3.0, and the probabilities
are identical (bit for bit) to v1.3.0's. The serving package `torchcast_decision/` was rewritten by Torchcast AI; the
server now answers every error with JSON and a status code (503 when the GPU runs out of memory, 500 for anything
else) instead of closing the connection. The Apple Silicon (MLX) and GGUF backends, which could not run this model,
were removed.

## Results

On the JevBench leaderboard (release v1.7.9, as of 2026-10-27), Torchcast Decision 4B v1.3 is
**#1 among open-weight models by composite score**:

| Model | Composite | Capability | Intelligence | Calibration | Speed | Cost |
|---|---|---|---|---|---|---|
| **Torchcast Decision 4B v1.3** | **76.16** | **77.50** | **67.15** | 87.85 | 92.45 | 64.81 |
| H2O-Lightning-4B v1.1 | 73.78 | 75.00 | 60.04 | 89.95 | 92.37 | 64.05 |
| Torchcast Decision 4B v1.2 | 73.00 | 72.61 | 60.26 | 84.95 | 90.89 | 64.81 |

Source: [benchmarkheaven.com/jev-models](https://benchmarkheaven.com/jev-models). Measured by the JevBench maintainers
at revision `004acea2` (tag `v1.3.0`; v1.3.1 has the same weights and probabilities) with the bundled server and settings, on the second regular v1.6 draw (anchor
runs pending, so scores may be re-placed when the board's anchor offsets are applied).

## Artifact

- Pinned revision: tag `v1.3.1` of this repository (the board measured tag `v1.3.0`, same weights).
- Weight SHA-256: see `SHA256SUMS`.
- Served model name: `torchcast-decision-4b-v1.3`.

## Serving settings

Serve the model through the bundled `torchcast_decision` package; `decision_config.json` holds the serving settings.
Within a prompt, the full-attention layers use no causal mask (as in training), so loading the weights with plain
`transformers`, vLLM, llama.cpp or MLX gives different probabilities. Prompts longer than 16,384 tokens keep the head and the tail of the state. Repeated runs on the same GPU type
give identical probabilities. See `NOTICE` and the serving instructions.

## Intended use and limitations

English text-based decision research, such as classification, routing and bounded rubric evaluation. The server
returns decisions and does not execute actions. Probabilities can be unreliable on new domains.

## Licence and attribution

Model weights: **Apache License 2.0** (see `LICENSE`). Base model: Qwen3.5-4B by the Qwen team, Apache
License 2.0, Copyright 2026 Alibaba Cloud (`LICENSE-qwen-Apache-2.0`, `NOTICE`). Serving package: Apache License 2.0,
written by Torchcast AI (`torchcast_decision/LICENSE`, `torchcast_decision/NOTICE`). This
project is independent of TypeSafe AI and the JevBench maintainers. Earlier releases keep their own licence: v1.1 (tag `v1.1.0`) remains under CC BY-NC 4.0.
