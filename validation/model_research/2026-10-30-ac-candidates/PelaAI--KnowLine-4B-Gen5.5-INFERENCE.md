# KnowLine-4B-Gen5.5: serving and Decision Index reproduction

Gen5.5 is KnowLine-4B-Gen5 with a new way of serving it: the weights are the same files, and the front end reads
short requests twice (see [Read twice](#read-twice)). These settings reproduce our self-run Decision Index 0.3 evaluation:
the full 0.3 public suite sent fresh (no rows carried over from another run), scored 2026-10-22 18:23 CST.

## Weights

- The weights are byte-identical to [KnowLine-4B-Gen5](https://huggingface.co/PelaAI/KnowLine-4B-Gen5): every weight,
  config and tokenizer file has the same SHA-256 as there (`SHA256SUMS`). They were made in two steps (bf16):
  1. **Averaging**, tensor by tensor (each step computed in fp32 and stored in bf16):
     - a model retrained from Qwen3.5-4B on the rebalanced data of this round (a LoRA r32, merged), 0.5;
     - a model that continues our earlier 4B line, trained further on a further round of data (a LoRA r32, merged),
       0.5.

     248 tensors are averaged. The other 490 are identical in both models and copied unchanged, including the base
     model's vision tower and MTP head.
  2. **Readout temperature.** The final norm weight `model.language_model.norm.weight` is rewritten as
     `w' = (1 + w) / 1.50 - 1`. The norm is zero-centred and the output head is tied to the embeddings, so this divides
     every output logit by T = 1.50. No other tensor changes; the MTP head keeps its own norm.
- The architecture is `Qwen3_5ForConditionalGeneration`. `config.json`, the tokenizer files and the chat template are
  byte-identical to Gen1-Gen5.
- `SHA256SUMS` lists every file. Only the serving files and the documentation differ from Gen5.

## Software

| component | version |
|---|---|
| SGLang | 0.5.21 (torch 2.13.0, CUDA 13.0, flashinfer-python 0.6.18) |
| transformers | 5.12.1 |
| front end | `knowline_server.py` + `knowline_layout.py` (this repository; need only transformers and requests) |
| decision-index kit | 0.3 at commit 62d2f51de34a2de64906345b6bc3e98e27ff55c7 |

### About the front end

`knowline_server.py` is the `/v1/systemone` front end of our runs. It is the Gen5 front end with one addition, read
twice, whose prompt layout lives in `knowline_layout.py` next to it. The front end contains:

- rendering: the chat template with thinking off; the state is followed by one user turn with the instruction, the
  question and all options labelled A, B, ...; the assistant turn opens with `Answer:`;
- read twice (on by default, see below);
- label-token scoring: one prefill per question, then a softmax over the option labels only;
- the HTTP server.

### Read twice

- **What changes:** for a text-only request of at most 3,000 tokens (counted with the model's tokenizer over the whole
  request read once), every turn after the system turn is written a second time before the answer is read: the state, the
  instruction, the question and its options. The second copy starts with the line "Read the same input again before
  answering:". The answer is still read from the label token after `Answer:`, one prefill per question.
- **What does not change:** requests over 3,000 tokens and requests with images are sent exactly as in Gen5. In our
  Decision Index run, 133,004 of the 140,620 requests (94.6%) were read twice.
- **Switches:** `--no-read-twice` gives exactly the Gen5 prompts; `--twice-max-tokens` sets the cut. `knowline_engine.py`
  takes `--option read_twice=0` and `--option twice_max_tokens=<n>` for the same.
- **Cost:** 1.56 times the prompt tokens of Gen5 over the whole suite (320 million against 205 million), and longer requests; see
  [Hardware and latency](#hardware-and-latency).
- **Credit:** the read-twice layout follows FlexDM ([github.com/1000luca/FlexDM](https://github.com/1000luca/FlexDM), MIT),
  including its "Read the same input again before answering:" line; repeating the input goes back to RE2 (Xu et al.,
  2023, [arXiv:2309.06275](https://arxiv.org/abs/2309.06275)). `knowline_layout.py` is our own implementation.

The front end still uses temperature 1. The calibration temperature is in the weights, so no option or calibration file
is needed, and both backends get it.

## Serve

`serve_knowline.sh` starts both processes. Apart from comments, it is the same script as for Gen5.

1. **SGLang engine.**
   - FP8 is on at serving: weights are stored in bf16 and SGLang quantizes them on load. Every run below used one 96 GB
     H20 per server.
   - `--mem-fraction-static 0.72` only sizes SGLang's KV cache. Any value that fits works and scores do not depend on it.
   - SGLang treats the model as multimodal by itself. The Decision Index run sent text only.
2. **`/v1/systemone` front end:** `knowline_server.py`, `chat` style, temperature 1, 16 scoring threads, read twice up
   to 3,000 tokens, no per-type calibration file.

```bash
pip install "sglang==0.5.21" "transformers==5.12.1" requests   # torch / CUDA per SGLang's install docs
bash serve_knowline.sh PelaAI/KnowLine-4B-Gen5.5 0 8080      # GPU 0; SGLang on :9080, /v1/systemone on :8080
curl -s http://127.0.0.1:8080/health
curl -s http://127.0.0.1:8080/v1/systemone -H 'Content-Type: application/json' -d '{
  "model": "m",
  "state": "Customer: my order arrived broken, I want my money back.",
  "questions": {"refund": {"type": "noul", "instructions": "Should the agent offer a refund?"},
                "tone": {"type": "choice", "instructions": "Customer tone?",
                         "criteria": {"angry": "Angry", "neutral": "Neutral", "happy": "Happy"}}}}'
```

Equivalent manual launch, with the exact flags of our run:

```bash
CUDA_VISIBLE_DEVICES=0 python -m sglang.launch_server --model-path PelaAI/KnowLine-4B-Gen5.5 --served-model-name m \
  --tp 1 --quantization fp8 --mem-fraction-static 0.72 --mamba-radix-cache-strategy extra_buffer --enable-fp32-lm-head \
  --port 9080 &
python knowline_server.py --model PelaAI/KnowLine-4B-Gen5.5 --backend sglang --url http://127.0.0.1:9080 \
  --served-model-name m --temperature 1 --workers 16 --port 8080          # read twice is on by default
```

Without SGLang (through transformers; text only, no prefix cache, bf16 rather than FP8):

```bash
pip install torch "transformers==5.12.1" requests
python knowline_server.py --model PelaAI/KnowLine-4B-Gen5.5 --backend hf --port 8080
```

- Checked on one H20, read twice on: on 30 random Decision Index 0.3 rows, 81 of 82 answers were the same as in our
  Gen5.5 SGLang run; the other one is a near-tie (top two options within 0.06). Requests took 264 ms median one at a
  time, about six times slower than SGLang (no prefix cache, and a request read twice is about twice as long).
- Images need the SGLang backend.

## Decision Index run

- Suite rows: the 140,620 rows that `decision-index run --edition 0.3` sends: `selected-rows.jsonl.gz`,
  `added-rows.jsonl.gz` and `gsm8k-rows.jsonl.gz` of `suite-0.3`, with ToolRet, BRIGHT and ACOS cut to their scoring
  subsets.
- Two identical servers ran on two GPUs, one each, with the settings above. The rows are split round-robin into 32
  shards, 16 per server. Each shard is a resumable `decision-index run` against its server.
- The run used this `knowline_server.py` rendering with `--read-twice --twice-max-tokens 3000` given explicitly; the
  released file differs only in its docstring, the model name and in having read twice on by default.

```bash
decision-index run --edition 0.3 --engine http --option base_url=http://127.0.0.1:<port> --option model=m --no-verify \
  --compact --rows shards/<i>.jsonl.gz --out shards/<i>          # i = 0..31, run in parallel; 16 shards per server
cat shards/*/results.jsonl > results.jsonl
decision-index score --suite-dir suite-0.3 --results results.jsonl --engine http --out score
```

## Hardware and latency

- Two NVIDIA H20 (96 GB each), driver 590.48.01, one server per GPU.
- **Latency and repeatability:** we sent the same 300 random Decision Index 0.3 rows (477 questions) as for Gen5, one at a
  time, to one server on one H20 (`serve_knowline.sh`, after a warm-up).
  - Requests took 42.1 ms median, 82.9 ms mean, 99.1 ms at the 80th percentile and 297.3 ms at the 95th.
  - 451 of the 477 answers were the same as in our published Gen5 run; the prompts differ, so some answers move.
  - Gen5 on the same rows and hardware: 31.6 ms median, 58.8 ms mean and 143.9 ms at the 95th percentile.
- Latency was not measured on the board's reference hardware (1x RTX PRO 6000, latency-v1).

## One-command Decision Index run

`knowline_engine.py` (in this repository) is a Decision Index engine. It runs the same front end in process, so there
is no server to start by hand:

```bash
pip install "sglang==0.5.21" "transformers==5.12.1" requests        # plus the decision-index kit
git clone https://huggingface.co/PelaAI/KnowLine-4B-Gen5.5 && cd KnowLine-4B-Gen5.5   # puts the three files on the path
python -m decision_index pipeline --engine knowline_engine:KnowLine \
    --option model=PelaAI/KnowLine-4B-Gen5.5 --option revision=<commit> --out runs/KnowLine-4B-Gen5.5
```

- **Default backend and layout (the setting of our runs):** read twice is on; the engine starts SGLang with the flags above (FP8 at load,
  `--mem-fraction-static 0.72`) on a free local port and stops it when the run ends. Use `--option gpu=<n>` to pick a
  GPU, and `--option sglang_python=<python>` if SGLang lives in another environment.
- **`--option backend=hf`:** transformers only, bf16, no server; slower, and not the setting of our runs.
- **Limits:** up to 64 questions per request and 255 options per question. Larger requests are reported as
  unsupported; nothing is truncated.
- **Temperature in both backends:** transformers (`Qwen3_5RMSNorm`) and SGLang (`GemmaRMSNorm`) both apply the final
  norm as `(1 + w) * x`, so both backends apply the folded temperature. Our Decision Index run and calibration numbers
  use SGLang.

## Acknowledgements

- Read-twice layout: FlexDM ([github.com/1000luca/FlexDM](https://github.com/1000luca/FlexDM), MIT licence).
- Input repetition: Xu et al., 2023, "Re-Reading Improves Reasoning in Large Language Models"
  ([arXiv:2309.06275](https://arxiv.org/abs/2309.06275)).
