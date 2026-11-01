"""Native d1 choice LoRA: preserve encoding, set attention and option readout."""
import argparse
import copy
import hashlib
import importlib
import json
import math
import random
import time
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F
from transformers import AutoModel


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LoRALinear(nn.Module):
    """Standard W + alpha/r B A; FP32 trainable adapters, frozen BF16 base."""
    def __init__(self, base, rank=16, alpha=32, dropout=0.05):
        super().__init__()
        self.base = base
        self.rank, self.scale = rank, alpha / rank
        self.dropout = nn.Dropout(dropout)
        self.A = nn.Parameter(torch.empty(rank, base.in_features, device=base.weight.device, dtype=torch.float32))
        self.B = nn.Parameter(torch.zeros(base.out_features, rank, device=base.weight.device, dtype=torch.float32))
        nn.init.kaiming_uniform_(self.A, a=math.sqrt(5))

    def forward(self, x):
        residual = F.linear(F.linear(self.dropout(x), self.A.to(x.dtype)), self.B.to(x.dtype))
        return self.base(x) + residual * self.scale

    def merged(self):
        self.base.weight.data.add_((self.B @ self.A * self.scale).to(self.base.weight.dtype))
        return self.base


def inject(model):
    model.requires_grad_(False)
    names = [n for n, m in model.named_modules()
             if isinstance(m, nn.Linear) and n.endswith((".q_proj", ".v_proj"))
             and "language_model" in n and "vision" not in n]
    if not names:
        raise RuntimeError("No verified text-only q/v targets; inspect actual module names.")
    for name in names:
        parent_name, child = name.rsplit(".", 1)
        parent = model.get_submodule(parent_name)
        setattr(parent, child, LoRALinear(getattr(parent, child)))
    return names


def adapter_state(model):
    return {n: p.detach().cpu() for n, p in model.named_parameters()
            if n.endswith((".A", ".B"))}


def load_adapter(model, path):
    state = torch.load(path, map_location="cpu", weights_only=True)
    params = dict(model.named_parameters())
    assert set(state) == {n for n in params if n.endswith((".A", ".B"))}
    with torch.no_grad():
        for name, value in state.items():
            params[name].copy_(value)


def merge(model):
    for name, module in list(model.named_modules()):
        if isinstance(module, LoRALinear):
            parent, child = name.rsplit(".", 1)
            setattr(model.get_submodule(parent), child, module.merged())


class Native:
    def __init__(self, model_path, lora=False, seed=11012026):
        random.seed(seed)
        torch.manual_seed(seed)
        torch.set_num_threads(2)
        self.model = AutoModel.from_pretrained(
            str(model_path), trust_remote_code=True, local_files_only=True,
            dtype=torch.bfloat16,
        ).to("cuda").eval()
        package = type(self.model).__module__.rsplit(".", 1)[0]
        self.prompt = importlib.import_module(package + ".prompt")
        self.slots = importlib.import_module(package + ".slots")
        self.attention = importlib.import_module(package + ".attention")
        # Never initialize the inference runner's irreversible fused projections
        # on the trainable model; preserve the official separate linear weights.
        original_fuse = self.model.fuse_projections
        self.model.fuse_projections = lambda: None
        self.engine = self.model.engine
        self.model.fuse_projections = original_fuse
        self.targets = inject(self.model) if lora else []

    def encode(self, request):
        keys = list(request["questions"])
        qs = [self.prompt.as_question(q) for q in request["questions"].values()]
        sequences = self.engine._sequences([(request["state"], qs, [])])
        return keys, qs, sequences

    def batch_scores(self, qs, seqs, batch):
        slots, indexes = [], []
        for row, b in enumerate(batch):
            start = seqs[b][1]
            for i, ends in enumerate(seqs[b][5]):
                assert len(ends) == 1, "Only single-choice answer slots are trained"
                j = start + i
                slots.append((row, (0, j), qs[j], ends[0]))
                indexes.append(j)
        logz, _ = self.engine._slot_logits(seqs, batch, slots, None)
        scores = []
        for row, j in enumerate(indexes):
            groups = self.prompt.readout_ids(self.engine.tokenizer, qs[j])
            # Exactly the official max over aliases per option, kept in torch.
            scores.append(torch.stack([logz[row, group].max() for group in groups]))
        return indexes, scores

    def train_task(self, request, labels, divisor=1):
        keys, qs, seqs = self.encode(request)
        active = sum(v != "omit" for v in labels.values())
        inactive = len(keys) - active
        both = active > 0 and inactive > 0
        total = 0.0
        # One original question set per microbatch: no changed question grouping.
        for b in range(len(seqs)):
            indexes, scores = self.batch_scores(qs, seqs, [b])
            terms = []
            for j, score in zip(indexes, scores):
                key = keys[j]
                target = list(request["questions"][key]["criteria"]).index(labels[key])
                weight = (0.5 if both else 1.0) / (active if labels[key] != "omit" else inactive)
                terms.append(F.cross_entropy(score[None].float(), torch.tensor([target], device="cuda")) * weight)
            loss = torch.stack(terms).sum()
            if not torch.isfinite(loss):
                raise RuntimeError("Nonfinite training loss")
            total += float(loss.detach())
            (loss / divisor).backward()
        return total

    @torch.inference_mode()
    def infer(self, request):
        return self.model.system_one(request["state"], request["questions"])

    @torch.inference_mode()
    def check_native_scores(self, request):
        keys, qs, seqs = self.encode(request)
        predictions = {}
        max_prob_diff = 0.0
        for batch in self.engine._batches(seqs):
            indexes, scores = self.batch_scores(qs, seqs, batch)
            for j, score in zip(indexes, scores):
                key = keys[j]
                probs = (score / self.engine.calibration.temperature(qs[j])).softmax(-1)
                predictions[key] = (list(request["questions"][key]["criteria"])[int(probs.argmax())],
                                    probs.cpu().tolist())
        official = self.infer(request)
        for key, (choice, probs) in predictions.items():
            assert choice == official["answers"][key]["choice"], (key, choice, official["answers"][key])
            got = official["answers"][key]["probabilities"]
            values = [got[k] for k in request["questions"][key]["criteria"]]
            max_prob_diff = max(max_prob_diff, max(abs(a-b) for a, b in zip(probs, values)))
        assert max_prob_diff < 2e-5, max_prob_diff
        return {"choices_equal": True, "max_probability_difference": max_prob_diff,
                "tokens": official["usage"]["input_tokens"], "sequence_lengths": [len(s[2]) for s in seqs]}


def request_for(template, row, rng=None, reverse=False):
    request = copy.deepcopy(template)
    state = json.loads(request["state"])
    state["query"] = row["query"]
    request["state"] = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    if rng:
        items = list(request["questions"].items())
        rng.shuffle(items)
        request["questions"] = dict(items)
    for question in request["questions"].values():
        choices = list(question["criteria"].items())
        if rng:
            rng.shuffle(choices)
        elif reverse:
            choices.reverse()
        question["criteria"] = dict(choices)
    return request


def grad_stats(model):
    values = [(n, p.grad) for n, p in model.named_parameters() if p.requires_grad]
    assert all(g is not None and torch.isfinite(g).all() for _, g in values)
    return {"trainable_tensors": len(values),
            "nonzero_grad_tensors": sum(bool(g.abs().max() > 0) for _, g in values),
            "norm": math.sqrt(sum(float(g.float().square().sum()) for _, g in values))}


def evaluate(native, template, rows, path):
    native.model.eval()
    results = []
    with path.open("w") as out:
        for row in rows:
            req = request_for(template, row)
            started = time.perf_counter()
            raw = native.infer(req)
            torch.cuda.synchronize()
            choices = {k: a["choice"] for k, a in raw["answers"].items()}
            expected = row["labels"]
            extra = sum(v != "omit" and v != expected[k] for k, v in choices.items())
            missing = sum(v != "omit" and v != choices[k] for k, v in expected.items())
            result = {"id": row["id"], "correct": choices == expected, "extra": extra,
                      "missing": missing, "choices": choices, "raw": raw,
                      "elapsed_ms": (time.perf_counter()-started)*1000}
            results.append(result)
            out.write(json.dumps(result, ensure_ascii=False) + "\n")
            out.flush()
    return {"tasks": len(rows), "correct": sum(r["correct"] for r in results),
            "extra": sum(r["extra"] for r in results), "missing": sum(r["missing"] for r in results)}


def smoke(args):
    out = args.root / "smoke"
    out.mkdir(exist_ok=False)
    native = Native(args.model, lora=True)
    template = json.loads((args.root / "template.json").read_text())
    row = json.loads((args.root / "train.json").read_text())[0]
    req = request_for(template, row)
    verification = native.check_native_scores(req)
    save(out / "encoding.json", verification)
    save(out / "modules.json", {
        "targets": native.targets, "trainable": sum(p.numel() for p in native.model.parameters() if p.requires_grad),
        "total": sum(p.numel() for p in native.model.parameters()),
        "torch": torch.__version__, "model_type": type(native.model).__name__,
    })
    native.model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    frozen = {n: p._version for n, p in native.model.named_parameters() if not p.requires_grad}
    optim = torch.optim.AdamW([p for p in native.model.parameters() if p.requires_grad], lr=5e-5)
    losses, gradients, durations = [], [], []
    for step in range(8):
        native.model.train()
        optim.zero_grad(set_to_none=True)
        started = time.perf_counter()
        loss = native.train_task(req, row["labels"])
        gradients.append(grad_stats(native.model))
        torch.nn.utils.clip_grad_norm_([p for p in native.model.parameters() if p.requires_grad], 1.0)
        optim.step()
        torch.cuda.synchronize()
        losses.append(loss)
        durations.append(time.perf_counter()-started)
        print(json.dumps({"smoke_step": step+1, "loss": loss, "seconds": durations[-1]}), flush=True)
    assert all(p._version == frozen[n] for n, p in native.model.named_parameters() if n in frozen)
    assert losses[-1] < losses[0], losses
    path = out / "adapter.pt"
    torch.save(adapter_state(native.model), path)
    native.model.eval()
    prediction = native.infer(req)
    load_adapter(native.model, path)
    assert prediction["answers"] == native.infer(req)["answers"]
    save(out / "result.json", {"passed": True, "losses": losses, "gradients": gradients,
                              "step_seconds": durations, "frozen_weights_unchanged": True,
                              "adapter_reload_equal": True, "max_gpu_bytes": torch.cuda.max_memory_allocated(),
                              "prediction": prediction})


def train(args):
    out = args.root / "training"
    out.mkdir(exist_ok=False)
    native = Native(args.model, lora=True)
    template = json.loads((args.root / "template.json").read_text())
    rows = json.loads((args.root / "train.json").read_text())
    dev = json.loads((args.root / "dev.json").read_text())
    baseline = evaluate(native, template, dev, out / "dev-base.jsonl")
    native.model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    params = [p for p in native.model.parameters() if p.requires_grad]
    frozen = {n: p._version for n, p in native.model.named_parameters() if not p.requires_grad}
    optimizer = torch.optim.AdamW(params, lr=5e-5, weight_decay=0.01)
    rng = random.Random(11012026)
    rng.shuffle(rows)
    checkpoints = []
    started = time.time()
    optimizer.zero_grad(set_to_none=True)
    with (out / "steps.jsonl").open("w") as log:
        for index, row in enumerate(rows, 1):
            native.model.train()
            t = time.perf_counter()
            req = request_for(template, row, rng)
            loss = native.train_task(req, row["labels"], divisor=16)
            if index % 16 == 0:
                stats = grad_stats(native.model)
                torch.nn.utils.clip_grad_norm_(params, 1.0)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
            else:
                stats = None
            torch.cuda.synchronize()
            entry = {"example": index, "id": row["id"], "loss": loss,
                     "seconds": time.perf_counter()-t, "gradients": stats,
                     "max_gpu_bytes": torch.cuda.max_memory_allocated()}
            log.write(json.dumps(entry)+"\n")
            log.flush()
            if index % 16 == 0:
                print(json.dumps(entry), flush=True)
                save(out / "progress.json", {**entry, "total": len(rows),
                                            "elapsed_seconds": time.time()-started})
            if index in (256, 512, 1024):
                checkpoint = out / f"adapter-{index}.pt"
                torch.save(adapter_state(native.model), checkpoint)
                summary = evaluate(native, template, dev, out / f"dev-{index}.jsonl")
                checkpoints.append({"examples": index, "path": checkpoint.name,
                                    "sha256": sha(checkpoint), **summary})
                save(out / "checkpoints.json", checkpoints)
    assert all(p._version == frozen[n] for n, p in native.model.named_parameters() if n in frozen)
    selected = max(checkpoints, key=lambda r: (r["correct"], -r["extra"]-r["missing"], -r["examples"]))
    save(out / "selection.json", {"baseline": baseline, "checkpoints": checkpoints, "selected": selected,
                                 "heldout_used": False, "frozen_weights_unchanged": True,
                                 "elapsed_seconds": time.time()-started})
    print("TRAINING_COMPLETE", json.dumps(selected), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["smoke", "train"])
    parser.add_argument("--root", type=Path, default=Path("/opt/ac-liquid-lora"))
    parser.add_argument("--model", type=Path, default=Path("/opt/ac-input-tests/models/liquid"))
    args = parser.parse_args()
    globals()[args.phase](args)
