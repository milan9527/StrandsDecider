# Copyright 2026 Torchcast AI. Licensed under the Apache License, Version 2.0 (see LICENSE in this folder).
"""From a /v1/systemone question to the prompt tokens the model reads (prompt format "jev_render_v3").

A question becomes a Question: its type, the state as text, the instruction and the options in request order.

    state     a string is used as is; null, {} and [] are empty; any other JSON value is written compactly
              (ensure_ascii off), and in it every list of 8 or more items gives each item its position as "_index"
    choice    criteria {id: description} or [id, ...]
    score     criteria [level, ...] or {key: level}: option ids "0".."n-1", lowest level first (dict keys in numeric
              order when they all parse as numbers, else as given)
    noul      criteria {"true": ..., "false": ...} (optional); options "true" and "false"; type "bool" is an alias
"options" and "question" are accepted for "criteria" and "instructions".

The prompt is the tokenizer's own chat template (thinking off) over two messages:

    system    SYSTEM
    user      Evidence:\\n{state or "(none)"}\\n\\nQuestion: {instructions}\\nOptions:\\nA) ...\\nB) ...

An option line is "id: description", or the id alone when the description is missing or only repeats the id; yes/no
options read "yes" / "no".  When every choice id is a bare label (a letter, a number, "option 3") and every option has
a description, the line is the description alone, so that a line such as "A) C: Paris" cannot make the letter
ambiguous.  The answer letter is read at the last prompt token.

A prompt over the budget (16,384 tokens) keeps the head and the tail of its state around a "\\n...\\n" line; the
instruction and the options are always kept.  The model was trained with the same budget and cut."""
from __future__ import annotations

import json
import re
import string
from dataclasses import dataclass, replace

VERSION = "jev_render_v3"
SYSTEM = "Apply the criterion to the evidence. Choose exactly one listed option. Answer with its letter only."
LETTERS = string.ascii_uppercase
KINDS = ("choice", "score", "noul")
MAX_OPTIONS = len(LETTERS)
MAX_LEVELS = 10
POSITIONS_FROM = 8                   # lists at least this long carry "_index"
BUDGET = 16384
ELLIPSIS = "\n...\n"
NO_STATE = "(none)"
DEFAULT_NOUL_QUESTION = "Which answer fits the evidence?"
THINKING_OFF = "<think>\n\n</think>\n\n"     # how the chat template must end with thinking off
_LABEL_ONLY = re.compile(r"\(?[a-z][).]?|\(?\d{1,3}[).]?|opt(?:ion)?[_ ]?\d{1,3}", re.IGNORECASE)


@dataclass(frozen=True)
class Question:
    kind: str
    state: str
    instructions: str
    options: tuple                   # ((id, description or None), ...) in request order

    @property
    def ids(self):
        return [oid for oid, _ in self.options]


# ---------------------------------------------------------------- request -> Question

def _positions(value):
    if isinstance(value, dict):
        return {k: _positions(v) for k, v in value.items()}
    if isinstance(value, list):
        if len(value) < POSITIONS_FROM:
            return [_positions(v) for v in value]
        return [{"_index": n, **_positions(v)} if isinstance(v, dict) else {"_index": n, "value": _positions(v)}
                for n, v in enumerate(value)]
    return value


def state_as_text(state):
    if isinstance(state, str):
        return state
    return "" if state in (None, {}, []) else json.dumps(_positions(state), ensure_ascii=False)


def _text_or_none(value):
    if value is None:
        return None
    text = (value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)).strip()
    return text or None


def level_keys(scale):
    """Keys of a dict-form score scale, lowest level first."""
    try:
        return sorted(scale, key=float)
    except (TypeError, ValueError):
        return list(scale)


def question(state, spec, state_text=None):
    """One question spec of a request -> a checked Question.  state_text overrides the rendering of the state."""
    kind = spec.get("type", "choice")
    kind = "noul" if kind == "bool" else kind
    crit = spec["criteria"] if "criteria" in spec else spec.get("options")
    instructions = _text_or_none(spec["instructions"] if "instructions" in spec else spec.get("question")) or ""
    if kind == "choice":
        pairs = ([(str(c), None) for c in dict.fromkeys(str(c) for c in crit)] if isinstance(crit, (list, tuple))
                 else [(str(k), _text_or_none(v)) for k, v in crit.items()])
    elif kind == "score":
        levels = [crit[k] for k in level_keys(crit)] if isinstance(crit, dict) else list(crit)
        pairs = [(str(n), _text_or_none(v)) for n, v in enumerate(levels)]
    elif kind == "noul":
        crit = crit if isinstance(crit, dict) else {}
        yes = crit["true"] if "true" in crit else crit.get(True)
        no = crit["false"] if "false" in crit else crit.get(False)
        pairs = [("true", _text_or_none(yes)), ("false", _text_or_none(no))]
        instructions = instructions or DEFAULT_NOUL_QUESTION
    else:
        raise ValueError(f"unknown question type {kind!r}")
    q = Question(kind, state_as_text(state) if state_text is None else state_text, instructions, tuple(pairs))
    _check(q)
    return q


def _check(q):
    if not q.instructions.strip():
        raise ValueError("the question has no instructions")
    n = len(q.options)
    if not 2 <= n <= MAX_OPTIONS:
        raise ValueError(f"a question takes 2 to {MAX_OPTIONS} options, not {n}")
    for oid, desc in q.options:
        if not oid.strip() or "\n" in oid or "\r" in oid or len(oid) > 200:
            raise ValueError(f"option id {oid!r} must be one line of 1 to 200 characters")
        if desc is not None and not isinstance(desc, str):
            raise ValueError("an option description must be text")
    if len(set(q.ids)) < n:
        raise ValueError("option ids repeat")
    if q.kind == "score" and n > MAX_LEVELS:
        raise ValueError(f"a score question takes 2 to {MAX_LEVELS} levels, not {n}")


# ---------------------------------------------------------------- Question -> prompt

def _squash(text):
    return re.sub(r"[\s_\-]+", " ", str(text)).strip().lower()


def option_lines(q):
    descs = dict(q.options)
    labels_only = q.kind == "choice" and all(_LABEL_ONLY.fullmatch(i) for i in q.ids) and all(descs[i] for i in q.ids)
    lines = []
    for letter, (oid, desc) in zip(LETTERS, q.options):
        shown = ("yes" if oid == "true" else "no") if q.kind == "noul" else oid
        if labels_only:
            body = desc
        elif desc is None or not desc.strip() or _squash(desc) == _squash(shown):
            body = shown
        else:
            body = f"{shown}: {desc}"
        lines.append(f"{letter}) {body}")
    return lines


def user_text(q):
    state = q.state if q.state.strip() else NO_STATE
    return f"Evidence:\n{state}\n\nQuestion: {q.instructions.strip()}\nOptions:\n" + "\n".join(option_lines(q))


def chat(q):
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_text(q)}]


def chat_text(tok, messages):
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    if not text.endswith(THINKING_OFF):
        raise ValueError("the tokenizer's chat template does not end with the thinking-off prefix")
    return text


def _tokens(tok, q):
    return tok.encode(chat_text(tok, chat(q)), add_special_tokens=False)


def prompt_ids(q, tok, budget=BUDGET):
    """Prompt tokens of q; over min(budget, BUDGET) tokens, the state keeps its head and tail around ELLIPSIS."""
    limit = min(int(budget), BUDGET)
    ids = _tokens(tok, q)
    if len(ids) <= limit:
        return ids
    state = tok.encode(q.state, add_special_tokens=False)
    keep = len(state) - (len(ids) - limit) - 16       # room for the marker and for re-tokenisation at the joins
    while keep > 0:
        head = keep // 2
        cut = tok.decode(state[:head]) + ELLIPSIS + tok.decode(state[len(state) - (keep - head):])
        ids = _tokens(tok, replace(q, state=cut))
        if len(ids) <= limit:
            return ids
        keep -= max(16, len(ids) - limit + 16)
    raise ValueError(f"the prompt does not fit in {limit} tokens even without its state")


def letter_ids(tok):
    """Token ids of "A".."Z" as read after the prompt; checks that each is one token that stays separate."""
    probe_text = chat_text(tok, chat(question("s", {"type": "noul", "instructions": "q"})))
    probe = tok.encode(probe_text, add_special_tokens=False)
    ids = []
    for letter in LETTERS:
        one = tok.encode(letter, add_special_tokens=False)
        if len(one) != 1 or tok.encode(probe_text + letter, add_special_tokens=False) != probe + one:
            raise ValueError(f"{letter!r} is not one separate token after the prompt")
        ids.append(one[0])
    if len(set(ids)) != len(ids):
        raise ValueError("letter token ids are not distinct")
    return ids
