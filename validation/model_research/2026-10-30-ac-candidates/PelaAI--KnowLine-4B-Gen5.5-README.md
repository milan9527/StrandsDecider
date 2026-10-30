---
license: apache-2.0
base_model:
  - Qwen/Qwen3.5-4B
base_model_relation: finetune
library_name: transformers
pipeline_tag: text-classification
language:
  - en
  - zh
tags:
  - decision-model
  - system-one
  - decision-index
  - lora-merged
---

# KnowLine-4B-Gen5.5

**KnowLine-4B-Gen5 with a new way of serving it: the same weights, and a front end that reads short requests twice
before it answers.**

[Inference guide](INFERENCE.md) · [中文说明](README.zh.md) · weights Apache-2.0 · previous version:
[KnowLine-4B-Gen5](https://huggingface.co/PelaAI/KnowLine-4B-Gen5) · siblings:
[KnowLine-35B-A3B-Gen1.5](https://huggingface.co/PelaAI/KnowLine-35B-A3B-Gen1.5),
[KnowLine-26B-A4B-Gen2.5](https://huggingface.co/PelaAI/KnowLine-26B-A4B-Gen2.5)

We raise the minor version when only inference changes and the major version (Gen) when the weights change. Every weight,
config and tokenizer file of Gen5.5 is byte-identical to Gen5.

Highlights:

- **Same weights, read twice.** For a text-only request of up to 3,000 tokens, the front end writes the whole input a
  second time before the model answers. Nothing was trained; see [What changed in Gen5.5](#what-changed-in-gen55).
- **Decision Index 0.3 public suite: 66.75** (self-run, fresh full run), up from 65.67 for Gen5 with the same weights.
  The gains are mostly in reasoning and inference over long inputs (knowledge and reasoning 45.0 → 47.3,
  language 66.8 → 68.2); tools and agents are unchanged (87.4) and arts and taste slightly lower (61.2 → 61.0). See [Comparison](#comparison).
- **Decision tasks from new domains:** on our 18 real-text decision tasks from domains not in training it scores 55.0,
  against 51.4 for Gen5 with the same weights on the same harness; on our 34-task set 48.4 (Gen5: 42.5), and on our older
  10-task set 51.3 (Gen5: 49.5).
- **Same skills on other data:** on our sibling sets, which test the skill of a public benchmark on other data, it
  averages 66.1 (Gen5: 63.6).
- **Private scores:** the board's full score comes from the maintainers' private run. Gen5 is listed at 53.68. Gen5.5 has
  the same weights as Gen5; its private scores will be produced by the maintainers' run.
- **Our other evaluations:** Open-Jev 1.1 test / OOD 92.2 / 90.7 (Gen5 on the same files: 90.0 / 88.0), C-Eval
  80.5 (79.2), JevBench / JevBench-hard 85.3 / 70.3 (83.1 / 66.7), and slightly higher scores on our in-house held-out
  sets. Planted instructions changed 1.2% of answers (Gen5: 0.6%), and 2.7% with injection templates not seen in
  training (Gen5: 2.5%); neither difference is significant.
- **Calibration:** the temperature folded into the weights is unchanged (T = 1.50). Computed with the board's method, ECE is
  about 0.035-0.046 (Gen5: 0.037-0.049) and the Brier score about 0.27-0.30 (Gen5: 0.28-0.31); see [Calibration](#calibration).
- **Cost:** about 1.56 times the prompt tokens of Gen5 on the Decision Index suite. One request at a time on one H20:
  42.1 ms median and 83 ms mean, against 31.6 ms and 58.8 ms for Gen5 (our measurement, not the board's
  reference hardware); see [INFERENCE.md](INFERENCE.md).
- **Images: unchanged.** Requests with images are sent exactly as in Gen5, so Gen5's image results apply; see
  [Images](#images-zero-shot).

KnowLine is an independent model. It is not affiliated with, endorsed by, or derived from TypeSafe or Jev.

## What it does

You send a state (text or a chat) and up to 64 typed questions: yes/no, choose one of k, or score on a rubric. The model
answers every question with a probability distribution over its options:

- one forward pass per question, with no text generation;
- the output is the probability of each option's label token;
- existing Jev clients only need to change the base URL, and users of earlier versions only need to change the model
  name, because the interface is unchanged.

| | |
|---|---|
| Base model | [Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B) (Apache-2.0) |
| Weights | byte-identical to [KnowLine-4B-Gen5](https://huggingface.co/PelaAI/KnowLine-4B-Gen5): a weight average of two LoRA SFT models (rank 32, alpha 64, language model only), merged into bf16 weights, with a readout temperature T = 1.50 folded into the final norm weight |
| Serving | `serve_knowline.sh`: SGLang with FP8 at load, as for Gen5; `knowline_server.py` reads short requests twice (on by default; `--no-read-twice` gives the Gen5 prompts). We ran every evaluation with one server on one 96 GB H20. |
| Languages | English, Simplified Chinese, Traditional Chinese |

## Quickstart

```bash
pip install "sglang==0.5.21" "transformers==5.12.1" requests
bash serve_knowline.sh PelaAI/KnowLine-4B-Gen5.5 0 8080     # SGLang (FP8 at load) on :9080 + /v1/systemone on :8080
curl -s http://127.0.0.1:8080/v1/systemone -H 'Content-Type: application/json' -d '{
  "model": "m",
  "state": "Customer: my order arrived broken, I want my money back.",
  "questions": {"refund": {"type": "noul", "instructions": "Should the agent offer a refund?"},
                "tone": {"type": "choice", "instructions": "Customer tone?",
                         "criteria": {"angry": "Angry", "neutral": "Neutral", "happy": "Happy"}}}}'
```

- **Front end:** `knowline_server.py` with `knowline_layout.py` next to it; together they depend only on transformers and
  requests.
- **Full settings:** the exact settings used for our Decision Index run are in [INFERENCE.md](INFERENCE.md).

## What changed in Gen5.5

1. **Read twice.** Gen5 saw each request once: the state, then the instruction, the question and its options. Gen5.5
   writes all of that a second time, introduced by the line "Read the same input again before answering:", and then
   reads the answer from the label token as before. The rule is mechanical: it applies to every text-only request of at
   most 3,000 tokens (94.6% of the Decision Index requests); longer requests and requests with images are sent as in
   Gen5.
2. **A likely reason.** With causal attention, the first copy of a long state is read before the model knows the
   question; in the second copy every token can also attend to the first copy, question included.
3. **No training.** The weights, the temperature and the label-token readout are those of Gen5. We checked the change on
   our own evaluation sets and on a fresh full run of the Decision Index public suite before release. It is the same
   change as in [KnowLine-35B-A3B-Gen1.5](https://huggingface.co/PelaAI/KnowLine-35B-A3B-Gen1.5) and
   [KnowLine-26B-A4B-Gen2.5](https://huggingface.co/PelaAI/KnowLine-26B-A4B-Gen2.5).
4. **Credit.** The read-twice layout follows FlexDM ([github.com/1000luca/FlexDM](https://github.com/1000luca/FlexDM),
   MIT); repeating the input goes back to RE2 (Xu et al., 2023,
   [arXiv:2309.06275](https://arxiv.org/abs/2309.06275)). `knowline_layout.py` is our own implementation.

## Comparison

Scores on the Decision Index. Since Decision Index 0.4, the board's full score is 60% private tests of the same skills
and 40% private tasks from new domains; the public suite is shown but no longer counts. Gen5.5 has no board entry yet.

| model | size | DI 0.3 public | DI 0.4.1 full | source |
|---|---|---|---|---|
| **KnowLine-4B-Gen5.5** | 4B | **66.75** | not yet scored | self-run, official kit |
| KnowLine-4B-Gen5 (same weights) | 4B | 65.67 | 53.68 | board |
| StartLux-Decision v1.1 4B | 4.7B | 67.81 | 54.80 | board |
| Perplexity Decider Flash v1.2 | 4.5B | 60.06 | 54.29 | board |
| vLLM-SR d3-mini | 4.5B | 54.90 | 49.97 | board |
| OneJev 1.6 | 4.5B | 61.95 | 48.88 | board |
| Jev 1.14 | (API) | 60.70 | 60.24 | board |
| KnowLine-35B-A3B-Gen1 | 35B-A3B | 69.49 | 61.20 | board |

Board rows from the board's data of 2026-10-21 (22:34 UTC, Decision Index 0.4.1).

Public-suite skill by area (DI 0.3, same weights):

| area | Gen5.5 | Gen5 |
|---|---|---|
| Knowledge & reasoning | 47.3 | 45.0 |
| Language | 68.2 | 66.8 |
| Retrieval & routing | 74.0 | 73.3 |
| Tools & agents | 87.4 | 87.4 |
| Arts & taste | 61.0 | 61.2 |

## Releases

The model is trained in a self-evolving loop, and new versions will follow.

| model | date | DI 0.3 public | golden held-out (en / zh-Hans / zh-Hant) | notes |
|---|---|---|---|---|
| KnowLine-4B-Gen5.5 (this model) | 2026-10-22 | 66.75 | 70.3 / 72.1 / 67.5 | Gen5 weights, read-twice serving |
| [KnowLine-4B-Gen5](https://huggingface.co/PelaAI/KnowLine-4B-Gen5) | 2026-10-21 | 65.67 | 69.6 / 71.7 / 67.1 | fifth release; rebalanced data, aimed at generalization |
| [KnowLine-4B-Gen4](https://huggingface.co/PelaAI/KnowLine-4B-Gen4) | 2026-10-10 | 64.90 | 69.7 / 70.1 / 65.1 | fourth release |
| [KnowLine-4B-Gen3](https://huggingface.co/PelaAI/KnowLine-4B-Gen3) | 2026-10-09 | 63.11 | 69.4 / 70.8 / 65.0 | third release |
| [KnowLine-4B-Gen2](https://huggingface.co/PelaAI/KnowLine-4B-Gen2) | 2026-10-08 | 62.54 | 69.7 / 71.2 / 64.8 | second release |
| [KnowLine-4B-Gen1](https://huggingface.co/PelaAI/KnowLine-4B-Gen1) | 2026-10-07 | 60.47 | 68.7 / 69.9 / 64.1 | first release |

## Evaluation

All results are self-run and have not been verified by a third party. Every Gen5.5 number below was measured through the
Gen5.5 front end (read twice on). Unless noted, the Gen5 numbers were measured again on the same files.

### Held-out, Chinese and generalization evaluations

| suite | Gen5.5 | Gen5 |
|---|---|---|
| In-house evaluation set, English | 70.3 | 69.6 |
| In-house evaluation set, Simplified Chinese | 72.1 | 71.7 |
| In-house evaluation set, Traditional Chinese | 67.5 | 67.1 |
| C-Eval (4 categories, macro) | 80.5 | 79.2 |
| Open-Jev 1.1 test / OOD | 92.2 / 90.7 | 90.0 / 88.0 |
| JevBench / JevBench-hard | 85.3 / 70.3 | 83.1 / 66.7 |
| Decision tasks from new domains (our own, 18 real-text tasks)¹ | 55.0 | 51.4 |
| Decision tasks from new domains (our own, 34 tasks)¹ | 48.4 | 42.5 |
| Decision tasks from new domains (our own, 10 tasks)¹ | 51.3 | 49.5 |
| Sibling sets (same skill, other data; mean skill)¹ | 66.1 | 63.6 |
| Prompt injection: answers changed (lower is better) | 1.2% | 0.6% |
| Prompt injection with templates not seen in training (lower is better) | 2.7% | 2.5% |

- In a paired test against Gen5, p < 0.001 for Open-Jev 1.1 test and OOD and p = 0.02 for C-Eval; the differences on
  the in-house sets (p = 0.20, 0.44 and 0.61), JevBench (p = 0.23) and JevBench-hard (p = 0.34) are not significant.
  Planted instructions changed 12 of 1,000 answers against 6 for Gen5 (p = 0.24), and 16 against 15 of 600 with unseen
  templates.
- The Gen5 column matches the Gen5 card.
- ¹ Re-run for both models under the same serving (FP8 at load, read twice through our evaluation front end, which uses
  the same layout); the Gen5 card's values (51.3, 43.0, 49.4 and 63.7) came from the serving of the time.

### Web operation (Mind2Web official test splits, evaluation only)

| split | Gen5.5 element selection | Gen5.5 operation (balanced) | Gen5 element selection | Gen5 operation (balanced) |
|---|---|---|---|---|
| test_task (websites seen in training, new tasks) | 92.7 | 96.9 | 92.6 | 97.1 |
| test_website (new websites) | 91.2 | 96.3 | 90.9 | 96.9 |
| test_domain (new domains) | 92.0 | 98.0 | 91.8 | 98.4 |

- Within noise of Gen5 on all three splits (paired test, p ≥ 0.06); no request failed.

- The task is to pick the target element from a candidate set: the target plus up to 5 other elements sampled from the
  page. This is easier than the original Mind2Web protocol, so do not compare these results with the Mind2Web
  leaderboard.

### Images (zero-shot)

- **Unchanged from Gen5:** read twice applies only to text-only requests. A request with images is sent exactly as in
  Gen5, byte for byte, to the same weights, so Gen5's image results hold for Gen5.5 and we did not rerun them.
- **Gen5's results:** 66.0 on our reconstruction of the Decision Index 0.3.1 vision public suite (Gen4: 66.4; stock
  Qwen3.5-4B: 59.4); see the [Gen5 card](https://huggingface.co/PelaAI/KnowLine-4B-Gen5#images-zero-shot) for the
  per-benchmark table.

### Calibration

Computed on the 0.3 public suite using the method described by the Decision Index board: each field is scored right or
wrong, confidence is the probability of the chosen option, benchmarks are weighted equally, and 10 equal-width bins are
used.

| metric | Gen5.5 | Gen5 |
|---|---|---|
| ECE (lower is better) | 0.035-0.046 | 0.037-0.049 |
| Brier score (lower is better) | 0.27-0.30 | 0.28-0.31 |
| Confidence ≥95% but wrong | 1.5-1.6% | 1.5-1.6% |
| Mean confidence / accuracy | 0.83 / 0.78-0.80 | 0.82-0.83 / 0.78-0.80 |

- **Temperature in the weights:** unchanged from Gen5: the final norm weight includes T = 1.50, so every logit is divided
  by 1.50 before the softmax over the option labels.
- **Why ranges:** the board does not publish which benchmarks it uses for calibration, so we report ranges over the
  plausible benchmark sets, as for Gen5.
- **Recommendation:** if your use depends on probability thresholds, check calibration on your own data.

## Disclosures

- **Training data:** the weights are those of Gen5, so Gen5's disclosures on training data, Decision Index format data
  and decontamination apply unchanged; see the [Gen5 card](https://huggingface.co/PelaAI/KnowLine-4B-Gen5#disclosures).
- **Selection on evaluations:** we adopted read twice after checking it on our own evaluation sets and on a fresh full
  run of the Decision Index 0.3 public suite (the 66.75 above).
- **No model outputs as labels:** no output of Jev or any other decision model was used as a training label.

## Limitations

- **Slower than Gen5:** about 1.56 times the prompt tokens on the Decision Index suite; one request at a time on one
  H20, 42.1 ms median and 83 ms mean (Gen5: 31.6 ms and 58.8 ms), and 297 ms at the 95th
  percentile (Gen5: 144 ms). Use `--no-read-twice` if latency matters more than these gains.
- **Only short requests change:** text-only requests over 3,000 tokens, and requests with images, are answered exactly as
  by Gen5.
- **Not better everywhere:** arts and taste on the public suite is slightly lower than with Gen5 (61.2 → 61.0), and planted
  instructions changed 1.2% of answers against 0.6% (not significant).
- **Everything else as Gen5:** knowledge-heavy reasoning is still the weakest area and a 4B model is limited there; new
  domains are better than with Gen5 on our own sets but still well below larger models; other prompt-injection attacks
  may still work; the image scores are zero-shot and self-run on our own reconstruction of the suite.

## Citation

```bibtex
@misc{knowline4bgen55,
  title  = {KnowLine-4B-Gen5.5: a 4B decision model served with read twice},
  author = {PelaAI},
  year   = {2026},
  url    = {https://huggingface.co/PelaAI/KnowLine-4B-Gen5.5}
}
```

## License

- **Weights:** Apache-2.0, the same as the base model.
- **Code:** `knowline_server.py`, `knowline_layout.py` and `knowline_engine.py` are MIT (see the file headers).
