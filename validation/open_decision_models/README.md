# Open-weight decision models on one NVIDIA L4

2026-10-29 · [中文](README.zh.md)

We tested Strands Decider v19, Liquid d1-2B, Perplexity Decider Flash v1.2, KnowLine-4B-Gen5.5 and H2O-Lightning-4B v1.4.1 sequentially on the existing **g6.xlarge: L4 24 GB, 4 vCPUs, 16 GiB RAM**. Jev 1.14.0 and GPT 6.1 Sol low are API controls. Strands uses native CUDA; the online vLLM instance did not participate. No model weights were fine-tuned for this test.

The legacy GPU controller resumed a background model during the initial round. Those observations are retained in `initial_shared_gpu/` and excluded below. Final GPU results come from the isolated repeat with the controller paused and a GPU-memory check before each model. See [correction record](isolation_correction.json). API controls reuse their original calls.

## Quality

89 independent cases, each in original and reversed candidate order: 178 quality requests per model, 1246 total. A multi-question case passes only if every choice matches the frozen reference. Failures remain in the denominator. These are **reference-policy matches**, not general accuracy or official JevBench scores.

| Model | Payment steps | Routing | Device actions | Temperature sets | Call/format failures |
| --- | --- | --- | --- | --- | --- |
| Strands Decider v19 | 66/80 | 26/64 | 13/24 | 10/10 | 0 |
| Liquid d1-2B | 77/80 | 35/64 | 17/24 | 10/10 | 0 |
| Perplexity Decider Flash v1.2 | 80/80 | 47/64 | 16/24 | 9/10 | 0 |
| KnowLine-4B-Gen5.5 | 80/80 | 42/64 | 19/24 | 10/10 | 0 |
| H2O-Lightning-4B v1.4.1 | 80/80 | 54/64 | 17/24 | 10/10 | 0 |
| Jev 1.14.0 | 80/80 | 59/64 | 20/24 | 10/10 | 0 |
| GPT 6.1 Sol low | 78/80 | 59/64 | 14/24 | 10/10 | 12 |

Payment uses 40 snapshots: four scenarios × pending/ready × five stages, with the same optimized input for every model. Later snapshots follow the reference trajectory; this is not an autonomous transaction rollout. Routing reuses 32 frozen validation cases with catalogue facts and synthetic endpoint conditions; no selected downstream model is invoked. Device cases contain three decisions over power, integer temperature and mode. The five temperature-set cases use 15 independent binary questions for all models.

References are used only for offline grading. See [inputs](requests.json), [references](references.json), and [frozen plan](plan.json).

### Task classification versus constrained model selection

| Model | Task-profile routing | Capabilities | Cost/budget | Availability/fallback/preferences |
| --- | --- | --- | --- | --- |
| Strands Decider v19 | 16/16 | 2/16 | 5/16 | 3/16 |
| Liquid d1-2B | 16/16 | 12/16 | 2/16 | 5/16 |
| Perplexity Decider Flash v1.2 | 16/16 | 10/16 | 8/16 | 13/16 |
| KnowLine-4B-Gen5.5 | 16/16 | 6/16 | 7/16 | 13/16 |
| H2O-Lightning-4B v1.4.1 | 15/16 | 16/16 | 11/16 | 12/16 |
| Jev 1.14.0 | 16/16 | 13/16 | 14/16 | 16/16 |
| GPT 6.1 Sol low | 11/16 | 16/16 | 16/16 | 16/16 |

Strands, Liquid, Perplexity, KnowLine and Jev match all 16 task-profile observations. GPT requests missing material in five cases where the task description says source code, a trace or a proof is supplied. This benchmark asks which workflow should handle that description, without executing the downstream task. These differences reflect interpretation of the task boundary; they should not be read as a universal intelligence ranking.

## Latency

Median successful quality-request latency in milliseconds. Requests contain one, three or fifteen decisions.

| Model | Payment | Routing | Three device decisions | Fifteen temperature decisions |
| --- | --- | --- | --- | --- |
| Strands Decider v19 | 65.4 | 188.8 | 232.6 | 277.1 |
| Liquid d1-2B | 38.6 | 114.3 | 60.6 | 71.7 |
| Perplexity Decider Flash v1.2 | 144.8 | 500.1 | 247.6 | 290.2 |
| KnowLine-4B-Gen5.5 | 314.6 | 1153.1 | 851.7 | 3188.8 |
| H2O-Lightning-4B v1.4.1 | 93.4 | 275.0 | 201.0 | 369.3 |
| Jev 1.14.0 | 74.9 | 87.3 | 80.0 | 74.3 |
| GPT 6.1 Sol low | 920.6 | 1022.2 | 1023.5 | 2268.8 |

GPU calls use loopback on the inference host. API calls include network round trips from a us-east-1 development EC2. These are service-request measurements, not directly comparable pure GPU compute times.

Strands uses its original SDK. Liquid uses its official Transformers implementation. Perplexity uses `fast=False`. KnowLine uses its official HF BF16 fallback with read-twice, not the recommended SGLang FP8 deployment. The latter two lack the optional fast convolution and linear-attention kernels. H2O uses vLLM 0.30.0 with its pinned Python overlay, bidirectional attention, eager execution and an 8192-token context. These runs do not establish each model's optimized performance ceiling.

<details>
<summary>Warmed concurrency 1 / 4 / 8 results</summary>

Every level runs the same eight cases four times: 32 requests and 160 decisions. Model loading is excluded. P50/P95 include valid responses; throughput is valid requests divided by whole-batch elapsed time, not tokens/second. Strands, Liquid, Perplexity and KnowLine wrappers serialize CUDA execution, so concurrency adds queues rather than demonstrating their maximum batching capacity.

| Model | Concurrency | P50 ms | P95 ms | Valid requests/s | Valid responses |
| --- | --- | --- | --- | --- | --- |
| Strands Decider v19 | 1 | 208.6 | 279.8 | 5.69 | 32/32 |
| Strands Decider v19 | 4 | 594.1 | 1017.5 | 5.73 | 32/32 |
| Strands Decider v19 | 8 | 1394.3 | 1423.1 | 5.71 | 32/32 |
| Liquid d1-2B | 1 | 59.6 | 112.2 | 16.43 | 32/32 |
| Liquid d1-2B | 4 | 232.3 | 313.6 | 16.50 | 32/32 |
| Liquid d1-2B | 8 | 482.7 | 498.3 | 16.41 | 32/32 |
| Perplexity Decider Flash v1.2 | 1 | 244.6 | 512.8 | 4.14 | 32/32 |
| Perplexity Decider Flash v1.2 | 4 | 907.2 | 1333.0 | 4.14 | 32/32 |
| Perplexity Decider Flash v1.2 | 8 | 1938.8 | 1945.8 | 4.13 | 32/32 |
| KnowLine-4B-Gen5.5 | 1 | 849.2 | 3178.3 | 0.79 | 32/32 |
| KnowLine-4B-Gen5.5 | 4 | 4912.3 | 8355.5 | 0.79 | 32/32 |
| KnowLine-4B-Gen5.5 | 8 | 10066.0 | 10159.0 | 0.79 | 32/32 |
| H2O-Lightning-4B v1.4.1 | 1 | 205.5 | 362.2 | 4.85 | 32/32 |
| H2O-Lightning-4B v1.4.1 | 4 | 712.1 | 1256.9 | 5.08 | 32/32 |
| H2O-Lightning-4B v1.4.1 | 8 | 1182.8 | 2022.9 | 5.22 | 32/32 |
| Jev 1.14.0 | 1 | 69.3 | 126.6 | 12.60 | 32/32 |
| Jev 1.14.0 | 4 | 80.0 | 110.5 | 47.00 | 32/32 |
| Jev 1.14.0 | 8 | 77.0 | 107.7 | 91.42 | 32/32 |
| GPT 6.1 Sol low | 1 | 987.2 | 2582.4 | 0.70 | 31/32 |
| GPT 6.1 Sol low | 4 | 1020.5 | 3091.6 | 2.21 | 29/32 |
| GPT 6.1 Sol low | 8 | 1053.2 | 2235.5 | 4.79 | 31/32 |

[Machine-readable performance metrics](results/performance_summary.json).

</details>

## Actual choices and business effects

Original-order examples: (1) fully paid 129 USDC with 12/12 confirmations, expected `credit_order`; (2) reduce the current 26°C setting by two degrees, expected `24`; (3) route a supplied connection-pool deadlock debugging request, expected `code_analysis`.

| Model | Credit execution | Target temperature | Debugging workflow |
| --- | --- | --- | --- |
| Strands Decider v19 | hold | 18 | code_analysis |
| Liquid d1-2B | credit_order | 24 | code_analysis |
| Perplexity Decider Flash v1.2 | credit_order | 24 | code_analysis |
| KnowLine-4B-Gen5.5 | credit_order | 24 | code_analysis |
| H2O-Lightning-4B v1.4.1 | credit_order | 24 | code_analysis |
| Jev 1.14.0 | credit_order | 24 | code_analysis |
| GPT 6.1 Sol low | credit_order | JSON error | clarify |

Strands selects `hold` in this credit sample. `JSON error` means strict parsing failed; responses were not silently repaired or retried.

We also apply each payment choice to its independent frozen sandbox snapshot and compare final device settings:

| Model | Payment guard corrections | Simulated ledger entries/8 opportunities | Hard route violations/48 | False no-route/48 | Device final states/24 |
| --- | --- | --- | --- | --- | --- |
| Strands Decider v19 | 2 | 3/8 | 27 | 7 | 17/24 |
| Liquid d1-2B | 3 | 8/8 | 23 | 3 | 19/24 |
| Perplexity Decider Flash v1.2 | 0 | 8/8 | 3 | 9 | 18/24 |
| KnowLine-4B-Gen5.5 | 0 | 8/8 | 4 | 15 | 23/24 |
| H2O-Lightning-4B v1.4.1 | 0 | 8/8 | 7 | 0 | 17/24 |
| Jev 1.14.0 | 0 | 8/8 | 2 | 1 | 21/24 |
| GPT 6.1 Sol low | 0 | 6/8 | 0 | 0 | 14/24 |

These ledger entries are **independent simulated steps**, not real transfers or completed model-driven transaction rollouts. Eligible-but-not-preferred routes are recorded separately in [business_audit.json](results/business_audit.json). Devices start off, set to 26°C and heat mode. Final-state grading allows setting an already-current value to be equivalent to leaving it unchanged; strict action grading retains that difference.

## Liquid native multi-select

With `type: "choice", multiple: true` and all 15 integer candidates from 16 through 30, 5/5 cases match the exact requested set. Loopback latency is 30.9–32.2 ms. The inclusive range 22–25 returns `["22","23","24","25"]`; other cases cover explicit sets, exclusions and the empty set. This extra capability test uses original candidate order and is excluded from the paired quality table.

[Exact requests](liquid_native_multiselect.json) · [actual responses](results/liquid-native-multiselect.jsonl)

## Candidate-order sensitivity

| Model | Changed cases / pairs with two valid responses |
| --- | --- |
| Strands Decider v19 | 17/89 |
| Liquid d1-2B | 10/89 |
| Perplexity Decider Flash v1.2 | 5/89 |
| KnowLine-4B-Gen5.5 | 7/89 |
| H2O-Lightning-4B v1.4.1 | 3/89 |
| Jev 1.14.0 | 7/89 |
| GPT 6.1 Sol low | 1/81 |

The two orders are repeated observations of the same cases. For API models, differences may also include service numerical variation or generation randomness; this experiment does not attribute every change solely to position bias. GPT has fewer valid pairs because of formatting failures.

## Recommendations by use case

- **Local deployment with stronger reference adherence: H2O-Lightning 4B.** Payment 80/80, routing 54/64 and 161/178 exact cases are the best local-model results in this batch. Payment median is 93 ms. Seven hard-constraint violations in 48 constrained routes still require attention.
- **Low latency, device actions and multi-select: Liquid d1-2B.** Payment is 77/80 at a 39 ms median; three device decisions take 61 ms; native set selection passes 5/5. Complex routing remains weak at 35/64, including 23/48 hard-constraint violations.
- **Another payment candidate: Perplexity Flash.** Payment 80/80, all eight simulated ledger opportunities, and 145 ms median payment latency. Routing is 47/64; its current reference inference path is not a speed ceiling.
- **Final device settings: retain KnowLine for further comparison.** Strict actions match 19/24 and final states 23/24; payment is 80/80. The HF path is slower, with an 852 ms device median; test the recommended deployment before judging suitability for frequent calls.
- **Existing Strands: task-profile routing and validated local choices.** Task classification is 16/16 and median payment latency 65 ms, while payment reaches 66/80 and full routing 26/64. Clarify the scope of conditions, add counterexamples and explicit completion criteria, then evaluate fine-tuning on a held-out set. This round does not measure those proposed improvements.
- **Hosted API: Jev has the strongest overall reference adherence here.** It reaches 169/178, with payment/routing medians of 75/87 ms and 91.42 valid requests/s at concurrency eight. GPT matches all 48 constrained-routing observations, with payment/routing medians around 0.92/1.02 seconds, but has 12 quality-response format failures.

GPT uses a prompt-only JSON contract, without constrained structured decoding. Two payment and ten device responses fail strict parsing; the raw outputs are retained. Improve the output contract and retest before attributing those failures to reasoning ability. GPT matches 161/166 valid responses; the primary table still includes all 178 attempts.

These conclusions apply to these frozen inputs. Budget arithmetic, condition scope, missing-material interpretation and no-change semantics need business-specific checks; this is not a universal intelligence ranking.

## Evidence and reproduction

The original text model, vision service, GPU controller and schedule were restored after testing, with the instance left running. Temporary model environments and S3 installation artifacts were removed; measurement evidence is retained. See [restoration record](restoration.json).

[Quality summary](results/summary.json), [mismatches](results/mismatches.json), [raw results](results/), [pinned models and hashes](models.json), [hardware](hardware.json), and [order-preserving request hashes](ordered_request_hashes.json).

`prepare.py` freezes inputs; `run.py` calls providers and parses strictly; `analyze.py`, `business_audit.py` and `performance.py` grade offline. `gpu_server.py` wraps official implementations, and `trial.py` runs and terminates one model. Offline provisioning and temporary-control helpers are in this directory; credentials and signed manifests remain in ignored `.deployment/` files.

```bash
python -m unittest discover -s validation/open_decision_models -p 'test_*.py'
python validation/open_decision_models/analyze.py
.venv/bin/python validation/open_decision_models/business_audit.py
python validation/open_decision_models/performance.py
python validation/open_decision_models/report.py
```

Selection references: [JevBench](https://benchmarkheaven.com/jev-models), [API/methodology](https://benchmarkheaven.com/jev-models/api), and the [Liquid](https://huggingface.co/LiquidAI/d1-2B), [Perplexity](https://huggingface.co/perplexity-ai/pplx-decider-flash-v1.2), [KnowLine](https://huggingface.co/PelaAI/KnowLine-4B-Gen5.5), and [H2O](https://huggingface.co/h2oai/h2o-lightning-4b) model cards. This is not a full JevBench run; external leaderboard scores are not mixed into business results.
