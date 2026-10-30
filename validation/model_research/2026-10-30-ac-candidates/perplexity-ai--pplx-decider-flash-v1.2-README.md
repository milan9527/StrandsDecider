---
license: apache-2.0
base_model: Qwen/Qwen3.5-4B
base_model_relation: finetune
library_name: pytorch
pipeline_tag: text-classification
tags:
  - classification
  - multimodal
  - custom-code
  - decider
  - decision-model
---

# pplx-decider-flash-v1.2

pplx-decider-flash-v1.2 is the small version of
[pplx-decider-v1.2](https://huggingface.co/perplexity-ai/pplx-decider-v1.2): the same joint request format,
the same API and the same text and image support, at about one seventh of the size. It is built on Qwen3.5-4B,
**distilled from the 27B decision models** on their training requests (the student learns the teachers' full
probability distributions, not just their answers). It combines several training runs through model souping (weight
averaging).

Use it when latency or cost matters more than the last points of accuracy. On our evaluations it keeps most of the
27B model's Decision Index and vision scores (see below). Distillation also improves results on decision tasks
held out from all training.

## Evaluation

| Decision Index 0.3 (public) | pplx-decider-flash-v1.2, joint requests | pplx-decider-flash-v1.2, one question per request | pplx-decider-v1.2, joint requests |
|---|---:|---:|---:|
| Knowledge | **42.0** | 41.4 | 56.3 |
| Language | 63.3 | **65.0** | 72.8 |
| Retrieval | 64.8 | **65.2** | 68.4 |
| Tools | 76.7 | **80.9** | 84.4 |
| Arts | **46.8** | **46.8** | 56.2 |
| **Overall Decision Index** | 58.88 | **60.05** | 68.09 |

The overall score uses the suite's weighting, not a simple category average. **Joint requests:** all of a request's
questions share one sequence. **One question per request:** every question is sent alone with its state. Unlike the
27B model, this model is more accurate with one question per request on most multi-question tasks (see
[When to group questions](#when-to-group-questions)); the two modes give the same score on the other benchmarks.

| Vision Decision Index 0.3 (public, images up to 1.6 MP) | pplx-decider-flash-v1.2 | pplx-decider-v1.2 |
|---|---:|---:|
| **Overall** | 72.53 | 77.43 |

## Usage

Requirements: Python 3.12+ and a CUDA GPU with room for about 9 GiB of BF16 weights plus working memory.
The repository is private: authenticate with a Hugging Face token that has access to it.
Download the repository and install `requirements.txt`. That file pins torch, transformers, safetensors, pillow,
torchvision and huggingface-hub. The [fast path](#fast-path) also needs `requirements-fast.txt`.

```python
import sys
from pathlib import Path
from huggingface_hub import snapshot_download

checkpoint = Path(snapshot_download("perplexity-ai/pplx-decider-flash-v1.2"))
sys.path.insert(0, str(checkpoint / "source" / "src"))
from pplx_decider import Decider

decider = Decider.from_pretrained(checkpoint, device="cuda")
response = decider.decide({
    "state": "My integration keeps failing with a 401 since we rotated our API key. Please help.",
    "questions": {
        "team": {
            "type": "choice",
            "instructions": "Which team should handle this request?",
            "criteria": {
                "billing": "Charges and refunds",
                "support": "Technical integration errors",
                "sales": "Questions about buying a product",
            },
        },
        "urgent": {"type": "noul", "instructions": "Is the customer blocked right now?"},
        "frustration": {"type": "score", "criteria": ["calm", "mildly annoyed", "frustrated", "angry"]},
    },
})
print(response["answers"]["team"]["choice"], response["answers"]["urgent"]["noul"])
```

`decide` accepts one request and returns one response. Given a list of requests, it returns a list of responses in
the same order. The source can also be installed as a package: `pip install ./source` (or
`pip install "./source[fast]"`).

### Request schema

```python
{
  "state": str | dict | list,            # the context to classify; non-strings are serialized as JSON
  "questions": {                         # 1 or more questions, answered from the same state
    "<id>": {
      "type": "choice" | "noul" | "score",
      "instructions": str | None,        # optional; default "Choose the best matching option."
      "criteria": ...,                   # see below
    },
  },
  "images": [path | "data:image/...;base64,..." | PIL.Image],   # optional
}
```

| Type | `criteria` | Answer |
|---|---|---|
| `choice` | `{option_name: description or None}`, 1 to 255 options | `choice`, `probabilities` (per option), `confidence` |
| `noul` | optional `{"true": description, "false": description}` | `noul` = P(true) |
| `score` | list of 2 to 255 level descriptions, lowest first | `score` (expected level index), `probabilities`, `legend`, `confidence` |

The options are shown to the model in the order you give them, under the answer codes `A`, `B`, ... Each response
looks like `{"answers": {"<id>": {...}}, "usage": {"input_tokens": int, "output_tokens": 0, "sequences": int}}`.
`input_tokens` counts every non-padding position the request used, including the template and image positions.
`sequences` is 1 unless the request had to be split. Requests that do not follow the schema raise
`pplx_decider.RequestError` before any computation.

`decider.logits(requests)` returns the raw readout logits of each question's valid options, before temperature.
For ranking, use the logit margin `true - false` of a `noul` question: unlike probabilities, it does not saturate
into ties.

## When to group questions

All questions in a request share one sequence, and every question attends to the state and to every other question.
For this model, **one question per request is the safer default**. Grouping helps only where the questions are tightly
coupled facets of one decision, and it hurts more than for the 27B model elsewhere:

| Task | Questions | Joint vs one question per request |
|---|---|---:|
| SATA-Bench (select all that apply) | one per option | **+6.6** |
| Home appliance simulator | steps of one task | **+3.4** |
| FinEntity | one per entity of a text | **+2.9** |
| PhishNChips | facets of one message | **+2.0** |
| BRIGHT (reasoning-intensive retrieval) | one per candidate document | −4.2 |
| ToolRet (tool retrieval) | one per candidate tool | −7.5 |
| BFCL (function calling) | one per candidate call | −15.4 |
| ACOS (aspect-category sentiment) | one per category | −20.1 |

(Decision Index task scores, points.) Our recommendations:

- **Send one question per request by default**, and score independent candidates (documents, tools, calls) in
  separate requests. The fast path packs many small requests efficiently, so separate requests stay cheap.
- **Group only multi-label "select all that apply" decisions** or steps of one routing decision, and check on your task.
- Question IDs are not shown to the model, but question order is. Put the context the questions need in the state.

## Temperature and calibration

`decision_config.json` stores the temperature fitted on held-out calibration data (1.554 for this checkpoint).
`decide` applies it exactly once, then normalizes a softmax over each question's valid options only.
`decide(..., temperature=t)` overrides it. When you use `logits` directly, divide by the saved temperature before the
softmax, and do not include the unused codes. It was fitted in the joint format, on data separate from the development
set. On the development set (1,497 questions) it gives accuracy 88.8%, ECE 0.021 and Brier 0.163 (without
temperature: ECE 0.057, Brier 0.173).

## Images

Images go in `images`. They are placed before the text of the request, and every question can see them. Each image is
resized (aspect ratio kept) to at most `max_pixels` pixels: **1,638,400 (1.6 MP)**, as saved in
`decision_config.json`. Smaller images keep their size (minimum 65,536 pixels). A 1.6 MP image uses about 1,600 sequence positions, so several large
images count toward the [length limit](#limits). Pass `max_pixels=` to `from_pretrained` to change the cap. The
checkpoint was trained and evaluated at its saved value.

## Fast path

`Decider.from_pretrained(..., fast=True)` packs whole requests into padding-free sequences, compiles the decoder
layers and replays CUDA graphs, exactly as for pplx-decider-v1.2 (see that model card for the details and options).
It needs `requirements-fast.txt`. Results match the reference path up to BF16 noise.

## Limits

- **Options:** 1 to 255 per question (2 to 255 for `score`).
- **Length:** `max_length` defaults to 262,144 tokens per sequence, the backbone's position limit. **Training used
  sequences up to about 32k tokens.** Longer requests still run as one sequence, but we have only spot-checked them:
  retrieving one fact from a long log works up to about 243k tokens (P(correct) above 0.999), with peak GPU memory of
  about 39 GiB (reference path) or 54 GiB (fast path), and about 1 minute (reference) or 20 seconds (fast) per
  243k-token request on one GB200. Validate beyond 32k on your own task, or pass `max_length=32768`. When a request
  exceeds `max_length`, its questions are split in halves, recursively, and every chunk keeps the full state and
  images; a single question that does not fit raises `pplx_decider.LengthError`. Inputs are never truncated.
- **Questions per request:** no fixed cap; the length limit is the only constraint (but see
  [When to group questions](#when-to-group-questions)).

## Checkpoint format and serving

This is the native decision-checkpoint layout: a `Qwen3_5Model` backbone plus `readout.safetensors`, a BF16
`[255, 2560]` decision head. The Transformers class name does not change the base model identity, Qwen3.5-4B.
`joint_config.json` declares the request protocol (`version: 3`, `joint-question-inline-readout-v1`, marker
`<|fim_suffix|>`).

- Full-attention layers are **noncausal** over the whole request. The linear-attention layers keep their native
  causal behavior. Default causal inference does not reproduce this checkpoint.
- The readout is applied at each `<|fim_suffix|>` marker, one per question, not at the last token. Literal special
  tokens in user content are neutralized before tokenization, so user text cannot create markers.
- This artifact has a separate readout, **not a full-vocabulary `lm_head`**. A serving system needs both the
  noncausal attention and the per-marker readout. Readout row `i` corresponds to vocabulary row
  `decision_config.json["token_ids"][i]`.

`release-manifest.json` records file checksums.

## Troubleshooting

- **`ImportError: ... flash-linear-attention`**: install `requirements-fast.txt`, or use `fast=False`.
- **Slow first call with `fast=True`**: `torch.compile` and CUDA-graph capture happen on first use of each bucket.
  Call `decider.warmup()` at startup. Pass `buckets=(32768,)` for a single shape, or `compile=None` to skip compiling.
- **Probabilities differ slightly between paths or batch compositions**: expected in BF16
  (mean |Δp| about 0.002, with rare argmax flips on near-ties). Use `fast=False` and one request per call for bit-stable results.
- **`LengthError`**: one question with the state and images exceeds `max_length`. Shorten the state, lower
  `max_pixels`, or raise `max_length` up to the backbone's 262,144 (beyond about 32k tokens, the training length,
  the probabilities are less validated).
- **Questions influence each other**: by design, see [When to group questions](#when-to-group-questions). Use one
  request per question for fully independent answers.
- **Out of memory**: lower `batch_tokens` (reference path) or use smaller buckets / `token_budget` (fast path).
- **Different answers from v1.1-style prompts**: this model expects the joint format built by `pplx_decider`. Do not
  reuse the v1.1 single-question prompt.

## Acknowledgment

A large part of the gains are thanks to the [tasksource](https://github.com/sileod/tasksource) data. If you also use
this data, consider citing the corresponding article

```bibtex
@inproceedings{sileo-2024-tasksource,
    title = "tasksource: A Large Collection of {NLP} tasks with a Structured Dataset Preprocessing Framework",
    author = "Sileo, Damien",
    booktitle = "Proceedings of the 2024 Joint International Conference on Computational Linguistics, Language Resources and Evaluation (LREC-COLING 2024)",
    month = may,
    year = "2024",
    address = "Torino, Italia",
    publisher = "ELRA and ICCL",
    url = "https://aclanthology.org/2024.lrec-main.1361",
    pages = "15655--15684",
}
```
