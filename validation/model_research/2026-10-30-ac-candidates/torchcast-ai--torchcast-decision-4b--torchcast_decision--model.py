# Copyright 2026 Torchcast AI. Licensed under the Apache License, Version 2.0 (see LICENSE in this folder).
"""Torchcast Decision 4B inference (Qwen3.5-4B, bidirectional full-attention layers).

Every question becomes one prompt (render.py) and one forward pass; nothing is generated.  The answer is read at the
last prompt token: the final hidden state times the output-head rows of the letters A..Z (fp32), divided by the
temperature of the question type (decision_config.json) and normalised over the listed options.  A yes/no probability
whose max(P, 1 - P) is under noul_floor moves to the floor on its own side, so the answer never changes.

Attention.  Within a prompt the full-attention layers see every prompt token (a key-padding mask, no causal mask), as
in training; the linear-attention layers are causal.  Rows are right-padded, so padding never reaches a real token.

Passes.  A request of one to four questions whose prompts fit a recorded shape replays a CUDA graph captured at start-up
(one question up to 4,096 tokens, or two to four questions up to 1,024 tokens each).  Everything else runs eagerly,
longest prompts first, padded to the same length grid, so a request takes the same shapes and kernels either way.

Images.  A request may carry images as evidence.  The checkpoint's image processor resizes each image to at most
max_pixels pixels, the vision tower embeds it once per request, and the embeddings replace the image tokens in every
question's prompt, with the checkpoint's multimodal positions.  "<image>" in a string state marks where each image goes;
without marks the images come before the state.  Requests with images always run eagerly."""
import base64
import binascii
import bisect
import importlib
import io
import json
import os
import re
import warnings

import torch

from . import render as R

ATTENTION_MODE = "noncausal_full_attention"
GRAPH_LONGEST = 4096                 # one-question graphs up to this length
GRAPH_MAX_ROWS = 4                   # questions per request replayed as one graph
GRAPH_MULTI_LONGEST = 1024           # longest prompt in a graph of two or more questions
IMAGE_MARK = "<image>"
_IMAGE_SLOT = "\x00torchcast-image\x00"


def _length_grid(first=128, last=65536):
    """Padded lengths: steps of 64 from 128 to 512, then four steps per doubling (640, 768, 896, 1024, 1280, ...)."""
    grid, n, step = [], first, 64
    while n <= last:
        grid.append(n)
        if n >= 512 and n & (n - 1) == 0:
            step = n // 4
        n += step
    return tuple(grid)


LENGTH_GRID = _length_grid()


def pad_to(n):
    """Length of a padded batch whose longest prompt has n tokens (multiples of 8,192 past the grid)."""
    at = bisect.bisect_left(LENGTH_GRID, n)
    return LENGTH_GRID[at] if at < len(LENGTH_GRID) else (n + 8191) // 8192 * 8192


def choice_certainty(p):
    """TypeSafe Choice confidence: (p_max - 1/n) / (1 - 1/n), within [0, 1]."""
    if len(p) < 2:
        return 1.0
    n = len(p)
    value = (n * max(p) - 1) / (n - 1)
    return 0.0 if value < 0 else 1.0 if value > 1 else value


def score_certainty(p):
    """TypeSafe Score confidence: 1 - E|level - most likely level| / the same for an even spread around the middle."""
    levels = range(len(p))
    mode = max(levels, key=lambda i: p[i])
    spread = sum(p[i] * abs(i - mode) for i in levels)
    centre = (len(p) - 1) / 2
    even = sum(abs(i - centre) for i in levels) / len(p)
    if not even:
        return 1.0
    return max(0.0, 1 - spread / even)


def read_image(value, paths=True):
    """PIL image, image bytes, base64 text, a data URI or (paths=True) a file path -> RGB PIL image."""
    from PIL import Image, UnidentifiedImageError

    if isinstance(value, Image.Image):
        return value.convert("RGB")
    if isinstance(value, str) and paths and not value.startswith("data:") and os.path.isfile(value):
        with open(value, "rb") as f:
            value = f.read()
    elif isinstance(value, str):
        payload = value.partition(",")[2] if value.startswith("data:") else value
        try:
            value = base64.b64decode("".join(payload.split()), validate=True)
        except binascii.Error:
            raise ValueError("cannot decode the image: expected base64 text or a data URI") from None
    if not isinstance(value, (bytes, bytearray)):
        raise ValueError(f"cannot read an image from a {type(value).__name__}")
    try:
        return Image.open(io.BytesIO(value)).convert("RGB")
    except (UnidentifiedImageError, OSError) as e:
        raise ValueError(f"cannot read the image: {e}") from None


def linear_attention_kernels(path):
    """Whether transformers will run the flash-linear-attention / causal-conv1d kernels for the model in `path`."""
    import transformers

    model_type = transformers.AutoConfig.from_pretrained(path).model_type
    module = f"transformers.models.{model_type}.modeling_{model_type}"
    try:
        return bool(importlib.import_module(module).is_fast_path_available)
    except (ImportError, AttributeError):
        return False


def _bidirectional_full_attention(body):
    """Give the full-attention layers a key-padding mask instead of the causal mask.  Callers pass either a 2-D 0/1
    padding mask (turned here into the per-layer masks) or ready per-layer masks, which pass through unchanged.
    transformers >= 5.17 takes a {layer type: mask} dict; older 5.x takes one 4-D mask for the attention layers, and the
    linear-attention layers get their padding mask from _update_linear_attn_mask, which is redirected here."""
    legacy = hasattr(body, "_update_linear_attn_mask")
    if legacy:
        body._tc_linear_mask = None
        body._update_linear_attn_mask = lambda attention_mask, past_key_values: body._tc_linear_mask

    def linear_mask(padding, n):
        if padding is None or padding.ndim != 2 or n == 1 or torch.all(padding == 1):
            return None
        return padding[:, -n:].contiguous()

    def before_forward(module, args, kwargs):
        mask = kwargs.get("attention_mask")
        if isinstance(mask, dict) or (torch.is_tensor(mask) and mask.ndim == 4):
            return args, kwargs
        embeds = kwargs.get("inputs_embeds")
        ref = embeds if embeds is not None else kwargs["input_ids"]
        rows, n = ref.shape[0], ref.shape[1]
        padding = mask if mask is not None else torch.ones((rows, n), device=ref.device, dtype=torch.long)
        keys = padding[:, None, None, :].bool()
        if legacy:
            module._tc_linear_mask = linear_mask(padding, n)
            kwargs["attention_mask"] = keys
        else:
            kwargs["attention_mask"] = {"full_attention": keys, "linear_attention": linear_mask(padding, n)}
        return args, kwargs

    body.register_forward_pre_hook(before_forward, with_kwargs=True)
    return legacy


class TorchcastDecision:
    """decide(state, questions, images=None) -> (answers, usage) in the TypeSafe /v1/systemone format.

    images=False leaves the vision tower out; max_pixels bounds each image after resizing."""

    def __init__(self, path, device=None, max_length=R.BUDGET, max_batch_tokens=65536, graphs=True, images=True,
                 max_pixels=1 << 20, min_pixels=65536):
        import transformers

        if not os.path.isdir(path):
            raise FileNotFoundError(f"model folder not found: {path}")
        with open(os.path.join(path, "decision_config.json")) as f:
            settings = json.load(f)
        self._apply_settings(settings)
        self.tok = transformers.AutoTokenizer.from_pretrained(path)
        self.letters = R.letter_ids(self.tok)
        if self.letters != settings["letter_token_ids"]:
            raise ValueError("decision_config.json letter_token_ids do not match the tokenizer")
        self.device = torch.device(device) if device else torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._require_fast_kernels(path)

        model_config = transformers.AutoConfig.from_pretrained(path)
        model_class = getattr(transformers, model_config.architectures[0])
        full = model_class.from_pretrained(path, dtype=torch.bfloat16, device_map={"": self.device})
        self.body = getattr(full.model, "language_model", full.model).eval()
        out_rows = full.get_output_embeddings().weight
        self.letter_rows = out_rows.index_select(0, torch.tensor(self.letters, device=out_rows.device)).float().detach()
        self._attach_vision(full, path, images, max_pixels, min_pixels)
        del full, out_rows

        self.legacy_masks = _bidirectional_full_attention(self.body)
        self.pad = self.tok.pad_token_id
        self.max_length = int(max_length)
        self.max_batch_tokens = int(max_batch_tokens)
        self.budget = min(self.max_length, R.BUDGET)
        self._images = None                                 # vision embeddings of the request being decided
        self.graphs = {}
        if graphs and self.device.type == "cuda" and os.environ.get("TC_GRAPHS", "1") != "0":
            self._record_graphs()

    def _apply_settings(self, settings):
        if settings.get("prompt_format", R.VERSION) != R.VERSION:
            raise ValueError(f"prompt_format {settings.get('prompt_format')!r}: this package renders {R.VERSION}")
        if settings.get("attention_mode") != ATTENTION_MODE:
            raise ValueError(f"attention_mode {settings.get('attention_mode')!r}: this package runs {ATTENTION_MODE}")
        self.temperature = {kind: float(t) for kind, t in settings["temperature_by_type"].items()}
        self.noul_floor = float(settings.get("noul_floor", 0.0))
        if self.noul_floor and not 0.5 < self.noul_floor < 1.0:
            raise ValueError(f"noul_floor {self.noul_floor}: must be in (0.5, 1), or 0 to turn it off")
        many = settings.get("wide_choice", {})
        self.group = many.get("group", 25)
        self.keep = many.get("keep", 3)
        self.residual = many.get("residual", 1e-3)
        self.release_date = settings.get("release_date")
        self.model_name = settings.get("model_name")

    def _require_fast_kernels(self, path):
        self.fast_kernels = linear_attention_kernels(path)
        if self.fast_kernels or self.device.type != "cuda":
            return
        message = ("flash-linear-attention and causal-conv1d are not active: the linear-attention layers would run "
                   "transformers' plain torch path (over 10x slower). pip install flash-linear-attention causal-conv1d, "
                   "or set TC_ALLOW_SLOW=1 to run anyway.")
        if os.environ.get("TC_ALLOW_SLOW") != "1":
            raise RuntimeError(message)
        warnings.warn(message)

    def _attach_vision(self, full, path, wanted, max_pixels, min_pixels):
        self.vision = self.image_processor = None
        if not wanted:
            self.vision_note = "image input was switched off (--no-images)"
            return
        if getattr(full.model, "visual", None) is None:
            self.vision_note = "this checkpoint has no vision tower"
            return
        import transformers
        try:
            processor = transformers.AutoImageProcessor.from_pretrained(path)
        except (OSError, ImportError, ValueError) as e:
            self.vision_note = "the image processor could not be loaded: " + str(e).splitlines()[0][:200]
            return
        processor.size = {"longest_edge": int(max_pixels), "shortest_edge": int(min_pixels)}
        self.image_processor = processor
        self.vision = full.model.eval()                    # vision tower and multimodal positions; decoder = self.body
        self.image_token = full.config.image_token_id
        self.vision_note = ""

    # ---------------------------------------------------------------- CUDA graphs
    def _graph_masks(self, keep):
        """Per-layer masks for a graph's rows (keep: (rows, length) bool, True = real token)."""
        keys = keep[:, None, None, :]
        if self.legacy_masks:
            self.body._tc_linear_mask = None
            return keys
        return {"full_attention": keys, "linear_attention": None}

    def _letter_logits_at(self, ids, last, keep):
        with torch.autocast(self.device.type, dtype=torch.bfloat16):
            states = self.body(input_ids=ids, attention_mask=self._graph_masks(keep), use_cache=False,
                               return_dict=True).last_hidden_state
        rows = torch.arange(ids.shape[0], device=ids.device)
        return states[rows, last].float() @ self.letter_rows.T

    @torch.inference_mode()
    def _record_graphs(self):
        lengths = [n for n in LENGTH_GRID if n <= GRAPH_LONGEST]
        shapes = [(rows, n) for rows in range(1, GRAPH_MAX_ROWS + 1) for n in lengths
                  if rows == 1 or n <= GRAPH_MULTI_LONGEST]
        shapes.sort(key=lambda s: (-s[0] * s[1], -s[1]))   # largest first: it sizes the shared memory pool
        pool = None
        for rows, n in shapes:
            ids = torch.full((rows, n), self.pad, dtype=torch.long, device=self.device)
            last = torch.full((rows,), n - 1, dtype=torch.long, device=self.device)
            keep = torch.ones((rows, n), dtype=torch.bool, device=self.device)
            warm = torch.cuda.Stream(device=self.device)
            warm.wait_stream(torch.cuda.current_stream(self.device))
            with torch.cuda.stream(warm):
                for _ in range(3):                          # tune and warm every kernel before recording
                    self._letter_logits_at(ids, last, keep)
            torch.cuda.current_stream(self.device).wait_stream(warm)
            recorded = torch.cuda.CUDAGraph()
            with torch.cuda.graph(recorded, pool=pool):
                logits = self._letter_logits_at(ids, last, keep)
            pool = recorded.pool()
            self.graphs[(rows, n)] = (recorded, ids, last, keep, logits)

    def _graph_for(self, prompts):
        """Recorded length for these prompts (one per question), or None."""
        if not self.graphs or self._images is not None or not prompts:
            return None
        need = max(map(len, prompts))
        lengths = sorted(n for rows, n in self.graphs if rows == len(prompts) and n >= need)
        return lengths[0] if lengths else None

    @torch.inference_mode()
    def _replay(self, prompts, n):
        recorded, ids, last, keep, logits = self.graphs[(len(prompts), n)]
        host = torch.full((len(prompts), n), self.pad, dtype=torch.long)
        for row, p in enumerate(prompts):
            host[row, :len(p)] = torch.tensor(p)
        lengths = torch.tensor([len(p) for p in prompts])
        ids.copy_(host)
        keep.copy_(torch.arange(n)[None] < lengths[:, None])
        last.copy_(lengths - 1)
        recorded.replay()
        return logits.cpu()

    # ---------------------------------------------------------------- images
    def _state_with_images(self, state, count):
        text = R.state_as_text(state)
        marks = text.count(IMAGE_MARK)
        if marks == count:
            return text.replace(IMAGE_MARK, _IMAGE_SLOT)
        if marks:
            raise ValueError(f"{count} images but {marks} {IMAGE_MARK} marks in the state")
        if count == 1:
            lead = _IMAGE_SLOT
        else:
            lead = "\n".join(f"Image {k}: {_IMAGE_SLOT}" for k in range(1, count + 1))
        return lead if not text.strip() else lead + "\n\n" + text

    @torch.no_grad()
    def _embed_images(self, images):
        if self.vision is None:
            raise ValueError("images are not supported here: " + self.vision_note)
        pixels = self.image_processor(images=[read_image(x) for x in images], return_tensors="pt")
        grid = pixels["image_grid_thw"]
        with torch.autocast(self.device.type, dtype=torch.bfloat16):
            embedded = self.vision.get_image_features(pixels["pixel_values"].to(self.device), grid.to(self.device),
                                                      return_dict=True)
        per_token = self.vision.visual.spatial_merge_size ** 2
        return {"features": torch.cat(embedded.pooler_output, 0), "grid": grid,
                "tokens": (grid.prod(-1) // per_token).tolist()}

    def _image_prompt(self, q):
        """Prompt tokens of q in a request with images, with each token's multimodal position and vision row."""
        system, user = R.chat(q)
        pieces = user["content"].split(_IMAGE_SLOT)
        content = []
        for k, piece in enumerate(pieces):
            if k:
                content.append({"type": "image"})
            if piece:
                content.append({"type": "text", "text": piece})
        messages = [{"role": "system", "content": [{"type": "text", "text": system["content"]}]},
                    {"role": "user", "content": content}]
        sizes = list(self._images["tokens"])
        tokens = []
        for t in self.tok.encode(R.chat_text(self.tok, messages), add_special_tokens=False):
            if t == self.image_token:
                if not sizes:
                    raise ValueError("the prompt has more image places than the request has images")
                tokens += [t] * sizes.pop(0)
            else:
                tokens.append(t)
        if sizes:
            raise ValueError("the request has more images than the prompt has image places")
        if len(tokens) > self.max_length:
            raise ValueError(f"the prompt has {len(tokens)} tokens; the limit with images is {self.max_length}")
        ids = torch.tensor(tokens)
        is_image = ids == self.image_token
        positions, _ = self.vision.get_rope_index(ids[None], mm_token_type_ids=is_image.int()[None],
                                                  image_grid_thw=self._images["grid"])
        return tokens, positions[:, 0], torch.where(is_image, is_image.long().cumsum(0) - 1, -1)

    # ---------------------------------------------------------------- forward passes
    def _prompt(self, q):
        if self._images is not None:
            return self._image_prompt(q)
        return R.prompt_ids(q, self.tok, self.budget), None, None

    def _decoder(self, ids, prompts, **kwargs):
        ids = ids.to(self.device)
        if self._images is None:
            return self.body(input_ids=ids, **kwargs)
        embeds = self.body.get_input_embeddings()(ids)
        width = ids.shape[1]
        positions = torch.empty((3, ids.shape[0], width), dtype=torch.long)
        for row, (_, pos, vision_row) in enumerate(prompts):
            used = pos.shape[1]
            positions[:, row, :used] = pos
            positions[:, row, used:] = pos[:, -1:] + torch.arange(1, width - used + 1)
            where = torch.nonzero(vision_row >= 0).squeeze(1)
            if where.numel():
                embeds[row, where.to(self.device)] = self._images["features"][vision_row[where].to(self.device)].to(embeds.dtype)
        return self.body(inputs_embeds=embeds, position_ids=positions.to(self.device), **kwargs)

    @torch.no_grad()
    def letter_logits(self, questions):
        """[Question] -> ([letter logits per question, in option order], prompt tokens)."""
        prompts = [self._prompt(q) for q in questions]
        token_lists = [p[0] for p in prompts]
        sizes = [len(q.options) for q in questions]
        used = sum(map(len, token_lists))
        n = self._graph_for(token_lists)
        if n is not None:
            z = self._replay(token_lists, n)
            return [z[row, :c].clone() for row, c in enumerate(sizes)], used
        result = [None] * len(questions)
        order = sorted(range(len(questions)), key=lambda i: -len(token_lists[i]))
        while order:
            width = pad_to(len(token_lists[order[0]]))
            batch, order = order[:max(1, self.max_batch_tokens // width)], order[max(1, self.max_batch_tokens // width):]
            lengths = torch.tensor([len(token_lists[i]) for i in batch])
            ids = torch.full((len(batch), width), self.pad, dtype=torch.long)
            for row, i in enumerate(batch):
                ids[row, :len(token_lists[i])] = torch.tensor(token_lists[i])
            padding = (torch.arange(width)[None] < lengths[:, None]).long()
            with torch.autocast(self.device.type, dtype=torch.bfloat16):
                states = self._decoder(ids, [prompts[i] for i in batch], attention_mask=padding.to(self.device),
                                       use_cache=False, return_dict=True).last_hidden_state
            rows = torch.arange(len(batch), device=self.device)
            z = states[rows, (lengths - 1).to(self.device)].float() @ self.letter_rows.T
            for row, i in enumerate(batch):
                result[i] = z[row, :sizes[i]].cpu()
        return result, used

    def probabilities(self, questions):
        logits, used = self.letter_logits(questions)
        out = [torch.softmax(z / self.temperature.get(q.kind, 1.0), -1).tolist() for q, z in zip(questions, logits)]
        return out, used

    def graph_check(self, state, questions):
        """Largest |p_graph - p_eager| over the questions of one request (0.0 without graphs)."""
        if not self.graphs:
            return 0.0
        qs = [R.question(state, spec) for spec in questions.values()]
        replayed, _ = self.probabilities(qs)
        recorded, self.graphs = self.graphs, {}
        try:
            eager, _ = self.probabilities(qs)
        finally:
            self.graphs = recorded
        return max(abs(a - b) for pa, pb in zip(replayed, eager) for a, b in zip(pa, pb))

    # ---------------------------------------------------------------- answers
    def _many_options(self, state, spec):
        """Choice with more than 26 options -> ({id: probability}, prompt tokens): near-equal groups of at most
        `group`, the best `keep` of each group in a final round, the rest sharing `residual` of the probability in
        proportion to their first-round probabilities."""
        ids = list(spec["criteria"])
        count = -(-len(ids) // self.group)
        base, extra = divmod(len(ids), count)
        bounds = [0]
        for g in range(count):
            bounds.append(bounds[-1] + base + (g < extra))
        groups = [ids[a:b] for a, b in zip(bounds, bounds[1:])]

        def only(keys):
            return dict(spec, criteria={k: spec["criteria"][k] for k in keys})

        round_one, used = self.probabilities([R.question(state, only(g)) for g in groups])
        p_one = {}
        finalists = []
        for g, ps in zip(groups, round_one):
            p_one.update(zip(g, ps))
            finalists += [k for k, _ in sorted(zip(g, ps), key=lambda kp: -kp[1])[:self.keep]]
        if len(finalists) > R.MAX_OPTIONS:
            p_final, more = self._many_options(state, only(finalists))
        else:
            ps, more = self.probabilities([R.question(state, only(finalists))])
            p_final = dict(zip(finalists, ps[0]))
        finalist_set = set(finalists)
        others = [k for k in ids if k not in finalist_set]
        others_mass = sum(p_one[k] for k in others) or 1.0
        merged = {k: p_final[k] * (1 - self.residual) for k in finalists}
        for k in others:
            merged[k] = self.residual * p_one[k] / others_mass
        total = sum(merged.values())
        return {k: v / total for k, v in merged.items()}, used + more

    def _answer(self, q, p, spec):
        if q.kind == "noul":
            yes = p[q.ids.index("true")]
            # JevBench counts 0.2 < P(yes) < 0.8 as no answer: a weaker yes/no moves to the floor on its own side
            if self.noul_floor and max(yes, 1.0 - yes) < self.noul_floor:
                yes = self.noul_floor if yes >= 0.5 else 1.0 - self.noul_floor
            return {"type": "noul", "noul": yes}
        if q.kind == "score":
            scale = spec.get("criteria") or []
            names = [scale[k] for k in R.level_keys(scale)] if isinstance(scale, dict) else list(scale)
            legend = {str(i): names[i] if i < len(names) else str(i) for i in range(len(p))}
            expected = sum(level * prob for level, prob in enumerate(p))
            return {"type": "score", "score": expected, "confidence": score_certainty(p), "legend": legend,
                    "probabilities": {str(level): prob for level, prob in enumerate(p)}}
        dist = dict(zip(q.ids, p))
        return {"type": "choice", "choice": max(dist, key=dist.get), "confidence": choice_certainty(p),
                "probabilities": dist}

    def _sort(self, state, questions):
        """-> (answers that need no model pass, [(key, Question)], tokens of many-option rounds)."""
        settled, pending, used = {}, [], 0
        for key, spec in questions.items():
            options = spec.get("criteria") or {}
            many = isinstance(options, dict) and spec.get("type", "choice") == "choice"
            if many and len(options) == 1:
                (sole,) = options
                settled[key] = {"type": "choice", "choice": sole, "confidence": 1.0, "probabilities": {sole: 1.0}}
            elif many and len(options) > R.MAX_OPTIONS:
                dist, n = self._many_options(state, spec)
                used += n
                settled[key] = {"type": "choice", "choice": max(dist, key=dist.get),
                                "confidence": choice_certainty(list(dist.values())), "probabilities": dist}
            else:
                pending.append((key, R.question(state, spec)))
        return settled, pending, used

    def _finish(self, settled, pending, probs, questions):
        for (key, q), p in zip(pending, probs):
            settled[key] = self._answer(q, p, questions[key])
        return settled

    def decide(self, state, questions, images=None):
        """One request -> (answers, usage).  images: PIL images, file paths, bytes, base64 text or data URIs."""
        if images is not None:
            images = list(images) if isinstance(images, (list, tuple)) else [images]
        try:
            if images:
                self._images = self._embed_images(images)
                state = self._state_with_images(state, len(images))
            settled, pending, used = self._sort(state, questions)
            if pending:
                probs, n = self.probabilities([q for _, q in pending])
                used += n
                settled = self._finish(settled, pending, probs, questions)
        finally:
            self._images = None
        return settled, {"input_tokens": used, "output_tokens": 0}

    def decide_batch(self, requests):
        """[(state, questions) or (state, questions, images), ...] -> [answers, ...]: the questions of all text
        requests in one length-sorted set of eager passes (requests with images run one at a time)."""
        plans = []
        for request in requests:
            state, questions = request[0], request[1]
            images = request[2] if len(request) > 2 else None
            if images:
                plans.append(("done", self.decide(state, questions, images)[0]))
            else:
                plans.append(("model", (*self._sort(state, questions)[:2], questions)))
        every = [q for kind, plan in plans if kind == "model" for _, q in plan[1]]
        recorded, self.graphs = self.graphs, {}
        try:
            probs = self.probabilities(every)[0] if every else []
        finally:
            self.graphs = recorded
        answers, at = [], 0
        for kind, plan in plans:
            if kind == "done":
                answers.append(plan)
                continue
            settled, pending, questions = plan
            answers.append(self._finish(settled, pending, probs[at:at + len(pending)], questions))
            at += len(pending)
        return answers
