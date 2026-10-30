---
license: cc-by-nc-4.0
base_model: google/gemma-4-12B-it
library_name: transformers
language:
- en
- multilingual
tags:
- decision-model
- jev
- calibration
- gemma4
---

# Jeff-1.1-Medium

Jeff-1.1-Medium is a Jev-style decision model: a state, a typed question, and its options go in, and one forward pass
returns a calibrated probability for each option. It is Gemma 4 12B (instruction-tuned) with a LoRA adapter merged
into the weights and a small decision head. When it is unsure, it can optionally reason briefly before answering
(off by default).

- Serving code (repository "Jeff", Docker, TypeSafe "System One" request format as used by JevBench): https://github.com/j-geuter/Jeff, release [v1.3.0](https://github.com/j-geuter/Jeff/tree/v1.3.0)
- Model collection: https://huggingface.co/collections/jgeuter/jeff-11-6ada6708f3ed49beaf0f97ae
- Previous version: [Jeff-1.0-Medium](https://huggingface.co/jgeuter/Jeff-1.0-Medium)

## What's new in 1.1

Compared with [Jeff-1.0-Medium](https://huggingface.co/jgeuter/Jeff-1.0-Medium):

- **Better training data.** 58,000 new decision questions written and labeled by Qwen3.8-27B, and 28,000
  programmatic questions with computed labels. Targets of the 1.0 training pool are now half the original label and
  half Qwen3.8-27B's answer distribution (see [Training](#training)).
- **Longer training + model soup.** 1,500 training steps instead of 400. The final model is the soup of three
  training runs: both the LoRA adapter and the decision head are the mean of the three runs (in weight space).
- **Bidirectional attention.** The full-attention layers of the model now use bidirectional attention instead of causal masks.
- **Optional fast reasoning.** With `--reasoning on`, questions with a low calibrated confidence get a short
  reasoning before the answer (see [How it decides](#how-it-decides)). Autoregressive reasoning can be run through a vLLM server for faster inference. Off by default.
- **Up to 256 options.** Questions with more than 16 options (up to 256) are answered in groups of 16.

| | Jeff-1.0-Medium | Jeff-1.1-Medium | Jeff-1.1-Medium, reasoning on (JevBench limits) |
|---|---:|---:|---:|
| OpenDecisions Capability (Intelligence / Calibration), JevBench metric | 74.5 (65.2 / 83.9) | 85.0 (77.2 / 92.8) | 87.2 (85.0 / 89.3) |
| 231 public JevBench items, Capability | 78.4 | 83.2 | 84.3 |
| Seven public decision datasets, macro accuracy (%) / mean ECE | 87.6 / 0.076 | 86.0 / 0.072 | 86.4 / 0.083 |
| Six knowledge datasets, macro accuracy (%) / mean ECE | 80.7 / 0.053 | 85.0 / 0.043 | 86.0 / 0.060 |
| Questions that reason (OpenDecisions) | 0% | 0% | 36% |
| Output tokens per decision (OpenDecisions, mean) | 0 | 0 | 99.6 |


## Use

```bash
hf download jgeuter/Jeff-1.1-Medium --local-dir /models/Jeff-1.1-Medium
git clone --branch v1.3.0 https://github.com/j-geuter/Jeff && cd Jeff
docker build -t jeff . && docker run --gpus '"device=0"' -v /models/Jeff-1.1-Medium:/model:ro -p 127.0.0.1:8013:8013 jeff
```

One GPU with at least 40 GB (bf16 weights are about 24 GB). The model needs to be served through the serving code (see above). To reason when unsure, with the limits
we evaluate on JevBench with:

```bash
docker run --gpus '"device=0"' -v /models/Jeff-1.1-Medium:/model:ro -p 127.0.0.1:8013:8013 jeff \
  /model --host 0.0.0.0 --port 8013 --reasoning on --jevbench-limits on
```

## What is in this repository

| File | Content |
|---|---|
| `model-*.safetensors`, `config.json`, tokenizer files | Gemma 4 12B text model (bf16) with merged LoRA adapter |
| `head.safetensors`, `head_config.json` | decision head |
| `serving_rule.json` | per-type temperatures (choice 1.42, yes/no 1.35, score 1.06) |
| `adapter/` | the LoRA adapter (PEFT format, rank 96 = three runs' rank-32 adapters); the serving code subtracts its output to get the base model, which writes the reasoning |
| `reasoning.json` | reasoning settings: thresholds, temperatures, token budget, JevBench limits |
| `jeff_config.json` | base model and revision, training runs, attention, prompt format, input limit |
| `SHA256SUMS` | checksums of all files |

## How it decides

Each question is rendered as a multiple-choice prompt (SemIf's template: a short system message and a JSON object
with the state, the question, and the options labeled A, B, C, ...; Gemma's chat template, thinking disabled). The
model reads it once. The full-attention layers read the prompt in both directions (`"bidirectional": "full"` in `jeff_config.json`); the other layers are causal. The head maps the last hidden state to one logit per option.
The serving rule divides the logits by one temperature per question type (fitted on held-out data, never below 1).

Question types: choice, yes/no, score (ordered levels). The head has 16 answer slots; questions with more options (up to
256) are answered in groups of 16 and a final round. Inputs up to 8,192 tokens; longer inputs are shortened to <8192 tokens (by keeping sentences or JSON entries that mention the question).

**Reasoning (optional, off by default).** With `--reasoning on`, a question whose calibrated confidence is below a
threshold for its type gets a short reasoning first. By default this is about 60% of choice questions, 30% of yes/no questions, 20% of score questions (thresholds from our validation
data; you can set other shares via `--think-share`). In this case, the base model (Gemma 4 12B without the LoRA adapter) writes a reasoning trace of up to 512 tokens; the decision model (with LoRA turned back on) reads this new context, and generates a second answer. The final answer
is the geometric mean of the probabilities.

## Training

LoRA rank 32 (alpha = 64) on all attention and MLP projections, trained jointly with the head.
Plain cross-entropy on soft targets; no reinforcement learning, reward model or auxiliary loss. 1,500 steps of
up to 65,536 tokens (linear warm-up over 250 steps, constant learning rate, cosine decay over the last 100 steps), three
seeds, with final weights averaged (see above). For more training details on the recipe, please see our paper:
https://arxiv.org/abs/2610.17205 (updated version with the Jeff-1.1 training details coming out soon!).

Training data (261,561 questions):

| Part | Rows | Labels | Licence of the source |
|---|---:|---|---|
| decider's public training mixture (79 tasks rebuilt from public datasets with decider's code; at most 2,094 per task) | 161,638 | half dataset label, half Qwen3.8-27B | mixed; includes sources with non-commercial terms (e.g. ToxicChat and customer-support-tickets: CC BY-NC 4.0; MS MARCO and RACE: research-only terms) |
| Civil Comments | 2,094 | half annotator distribution, half Qwen3.8-27B | CC0 1.0 |
| Measuring Hate Speech | 2,094 | half annotator distribution, half Qwen3.8-27B | CC BY 4.0 |
| STS-B | 2,094 | half similarity distribution, half Qwen3.8-27B | see the STS benchmark |
| ChaosNLI | 2,886 | half 100 votes per item, half Qwen3.8-27B | CC BY-NC 4.0 |
| synthetic business documents (from 1.0) | 2,094 | half the 1.0 teacher labels, half Qwen3.8-27B | generated with Qwen models (Apache-2.0) |
| decider's custom questions, relabeled (from 1.0) | 2,094 | half the 1.0 teacher labels, half Qwen3.8-27B | Apache-2.0 (decider) |
| **new:** decision questions written by Qwen3.8-27B (thinking off) | 58,125 | Qwen3.8-27B (thinking, two samples averaged); kept only where its answer matched the intended one | generated with Qwen3.8-27B (Apache-2.0) |
| **new:** programmatic questions | 28,442 | computed by code | ours |

The 1.0 teacher labels come from Qwen3.5-122B-A10B and Qwen3.6-27B (two thinking samples each, averaged). Qwen3.8-27B
answers are the mean of two thinking samples.

**Disclosure.** No JevBench item (public or sealed) and no OpenDecisions item is in the training data. The training
length was chosen on [OpenDecisions](https://huggingface.co/datasets/jgeuter/OpenDecisions), our own validation set of 2,352 decisions; the temperatures and reasoning settings
on separate held-out data.

## Evaluation

Jeff 1.1 in one pass (no reasoning) against other decision models on [OpenDecisions](https://huggingface.co/datasets/jgeuter/OpenDecisions),
our 2,352-question validation set. Every model is scored by the dataset's `score.py` on the same questions (a yes/no
answer counts as "yes" when P(yes) ≥ 0.5); the other models are served with their authors' code, without reasoning.

| Model | Size | Capability | Intelligence | Calibration |
|---|---|---:|---:|---:|
| **[Jeff-1.1-Large](https://huggingface.co/jgeuter/Jeff-1.1-Large)** | 31B | 89.0 | 83.5 | 94.5 |
| [StartLux-Decision v1.1 27B Instant](https://huggingface.co/startlux-models/StartLux-Decision-v1.1-27B-Instant) | 27B | 88.5 | 85.2 | 91.7 |
| **[Jeff-1.1-Qwen-27B](https://huggingface.co/jgeuter/Jeff-1.1-Qwen-27B)** | 27B | 86.8 | 81.2 | 92.5 |
| **[Jeff-1.1-Medium](https://huggingface.co/jgeuter/Jeff-1.1-Medium)** | 12B | 85.0 | 77.2 | 92.8 |
| [vLLM-SR d3](https://huggingface.co/vllm-sr/d3) | 27B | 84.5 | 77.9 | 91.1 |
| [Amos-1-Large](https://huggingface.co/mukaddamzaid/amos-1-large) | 27B | 84.1 | 78.5 | 89.6 |
| [StartLux-Decision v1.1 4B Instant](https://huggingface.co/startlux-models/StartLux-Decision-v1.1-4B-Instant) | 4B | 82.2 | 72.8 | 91.6 |
| [pplx-decider v1.1 27B](https://huggingface.co/perplexity-ai/pplx-decider-v1.1-27b) | 27B | 81.3 | 77.3 | 85.3 |
| [Jev 1.13.0 (TypeSafe API)](https://typesafe.ai/blog/introducing-system-one-models-and-jev) | closed | 80.1 | 71.9 | 88.3 |
| **[Jeff-1.1-Qwen-4B](https://huggingface.co/jgeuter/Jeff-1.1-Qwen-4B)** | 4B | 79.3 | 68.4 | 90.2 |
| [Wald-4B v2.0](https://huggingface.co/org2ai/Wald-4B/tree/919a9d72a65379271005ed0945bfc72742dad3af) | 4B | 77.1 | 67.0 | 87.3 |

Jeff numbers are from the models served by [Jeff v1.2.0](https://github.com/j-geuter/Jeff) on one H200 GPU at batch size
one; this model takes 0.035 s per decision (median; 0.040 s with reasoning). In the table at the top, the seven public
decision sets are TREC, CB, WANLI (256 items), SemIf's authored and perturbation sets, TypeSafe's example set and 1,500
items of decider's held-out tasks; the six knowledge sets are BoolQ, MMLU, MMLU-Pro, ARC, WinoGrande and SciQ. See the
paper for more details.

## Limitations

- At most 256 options per question; inputs above 8,192 tokens are shortened to the parts that mention the question.
- Reasoning adds latency (a few seconds per reasoning question) and output tokens; the per-type temperatures after
  reasoning were fitted for the released shares and budget.
- Mostly English training data (OpenDecisions is 78% English).
- Probabilities are calibrated on our held-out data; recalibrate for a very different domain.

## Licence

The weights are released under **CC BY-NC 4.0** (non-commercial). They are derived from google/gemma-4-12B-it
(Apache License 2.0), and the training data includes sources with non-commercial terms (see the table above). The
serving code is Apache-2.0.

## Citation

If you find this model helpful, please consider citing our paper:
```bibtex
@misc{geuter2026releasinginnerjevsimple,
      title={Releasing the Inner Jev: A Simple Recipe for Open Decision Models},
      author={Jonathan Geuter and Andrew Cheng and David Alvarez-Melis},
      year={2026},
      eprint={2610.17205},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2610.17205},
}
```
