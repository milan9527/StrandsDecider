---
model_name: GLiDE
license: other
library_name: transformers
tags:
- decision-model
- classification
- multimodal
license_name: fastino-community
license_link: https://huggingface.co/fastino/GLiDE/blob/main/LICENSE
---

<a href="https://fastino.ai" target="_blank" rel="noopener noreferrer">
  <img src="assets/fastino-glide-banner.svg" alt="Fastino Labs — GLiDE: decisions in a single forward pass" width="100%" />
</a>

# GLiDE

## #1 decision model in the world

**GLiDE is ranked #1 of 229 models on the [Decision Index 0.4.1](https://huggingface.co/spaces/multimodalart/jev-decision-index) (Thursday, 22 October 2026).**

<img src="assets/glide-v1.2-decision-index-27b-card.webp" alt="Fastino GLiDE V1.2: full score 71.52, #1 overall on the Decision Index 0.4.1" width="100%" />

**Inference provider: [Fastino](https://fastino.ai)** — use GLiDE through Fastino's hosted API (`POST https://api.fastino.ai/v1/systemone`, model `fastino/GLiDE`). [Get an API key](https://agent.fastino.ai) · [API documentation](https://docs.fastino.ai/inference/systemone)

| Rank | Model | Full score |
|---|---|---|
| **#1** | **Fastino GLiDE V1.2** | **71.5** |
| #2 | Jeffan-31b-1710 | 69.8 |
| #3 | baselabs mammoth-1 (27B) | 68.4 |

<img src="assets/decision-index-0.4.1-full-score.webp" alt="Decision Index 0.4.1 full-score ranking: Fastino GLiDE V1.2 #1 at 71.5" width="100%" />


<a href="https://fastino.ai" target="_blank" rel="noopener noreferrer">Fastino</a> · <a href="https://docs.fastino.ai/inference/systemone" target="_blank" rel="noopener noreferrer">API documentation</a> · <a href="https://agent.fastino.ai" target="_blank" rel="noopener noreferrer">Get an API key</a>

GLiDE is a decision model from <a href="https://fastino.ai" target="_blank" rel="noopener noreferrer">Fastino</a>. Given a state (text or JSON, optionally with images) and one or more typed questions, it returns a
probability for every option of every question.

## Fastino API

Use GLiDE through <a href="https://docs.fastino.ai/inference/systemone" target="_blank" rel="noopener noreferrer">Fastino’s hosted API</a> for classification, routing, and scoring.
Send decision requests to `POST https://api.fastino.ai/v1/systemone` with model `fastino/GLiDE`.
<a href="https://agent.fastino.ai" target="_blank" rel="noopener noreferrer">Create an account and get an API key</a>, or follow the <a href="https://docs.fastino.ai/quickstart" target="_blank" rel="noopener noreferrer">API quickstart</a>.
The instructions below cover running this repository locally.

## Overview

- **Typed decisions:** `choice` (one of up to 255 named options), `noul` (yes / no, returns P(yes)) and `score` (ordered levels).
- **Probabilities for every option,** read from a 255-way decision readout. Nothing is generated.
- **One forward pass per question.** All questions of a request (and of concurrent requests) are scored together in micro-batches.
- **Text, JSON and images:** the state can be a string, any JSON value, or a list of text and image parts.
- **Long contexts:** up to 40,000 tokens per question prompt by default (state, question, options and image tokens).
- **Interfaces:** a Python API and an HTTP server speaking the System One format (`POST /v1/systemone`).

## Hardware and memory

| | |
|---|---|
| Weights | bf16, 52.2 GB on disk: 51.2 GB language model, 0.92 GB vision encoder, 2.6 MB readout |
| GPU | one GPU with 80 GB or more |
| GPU memory | 52.2 GB after loading; 60.2 GB peak for a 39k-token question |
| Tested GPUs | NVIDIA RTX PRO 6000 Blackwell Server Edition (96 GB), NVIDIA B200 (180 GB), NVIDIA H100 80GB HBM3 |
| Load time | 30 to 60 s from network storage |

Weights are copied to the GPU tensor by tensor, so host memory use during loading stays low. Image preprocessing runs on the CPU.

## Install

```bash
pip install huggingface_hub
hf download fastino/GLiDE --local-dir GLiDE    # needs a token with read access to the fastino org
cd GLiDE
pip install -r requirements.txt
```

- Tested with Python 3.12, `torch==2.14.0` and `transformers==5.17.0` (all pins are in `requirements.txt`).
- `flash-linear-attention==0.5.2` is optional but recommended: it provides fast kernels for the linear-attention layers. Without it
  transformers falls back to a much slower PyTorch implementation, which was not part of the validation. All numbers below were
  measured with it installed.
- At load, transformers logs that `causal_conv1d` is not installed and uses its PyTorch path. This is expected: the validated setup
  does not use that package.
- The `glide/` package lives at the repository root: run from the repository directory or add it to `PYTHONPATH`.

## Quickstart

### Python

```python
from glide import Glide

model = Glide.from_pretrained(
    "GLiDE"
)  # local directory, or the Hub repo id "fastino/GLiDE"

result = model.decide(
    state={
        "ticket": "I was charged twice for order #4821 and the second charge is still pending.",
        "customer_tier": "gold",
    },
    questions={
        "intent": {
            "type": "choice",
            "instructions": "What does the customer want?",
            "criteria": {
                "refund": "Get money back",
                "cancel": "Cancel the order",
                "track": "Track a delivery",
                "other": "Something else",
            },
        },
        "urgent": {
            "type": "noul",
            "instructions": "Should this ticket be escalated today?",
        },
        "priority": {
            "type": "score",
            "instructions": "What support priority should this ticket get?",
            "criteria": [
                "low: no impact on the customer",
                "medium: the customer is inconvenienced",
                "high: the customer has lost money or cannot use the service",
            ],
        },
    },
)
```

Result on an RTX PRO 6000 (rounded):

```json
{
  "model": "glide-v1.2",
  "answers": {
    "intent": {"type": "choice", "choice": "refund", "confidence": 0.9521, "probabilities": {"refund": 0.9751, "cancel": 0.0016, "track": 0.0004, "other": 0.0229}},
    "urgent": {"type": "noul", "noul": 0.8267, "confidence": 0.6534},
    "priority": {"type": "score", "score": 2, "expected_level": 1.9191, "confidence": 0.8527, "probabilities": {"0": 0.0048, "1": 0.0712, "2": 0.9239}}
  },
  "usage": {"input_tokens": 316, "output_tokens": 0}
}
```

With images (PIL images, file paths, bytes, base64 strings or data URLs):

```python
from PIL import Image, ImageDraw

img = Image.new("RGB", (512, 512), "white")
ImageDraw.Draw(img).ellipse((128, 128, 384, 384), fill="red")

result = model.decide(
    state="A product photo from the catalogue.",
    questions={
        "color": {
            "type": "choice",
            "instructions": "What color is the shape in the image?",
            "criteria": {"red": "Red", "green": "Green", "blue": "Blue"},
        },
        "circle": {"type": "noul", "instructions": "Is the shape a circle?"},
    },
    images=[img],
)
```

```json
{
  "model": "glide-v1.2",
  "answers": {
    "color": {"type": "choice", "choice": "red", "confidence": 0.9997, "probabilities": {"red": 0.9998, "green": 0.0001, "blue": 0.0001}},
    "circle": {"type": "noul", "noul": 0.9941, "confidence": 0.9882}
  },
  "usage": {"input_tokens": 653, "output_tokens": 0}
}
```

`model.decide_batch([{"state": ..., "questions": ...}, ...])` scores several requests together and returns one item per request: a
response dict, or a `glide.RequestError` for a request that cannot be served (`decide` raises it instead).

### HTTP server

```bash
GLIDE_MODEL=/models/GLiDE uvicorn glide.server:app --host 0.0.0.0 --port 8000
# or
python -m glide.server --model /models/GLiDE --port 8000
```

The model loads at startup; `GET /health` answers once it is ready.

```bash
curl -s localhost:8000/v1/systemone -H 'Content-Type: application/json' -d '{
  "model": "glide-v1.2",
  "state": "Order #4821 was delivered to the wrong address and the customer wants it re-sent today.",
  "questions": {
    "action": {"type": "choice", "instructions": "What should support do next?",
               "criteria": {"resend": "Re-ship the order", "refund": "Refund the order", "investigate": "Open a carrier investigation"}},
    "urgent": {"type": "noul", "instructions": "Is the request time-sensitive?"}
  }
}'
```

With an image, the state is a list of parts:

```bash
IMG=$(base64 < photo.png | tr -d '\n')
curl -s localhost:8000/v1/systemone -H 'Content-Type: application/json' -d '{
  "model": "glide-v1.2",
  "state": ["Inspection photo from line 3.", {"type": "image_url", "image_url": {"url": "data:image/png;base64,'"$IMG"'"}}],
  "questions": {"damaged": {"type": "noul", "instructions": "Is there visible damage on the part?"}}
}'
```

#### Request

| Field | Type | Description |
|---|---|---|
| `model` | string | Optional. Ignored; the response reports the served model name (`GLIDE_MODEL_NAME`). |
| `state` | string, JSON value, or list of parts | The context to decide on. A list that contains image parts is multimodal: text parts are strings or `{"type": "text", "text": "..."}`, image parts are `{"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}`. Text parts are joined with newlines; images are placed before the text. Any other value is used as is (JSON values are serialized). |
| `questions` | object | `{key: question}`. Every question is answered independently, one forward pass each. |

Question fields:

| Field | Description |
|---|---|
| `type` | `choice`, `noul` or `score`. |
| `instructions` | The question. A string; objects are rendered as `key: value` lines. |
| `criteria` | **choice:** object `{option_key: description}`, 1 to 255 options, shown in the given order; descriptions may be strings or JSON (an empty description shows only the key). **noul:** optional `{"true": "...", "false": "..."}` descriptions (default Yes / No). **score:** a list of level descriptions (level *i* is index *i*), or an object keyed by numeric level (sorted ascending and re-indexed from 0). |

Images must be inline (data URLs or raw base64); remote URLs are not fetched. Each image is resized to at most
`GLIDE_MAX_PIXELS` pixels (default 1024 x 1024, i.e. at most 1,024 image tokens).

#### Response

For the first curl request above (RTX PRO 6000, rounded; the HTTP response also carries `latency_ms`):

```json
{
  "model": "glide-v1.2",
  "answers": {
    "action": {"type": "choice", "choice": "investigate", "confidence": 0.3816, "probabilities": {"resend": 0.3044, "refund": 0.0095, "investigate": 0.6861}},
    "urgent": {"type": "noul", "noul": 0.9917, "confidence": 0.9834}
  },
  "usage": {"input_tokens": 172, "output_tokens": 0}
}
```

| Answer type | Fields |
|---|---|
| `choice` | `choice`: most probable key. `probabilities`: `{key: p}` over all options, summing to 1. `confidence`: top minus second probability. |
| `noul` | `noul`: P(true). `confidence`: \|2 P(true) - 1\|. |
| `score` | `score`: most probable level index. `expected_level`: sum of index x probability. `probabilities`: `{"0": p, "1": p, ...}`. `confidence`: top minus second probability. |

`usage.input_tokens` is the prompt length summed over the request's questions (image tokens included). `latency_ms` is the server-side
time for the request (queueing plus inference).

Errors return `{"error": "..."}`: 422 for requests the model cannot serve (see below), 401 for a missing or wrong API key, 503 when the
queue is full, 504 on timeout, 500 for an internal error.

## Production notes

**Process model.** Run one server process per GPU (`workers=1`) and scale out with replicas behind a load balancer. A single worker
thread owns the GPU; HTTP handler threads only queue requests and wait for results.

**Batching and concurrency** (environment variables):

| Variable | Default | Meaning |
|---|---|---|
| `GLIDE_MODEL` | required | Model directory or Hub repo id. |
| `GLIDE_MODEL_NAME` | `glide-v1.2` | `model` field in responses. |
| `GLIDE_DEVICE` | `cuda` | Torch device, e.g. `cuda:1`. |
| `GLIDE_MAX_BATCH` | 16 | Max requests scored together in one micro-batch. |
| `GLIDE_BATCH_WAIT_MS` | 5 | How long the worker waits to fill a micro-batch. |
| `GLIDE_TOKEN_BUDGET` | 16384 | Max padded tokens per forward pass; question prompts are length-sorted and packed under it (a longer prompt runs alone). |
| `GLIDE_MAX_LEN` | 40000 | Max tokens per question prompt, image tokens included. |
| `GLIDE_MAX_QUEUE` | 1024 | Queued requests before new ones get 503. |
| `GLIDE_REQUEST_TIMEOUT_S` | 600 | Max wait for a result before 504. |
| `GLIDE_THREADS` | 1024 | HTTP handler threads (concurrent open requests). |
| `GLIDE_API_KEY` | unset | If set, require `Authorization: Bearer <key>`. |
| `GLIDE_MIN_PIXELS` / `GLIDE_MAX_PIXELS` | 65536 / 1048576 | Image resize bounds. |

**Max context.** 40,000 tokens per question prompt, validated end to end: a single 39k-token question takes about 13 s on an
RTX PRO 6000 once warm (23 s on first use) and peaks at 60.2 GB of GPU memory. Full-attention cost grows quadratically with
length, so long prompts dominate a micro-batch; set client timeouts with headroom (for example 60 s). Raising `GLIDE_MAX_LEN` is
possible but untested.

**Health.** `GET /health` returns `{"status": "ok", ...}` with the queue length and batch counters once the model is loaded.

**Latency** (bf16, warm, one request at a time; 750 requests of mixed length with 2.3 questions per request on average):

| GPU | Median | Mean | p90 | p99 |
|---|---|---|---|---|
| RTX PRO 6000 Blackwell (96 GB) | 84 ms | 263 ms | 803 ms | 2,709 ms |
| B200 (180 GB) | 48 ms | 116 ms | 326 ms | 1,086 ms |
| H100 80GB, first 300 requests | 78 ms | 254 ms | 672 ms | 1,949 ms |

On the same first 300 requests the RTX PRO 6000 measured 123 ms median and 369 ms mean. Latency grows with prompt length and
the number of questions. HTTP adds about 4 ms per request on localhost (server-side `latency_ms` vs client wall time).
Throughput with 32 concurrent HTTP clients on the RTX PRO 6000 was 2.3 requests/s (4.3 questions/s) on the first 256 of these
requests, the same as one at a time (2.3 requests/s): on this mix one request already keeps the GPU busy, so add replicas for
throughput; micro-batching gave no measurable gain here.

**Cold start and the kernel cache.** The linear-attention kernels are compiled and autotuned by Triton on first use of each new
shape. In a fresh process the first request takes about 25 to 35 s, and roughly ten later requests with new shapes take an extra
8 to 12 s each; in a cold pass over 750 mixed requests these delays stopped after about the first 450. Compiled kernels and
autotuning results are cached on disk (`TRITON_CACHE_DIR`, default `~/.triton/cache`, about 55 MB): a restarted process reusing
the cache showed no compile delays on the same 300 requests (p99 3.3 s instead of 10.3 s). In production:

1. point `TRITON_CACHE_DIR` at persistent storage shared by replicas with the same GPU type and software versions;
2. after the first deployment (or an upgrade), replay a few hundred representative requests through one replica to fill the cache;
3. keep a replica out of rotation until `/health` is up and its first warm-up requests have returned.

**Unsupported requests** get HTTP 422 with a message:

- more than 255 options: `options per choice exceeds the label set (N > 255)`
- a question prompt over `GLIDE_MAX_LEN`: `prompt exceeds the maximum context length`
- an image that cannot be decoded: `invalid image: ...`
- an unknown question type, missing `state`, or malformed `questions` / `criteria`

A request with an empty `questions` object returns 200 with empty `answers`.

**Determinism.** There is no sampling. The same request scored alone gives bit-identical results on the same GPU type and
software stack. The questions of one request always share forward passes; when concurrent requests are also micro-batched,
padding changes the shape of the bf16 computation and probabilities move slightly. Over 1,644 questions, scoring requests in
batches of 16 instead of one at a time changed probabilities by at most 0.039 and the top answer for 3 near-ties. Different GPU
types differ by a similar amount (at most 0.016 over 219 questions, one near-tie changed). Set `GLIDE_MAX_BATCH=1` when results
must not depend on other traffic.

**Precision.** Weights and compute are bf16 with PyTorch SDPA attention (`Glide.from_pretrained` disables the cuDNN SDPA backend
process-wide, so the memory-efficient kernel is used). Quantized variants have not been validated.

**Logging.** Request contents are not logged.

## Limitations

- It chooses among the options it is given; it does not generate text or explanations.
- Probabilities are model estimates; set decision thresholds on your own data.
- At most 255 options per question and 40,000 tokens per question prompt (default); larger requests are rejected with 422.
- Images: still images supplied inline only; no video and no remote URLs.
- Cost grows with the number of questions: each question is a separate forward pass over the full state.

## License

GLiDE’s Fastino contributions are licensed under the <a href="https://huggingface.co/fastino/GLiDE/blob/main/LICENSE" target="_blank" rel="noopener noreferrer">Fastino Community License</a>.

GLiDE is a modified version of Qwen3.8-27B. Qwen and other third-party components retain their original licenses; the <a href="licenses/Qwen3.8-27B-LICENSE" target="_blank" rel="noopener noreferrer">Qwen Apache License 2.0</a> is included separately. See <a href="NOTICE" target="_blank" rel="noopener noreferrer">NOTICE</a> for attribution.

## Citation

If you use GLiDE in your research, applications, or as the base for a derived model, please cite our forthcoming GLiDE paper on arXiv.
The arXiv link and BibTeX entry will be added here once the paper is available.
