---
base_model: Qwen/Qwen3.5-2B-Base
datasets:
- ccdv/arxiv-classification
- clinc/clinc_oos
- community-datasets/yahoo_answers_topics
- dair-ai/emotion
- fancyzhx/ag_news
- fancyzhx/dbpedia_14
- google-research-datasets/paws
- google/boolq
- google/civil_comments
- legacy-datasets/banking77
- mteb/amazon_massive_intent
- nyu-mll/glue
- osyvokon/pavlick-formality-scores
- papluca/language-identification
- qiaojin/PubMedQA
- raquiba/Sarcasm_News_Headline
- sealuzh/app_reviews
- SetFit/20_newsgroups
- SetFit/sst5
- SetFit/subj
- SetFit/TREC-QC
- tals/vitaminc
- tasksource/ruletaker
- ucberkeley-dlab/measuring-hate-speech
- ucirvine/sms_spam
- Yelp/yelp_review_full
- nvidia/HelpSteer2
- tasksource/Boardgame-QA
- hotpotqa/hotpot_qa
library_name: peft
license: apache-2.0
pipeline_tag: text-classification
tags:
- strands-decider
- decision-model
- hobson
- lora
- peft
- qwen3.5
- classification
- calibration
- typed-decisions
base_model_relation: adapter
model-index:
- name: hobson-2b-v19
  results:
  - task:
      type: text-classification
    dataset:
      name: JevBench public, served at 4096
      type: jevbench
      config: w4096
    metrics:
    - type: accuracy
      value: 0.7229
      name: accuracy (167/231)
  - task:
      type: text-classification
    dataset:
      name: JevBench public, served at 3072
      type: jevbench
      config: w3072
    metrics:
    - type: accuracy
      value: 0.7229
      name: accuracy (167/231)
  - task:
      type: text-classification
    dataset:
      name: 'eval: held-out short tasks'
      type: hobson-internal
      config: 'eval: held-out short tasks'
    metrics:
    - type: accuracy
      value: 0.641
      name: accuracy (n=6000)
  - task:
      type: text-classification
    dataset:
      name: 'eval: boardgame'
      type: hobson-internal
      config: 'eval: boardgame'
    metrics:
    - type: accuracy
      value: 0.822
      name: accuracy (n=900)
  - task:
      type: text-classification
    dataset:
      name: 'eval: contractnli'
      type: hobson-internal
      config: 'eval: contractnli'
    metrics:
    - type: accuracy
      value: 0.872
      name: accuracy (n=1026)
  - task:
      type: text-classification
    dataset:
      name: 'eval: hotpotqa (held out)'
      type: hobson-internal
      config: 'eval: hotpotqa (held out)'
    metrics:
    - type: accuracy
      value: 0.717
      name: accuracy (n=959)
  - task:
      type: text-classification
    dataset:
      name: 'eval: musique'
      type: hobson-internal
      config: 'eval: musique'
    metrics:
    - type: accuracy
      value: 0.884
      name: accuracy (n=1199)
  - task:
      type: text-classification
    dataset:
      name: 'eval: musique, answerable'
      type: hobson-internal
      config: 'eval: musique, answerable'
    metrics:
    - type: accuracy
      value: 0.87
      name: accuracy (n=599)
  - task:
      type: text-classification
    dataset:
      name: 'eval: musique, unanswerable'
      type: hobson-internal
      config: 'eval: musique, unanswerable'
    metrics:
    - type: accuracy
      value: 0.898
      name: accuracy (n=600)
  - task:
      type: text-classification
    dataset:
      name: 'eval: [4] adequacy_hs2'
      type: hobson-internal
      config: 'eval: [4] adequacy_hs2'
    metrics:
    - type: accuracy
      value: 0.722
      name: accuracy (n=234)
  - task:
      type: text-classification
    dataset:
      name: 'eval: [5] gen:adequacy'
      type: hobson-internal
      config: 'eval: [5] gen:adequacy'
    metrics:
    - type: accuracy
      value: 0.798
      name: accuracy (n=302)
---

# strands-decider-2B-hobson-v19

Strands decider is a small, fast decision model for agentic AI. Unlike an LLM, which can
generate arbitrary text, a decision model picks between sets of options and rates things on
a scale, and every answer carries a calibrated confidence. It fits the decisions inside an
agentic workflow: model routing, tool selection, argument checking, triage, guardrails,
evaluations, and the rote decisions of a hybrid agent that leaves the hard ones to an LLM.

This repository holds one trained checkpoint: a LoRA adapter on `Qwen/Qwen3.5-2B-Base` plus a
small readout head that scores the options of a typed question (`noul`, a yes/no question;
`choice`, one of N options; `score`, a level on an ordered scale). The code, the training
recipe, the data inventory and the evaluations are at https://github.com/strands-labs/strands-decider, under the same
Apache-2.0 license as this model (see `LICENSE.md`).

## Use

```bash
pip install strands-decider
```

Ask one or more questions about a state. Pass `--device cuda`, `mps` or `cpu`; without it,
the best available device is used. The base weights download from the Hub at first use.

```bash
strands-decider ask StrandsAgents/strands-decider-2B-hobson-v19 \
  --state "Help! My payouts have been failing for 3 days! " \
  --choice "Which team should handle this?=billing,sales,retail" \
  --noul "Does this convey urgency?" \
  --score "How frustrated is the writer?=calm,frustrated,depressed"
```

The output of the v19 reference checkpoint (a retrain gives somewhat different numbers
with the same answers):

```
noul_0 noul = 0.829
choice_0 -> billing (confidence 0.769)
  billing                  0.846
  retail                   0.090
  sales                    0.064
score_0 score = 1.10 (confidence 0.519)
  0: calm                                     0.163
  1: frustrated                               0.574
  2: depressed                                0.263
```

Or serve it over HTTP. The server binds to `127.0.0.1` and has no authentication: use it
for local experiments.

```bash
strands-decider serve StrandsAgents/strands-decider-2B-hobson-v19 --port 8000
curl -s localhost:8000/v1/systemone -H 'content-type: application/json' -d '{
  "state": "Help! My payouts have been failing for 3 days!",
  "questions": {"is_urgent": {"type": "noul", "instructions": "Does this convey urgency?"}}
}'
```

In Python, `strands_decider.modeling.StrandsDeciderModel.load("StrandsAgents/strands-decider-2B-hobson-v19")`. The adapter in
`lora/` is a standard PEFT adapter on the Qwen3.5 text decoder
(`transformers.Qwen3_5ForCausalLM(...).model`); the head is `head.safetensors`.

## Results

| evaluation | tasks right | Brier | ECE | served |
| --- | --- | --- | --- | --- |
| JevBench public, window 4096 | 167/231 | 0.348 | 0.050 | these files |
| JevBench public, window 3072 | 167/231 | 0.349 | 0.056 | a copy with window 3072; weights symlinked, not hashed |

| internal set | accuracy | n |
| --- | --- | --- |
| eval: held-out short tasks | 0.641 | 6,000 |
| eval: boardgame | 0.822 | 900 |
| eval: contractnli | 0.872 | 1,026 |
| eval: hotpotqa (held out) | 0.717 | 959 |
| eval: musique | 0.884 | 1,199 |
| eval: musique, answerable | 0.870 | 599 |
| eval: musique, unanswerable | 0.898 | 600 |
| eval: [4] adequacy_hs2 | 0.722 | 234 |
| eval: [5] gen:adequacy | 0.798 | 302 |

JevBench is the external benchmark (231 public tasks); the internal sets are this recipe's
held-out short tasks, multi-step documents and answer-adequacy judgements.
`evaluation/README.md` in the code repository describes each set, and its results pages
give the figures by version. Per-skill results and the raw reports and logs are in
`eval/summary.json` and `eval/internal/`.

## Limitations

- **Questions are read less than documents.** With the state and options fixed, a changed
  question often gets the same answer. Phrase a question so the obvious reading is the
  intended one.
- **Long, multi-step documents are the weak spot**: JevBench's hard tier scores far below
  its easy tier.
- **`score` and `noul` transfer poorly** to rubrics and yes/no tasks unlike the training
  mix. Train on a rubric resembling yours.
- **Calibration is one temperature per primitive**, fitted on held-out short
  classification. The confidence bands are established there only: measure on your own
  traffic before you trust a threshold.
- **Trained on public datasets**, so it inherits their domains and their label noise.

`evaluation/README.md`, section "Limitations", has the measured figures behind each point.

## Training data

The `datasets` list in the metadata holds the Hub datasets that the recipe reads.
`hotpotqa/hotpot_qa` is for evaluation only. The recipe also uses these sources:

- ContractNLI and MuSiQue, from their authors' releases (not from the Hub).
- Synthetic rows that open-weight language models generated and checked.
- The output distributions of the frozen teacher model `Qwen/Qwen3.5-4B`. They are training
  targets, directly or through a parent model that the recipe trains first.

In the code repository, `data/sources.md` lists every source with its revision, role,
license and attribution, and `data/README.md` states what is committed, what is downloaded
and the reproduction contract.

## Training

Trained by `training/recipe.sh all` of the code repository on a `p5.48xlarge`
host (NVIDIA H100 80GB HBM3): recipe wall clock 4204 s, training stage
1685 s. Stage timings: `training/stages.jsonl`; data hashes:
`training/data_sha256.txt`; configs: `train_config.json`, `training/configs/`.

To retrain, run the same recipe on a Linux or WSL2 host with NVIDIA GPUs: about 11 hours
on one RTX 3090, or about 1 h 10 min on eight H100s with `NGPU=8 FAST=1` through the AWS
runner. `training/README.md` has the setup, the stages and the hardware notes.

## Provenance

`provenance.json`: base model and revision (inferred: the hosts did not pin one), and the
sha256 of the config, adapter, head and source pickle. `MANIFEST.sha256` lists every file;
`python -m strands_decider.hf_export verify <folder>` checks them. The run records keep
their timings and results; host paths, cloud identifiers and cost fields are removed.
