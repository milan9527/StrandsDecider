#!/usr/bin/env python3
"""H2O-Lightning-4B shim: typed decisions over a stock vLLM server, one output token per decision. Stdlib only
(selector_v2.py, shipped beside it, is too).

WHAT IT DOES
    POST /v1/systemone  (the decision wire format; /api/alpha/decisions is an alias)
    POST /v1/decisions  (OpenAI's Decisions API, e.g. client.decisions.create; mapped onto the same decision)
      -> renders each question in the prompt the model was trained on (serve_config.json: the chat template with
         thinking off, the system prompt, the "plain" layout, compact JSON for a structured state, one label per
         option, the "Answer:" prefill)
      -> sends ONE vLLM completion per question with max_tokens=1 and `logprob_token_ids` set to that question's
         label tokens, so every option is read at the answer slot and none can fall out of a top-k
      -> applies the temperature (one for every question type, or one per type: serve_config.json "temperature":
         {"choice": T, "noul": T, "score": T}), then the yes/no commit floor
      -> returns {"model", "answers", "probability_source", "effort_used", "usage"}

    Several questions about one state are sent concurrently; vLLM's prefix cache shares the state between them, and
    usage.input_tokens counts that shared head once plus each question's own tail.
    It generates no text and calls nothing but the local vLLM server.

    python3 h2o_lightning_shim.py --config serve_config.json --vllm http://127.0.0.1:8000 --port 8741

IMAGES (only when serve_config.json has an "image" block, and only for a request that carries an image)
    Accepted forms: a `data:image/...;base64,` URI or bare base64 image bytes anywhere inside `state` (a string, an
    object value, a list item); a chat-style image part inside `state` ({"type": "image_url", "image_url": {"url"}},
    {"type": "image", "image": ...}, {"type": "input_image", "image_url": ...}, {"type": "base64", "media_type",
    "data"}); the top-level fields `images`, `image`, `image_url`, `image_urls`, `image_data`, `image_base64` (data
    URIs, bare base64, http(s) URLs, or the part objects above); and multipart/form-data with the JSON in a
    `request` field and the images as file parts. A URL is an image only in those explicit places, never as a plain
    string inside `state`. Each image lifted out of `state` leaves `[image N]` in the record (the top-level images are
    numbered first). The question is then read through vLLM's chat completions with the images ahead of the same
    user text, the assistant turn pre-filled with the same "Answer:" (continue_final_message) and the same
    `logprob_token_ids` readout, so the prompt is the text prompt plus the image tokens. A request without an image
    takes the text path above, unchanged.

TWO-WAY READING (the recommended default; serve.sh TWO_WAY=1)
    The weights were trained to answer under two attention patterns: one-way (causal, the readout above) and two-way
    (bidirectional attention on the full-attention layers; the Gated DeltaNet layers stay causal). serve.sh serves
    two-way on ONE generate-mode engine of the vLLM build with per-request attention (github.com/h2oai/vllm, commit
    b05cc29ab813895947954c268c4ec41ca0da1306; SHIM_TWO_WAY_FLAG=1): a two-way read carries vllm_xargs
    attention_mode=bidirectional and comes back through the same `logprob_token_ids` readout; the same engine answers
    one-way requests and Box questions. TWO_WAY=0 serves one-way only, on stock vLLM (the shim started with --vllm).
    A request chooses with `"attention_mode": "bidirectional"` or `"causal"` (also "two-way" / "one-way"); without it
    the deployment's default applies (two-way on the one engine; serve_config.json two_way.default /
    SHIM_ATTENTION_MODE). A request for a mode that is not running is a 400, never a silent answer in the other mode;
    every response states the mode it was read in. The two-way temperatures and yes/no floor are the block's own
    (two_way.temperature, two_way.noul_floor, two_way.image_temperature; the SHIM_* overrides apply to both modes); a
    missing one falls back to the one-way value with a WARNING line. Before the first two-way answer the shim reads
    three fixed probes flagged and unflagged: the flagged answers must be within two_way.probe_tolerance of the
    answers recorded on the release weights (two_way.probe_reference) and differ from the unflagged ones (an engine
    without the build ignores the flag); any failure is a 503, kept 10 s (SHIM_TWO_WAY_RETRY_SECONDS) before the
    engine is checked again. The earlier two-engine layout (a pooling-runner engine, --vllm-two-way, reading the final
    hidden state with label_rows.lightning and pooled_readout.py) is still accepted by the shim for a manual start but
    is no longer supported by serve.sh or the model card.

LONG RECORDS (selector v2, the default). A question whose prompt fits vLLM's context (--max-model-len) is read whole,
exactly as before. One that does not has its record cut to the room its own prompt leaves (the context less the
question, the options, the template, the images' tokens and SHIM_CONTEXT_SLACK, 16) by BM25 selection (selector_v2.py,
the 31B's: the parts most relevant to the question and its options, with their headings); where no part matches, its
head and tail around a "\n...\n" line. Each question of a request is fitted on its own. A question too long for the
context even without its record is answered without it, its instructions, then its option descriptions, then its
option names (in the prompt only) cut to fit. effort_used.state_selection says what was done; usage.input_tokens
stays the full input. An over-context request never fails. SHIM_MAX_STATE_TOKENS caps the record lower than the
context allows; SHIM_SELECTOR=headtail (prompt.selector) restores v1.4.1's cut (the record over prompt.max_state_tokens,
32,000, to its head and tail), for comparison only.

STATUS CODES (an evaluation runner stops after three consecutive failures unless a failure is a 422): a request this
system cannot answer -- too many options, a malformed question -- is a 422, scored as one wrong answer; an empty request is a 400; an unreachable or failing vLLM is a 502, and a vLLM that does not serve
the configured model is a 503, so a broken backend stops a run; vLLM's own 401/403/429 pass through.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import email.parser
import email.policy
import http.client
import ipaddress
import json
import logging
import math
import os
import re
import select
import socket
import ssl
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SHIM_VERSION = "h2o-lightning-shim"
PRIMITIVES = ("choice", "noul", "score")
EFFORT_TIERS = ("fast", "balanced", "thorough")
# vLLM 0.30 accepts at most 128 `logprob_token_ids` per request; a question with more options is read in chunks
LOGPROB_CHUNK = int(os.environ.get("SHIM_LOGPROB_CHUNK", "128"))
TIMEOUT = float(os.environ.get("SHIM_TIMEOUT", "180"))
# PREFIX-CACHE WRITES (one-way reads; the vLLM build's vllm_xargs prefix_cache_write, ignored by stock vLLM): which
# reads may write their prompt to vLLM's prefix cache. With prefix caching on, vLLM 0.30 splits a writing prefill of
# this hybrid model at the last 528-token state block (so the state there can be cached) and runs the rest as a second
# step; a read that writes nothing runs in one step and still reads what others cached. "all" (default): every read
# writes (stock behaviour); "first": the first question of a multi-question request writes (the others read the
# shared record from it) and a single question writes nothing: one request at a time is faster (one H100, 1,000-token
# one-way read: 38.5 -> 28.9 ms), but one-step prefills batch worse under load (91.5 -> 62.4 requests/s at 8 in
# flight); "none": no read writes.
CACHE_WRITE = os.environ.get("SHIM_CACHE_WRITE", "all").strip().lower()
if CACHE_WRITE not in ("first", "all", "none"):
    raise SystemExit("SHIM_CACHE_WRITE must be first, all or none")
# vLLM's wording when a prompt does not fit --max-model-len (it has changed between releases)
_CONTEXT_ERROR = re.compile(r"maximum context length|maximum model length|max_model_len|too long and exceeds|"
                            r"longer than the maximum", re.I)
# Qwen3.5's chat template for a system and a user message with the generation prompt and thinking off; the template
# trims both contents (Jinja's `trim` is Python's str.strip)
CHATML = {"system": "<|im_start|>system\n{content}<|im_end|>\n",
          "user": "<|im_start|>user\n{content}<|im_end|>\n",
          "generation": "<|im_start|>assistant\n<think>\n\n</think>\n\n"}
# what the template writes for one image part, before vLLM expands the pad into the image's tokens
VISION_SLOT = "<|vision_start|><|image_pad|><|vision_end|>"
# OVER-CONTEXT (BM25 down to fit, the question and options whole, never a 422, never under the model's own
# limit): SELECTORS v2 = selector_v2's BM25 over the record when a question's prompt would not fit vLLM's context (the
# default); headtail = v1.4.1's training cut at prompt.max_state_tokens, for comparison only
SELECTORS = ("v2", "headtail")
CONTEXT_SLACK = int(os.environ.get("SHIM_CONTEXT_SLACK", "16"))   # context tokens kept free: the answer token, seams
MIN_STATE_BUDGET = 64              # under this many tokens of room the record is left out of the prompt
PIXELS_PER_IMAGE_TOKEN = 32 * 32   # Qwen3.5's vision tower: 16-px patches merged 2x2 into one token
MAX_IMAGE_BYTES = int(os.environ.get("SHIM_MAX_IMAGE_BYTES", str(20 * 1024 * 1024)))
# A kept-alive connection to vLLM is reused only while the server still holds it open: vLLM (uvicorn) closes idle
# connections after 5 s, and a reused socket the server has closed can stall a large send (an image body) until the
# whole request timeout. Idle longer than LIGHTNING_BACKEND_IDLE_SECONDS, or closed by the server: a fresh connection.
IDLE_SECONDS = float(os.environ.get("LIGHTNING_BACKEND_IDLE_SECONDS", "3"))
# Sending a request (a few MB of images at most) never needs long; waiting for the answer may (a long read queued
# behind others), so only the send is bounded. A stalled send fails and is retried once on a fresh connection.
SEND_SECONDS = float(os.environ.get("LIGHTNING_BACKEND_SEND_SECONDS", "30"))


def _peer_closed(sock):
    """True when the server has closed (or written unexpectedly to) an idle kept-alive socket."""
    try:
        readable, _, _ = select.select([sock], [], [], 0)
    except (OSError, ValueError):
        return True
    return bool(readable)


class Unprocessable(ValueError):
    """A request in the contract's shape that this system cannot answer: a 422, one wrong item, the run goes on."""


class BadRequest(ValueError):
    """Not the contract's shape at all (no questions, an unknown effort tier): a 400."""


class UpstreamError(RuntimeError):
    """vLLM failed or could not be reached: a 502 (or 503, or vLLM's own 401/403/429), so a run stops."""

    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------------------------------------- the prompt
def render_state(state, compact):
    """The record: a string verbatim, anything else as JSON (compact when the config says so)."""
    if isinstance(state, str):
        return state
    if compact:
        return json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(state, indent=1)


def desc_text(v):
    """An option description or score level: a string verbatim, anything else as JSON."""
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def render_instr(value):
    """`instructions` may be a string, an object or an array."""
    return value if isinstance(value, str) else json.dumps(value, indent=1)


def options_of(question, max_options=255):
    """(option names, descriptions) for the three question types. A yes/no question is always [true, false]."""
    typ = question.get("type", "choice")
    criteria = question.get("criteria")
    if typ not in PRIMITIVES:
        raise Unprocessable(f"question type {typ!r} is not one of {list(PRIMITIVES)}")
    if typ == "noul":
        criteria = criteria or {}
        if not isinstance(criteria, dict):
            raise Unprocessable("noul criteria must be an object with true/false descriptions")
        true_desc = criteria.get("true", criteria.get("yes"))
        false_desc = criteria.get("false", criteria.get("no"))
        return ["true", "false"], [
            desc_text(true_desc) if true_desc not in (None, "") else "the statement holds",
            desc_text(false_desc) if false_desc not in (None, "") else "it does not",
        ]
    if typ == "score":
        if not isinstance(criteria, list) or len(criteria) < 1:
            raise Unprocessable("score criteria must be an ordered array of levels")
        return [str(i) for i in range(len(criteria))], [desc_text(value) for value in criteria]
    if not isinstance(criteria, dict) or len(criteria) < 1:
        raise Unprocessable("choice criteria must map option -> description")
    if len(criteria) > max_options:
        raise Unprocessable(f"choice supports at most {max_options} options")
    names = list(criteria)
    return names, [desc_text(criteria[name]) if criteria[name] is not None else name for name in names]


def option_lines(labels, names, descs):
    """One line per option: `A) name: description`."""
    if len(labels) < len(names):
        raise Unprocessable(f"{len(names)} options but only {len(labels)} labels")
    return [f"{l}) {n}: {d}" for l, n, d in zip(labels, names, descs)]


def user_turn(state_text, instructions, names, descs, labels, layout="plain"):
    """The user message."""
    body = "\n".join(option_lines(labels, names, descs))
    if layout == "plain":
        return f"record: {state_text}\nquestion: {instructions}\noptions:\n{body}"
    if layout == "markdown":
        return f"### RECORD\n{state_text}\n\n### QUESTION\n{instructions}\n\n### OPTIONS\n{body}\n"
    raise ValueError(f"layout {layout!r} is not supported")


def render_chat(system, user, prefill, chat=True):
    """The full prompt: the chat template for [system, user] with thinking off, then the answer prefill. Without the
    template, the same parts joined by blank lines."""
    if not chat:
        return "\n\n".join(([] if system is None else [system]) + [user]) + f"\n{prefill}"
    out = "" if system is None else CHATML["system"].replace("{content}", system.strip())
    return out + CHATML["user"].replace("{content}", user.strip()) + CHATML["generation"] + prefill


def chat_messages(system, user, prefill, image_urls):
    """The same prompt as render_chat, as chat messages for vLLM: the images ahead of the user text, and the assistant
    turn pre-filled with the prefill (sent with continue_final_message). Qwen3.5's template renders a final assistant
    turn after the last user turn as `<think>\\n\\n</think>\\n\\n` + its content, which is render_chat's generation
    prompt + prefill, so with no image the two token streams are the same (checked against vLLM at first use)."""
    msgs = [] if system is None else [{"role": "system", "content": system.strip()}]
    parts = [{"type": "image_url", "image_url": {"url": u}} for u in image_urls]
    msgs.append({"role": "user", "content": parts + [{"type": "text", "text": user.strip()}]})
    msgs.append({"role": "assistant", "content": prefill})
    return msgs


# ------------------------------------------------------------------------------------------------- images
IMAGE_KEYS = ("images", "image", "image_url", "image_urls", "image_data", "image_base64")
_DATA_URI = re.compile(r"data:(image/[A-Za-z0-9.+-]+);base64,(.*)", re.S | re.I)
_B64_CHARS = re.compile(r"[A-Za-z0-9+/=\s]+")
_B64_URLSAFE = re.compile(r"[A-Za-z0-9_\-=\s]+")
_SPACE = re.compile(r"\s")
_PART_TYPES = ("image_url", "image", "input_image")
# how base64 of a PNG, JPEG, GIF and WebP begins: the cheap test before anything inside `state` is decoded
_B64_HEADS = ("iVBORw0KGgo", "/9j/", "R0lGOD", "UklGR")


def sniff_image(raw):
    """The image type from its first bytes, or None."""
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw.startswith(b"BM"):
        return "image/bmp"
    if raw[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    return None


def _b64_bytes(s):
    """Decoded bytes of a (standard or URL-safe) base64 string, or None. The standard decoder checks the alphabet itself
    (validate=True), and whitespace is stripped only when there is some, so a large image is not scanned in Python."""
    t = re.sub(r"\s+", "", s) if _SPACE.search(s) else s
    if not t:
        return None
    try:
        return base64.b64decode(t + "=" * (-len(t) % 4), validate=True)
    except (binascii.Error, ValueError):
        pass
    try:
        if _B64_URLSAFE.fullmatch(t):
            return base64.urlsafe_b64decode(t + "=" * (-len(t) % 4))
    except (binascii.Error, ValueError):
        return None
    return None


def _data_uri(mime, raw):
    if len(raw) > MAX_IMAGE_BYTES:
        raise Unprocessable(f"an image of {len(raw)} bytes is over the {MAX_IMAGE_BYTES}-byte limit")
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


# IMAGE URLS ARE FETCHED HERE, SAFELY, AND NEVER BY vLLM. An http(s) image URL in a request is downloaded by this shim
# and handed to vLLM as a data URI, so vLLM never makes a request on a caller's behalf (start it with
# --allowed-media-domains set to a name that never resolves, or with no egress, as a backstop). The rules:
#   - https only (LIGHTNING_IMAGE_URL_ALLOW_HTTP=true also allows http); no user:password in the URL; port 443 (80 for
#     http) unless the host is on LIGHTNING_IMAGE_URL_HOSTS
#   - every address the host resolves to must be public: loopback, private, link-local (169.254.0.0/16, the cloud
#     metadata address), CGNAT 100.64.0.0/10, multicast, reserved, IPv6 ULA / link-local / site-local and IPv4-mapped,
#     -compatible, -translated or embedded private addresses are refused; the connection goes to the checked address
#     (no DNS rebinding) and TLS still verifies the certificate for the host name
#   - at most 3 redirects, each one checked the same way; the final answer must be HTTP 200
#   - LIGHTNING_IMAGE_FETCH_SECONDS (5) is a hard deadline for the whole fetch (name lookup, connect, TLS, headers,
#     body and redirects): a watchdog closes the connection when it passes, however slowly the server sends
#   - LIGHTNING_IMAGE_FETCH_MAX_BYTES (20 MiB) per image, read with a cap; LIGHTNING_IMAGE_FETCH_MAX_TOTAL_BYTES
#     (4 x that) per request
#   - the links of a request are counted before any is fetched: more images than the deployment reads is refused
#     without fetching; at most LIGHTNING_IMAGE_FETCH_CONCURRENCY (8) fetches run at once in this process
#   - the response must say image/* and its bytes must be a PNG, JPEG, GIF, WebP, BMP or TIFF
#   - optional LIGHTNING_IMAGE_URL_HOSTS (allowlist) and LIGHTNING_IMAGE_URL_DENY_HOSTS (host names, compared in
#     their IDNA form); LIGHTNING_IMAGE_URLS=off refuses every image URL (locked-down deployments)
# The bytes live in memory only, for this request: no file, no cache, no log line with the URL or the image. Errors
# returned to the caller are generic (no address or fetch detail).
IMAGE_FETCH_SECONDS = float(os.environ.get("LIGHTNING_IMAGE_FETCH_SECONDS", "5"))
IMAGE_FETCH_MAX_BYTES = int(os.environ.get("LIGHTNING_IMAGE_FETCH_MAX_BYTES", str(20 * 1024 * 1024)))
IMAGE_FETCH_MAX_TOTAL_BYTES = int(os.environ.get("LIGHTNING_IMAGE_FETCH_MAX_TOTAL_BYTES", str(4 * IMAGE_FETCH_MAX_BYTES)))
IMAGE_FETCH_REDIRECTS = 3
_FETCH_SLOTS = threading.BoundedSemaphore(int(os.environ.get("LIGHTNING_IMAGE_FETCH_CONCURRENCY", "8")))
_FETCH_LOG = logging.getLogger("lightning.image_fetch")
_BLOCKED_V4 = [ipaddress.ip_network(n) for n in ("0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
               "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.88.99.0/24", "192.168.0.0/16",
               "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4")]
_BLOCKED_V6 = [ipaddress.ip_network(n) for n in ("::/96", "::ffff:0:0/96", "::ffff:0:0:0/96", "fc00::/7", "fe80::/10",
               "fec0::/10", "ff00::/8", "64:ff9b::/96", "64:ff9b:1::/48", "100::/64", "2001:db8::/32", "2001::/23",
               "fd00:ec2::/32")]
# the path and query as sent: non-ASCII is percent-encoded (as a browser does); existing %XX escapes are kept
_URL_SAFE = "/%?=&;:@!$'()*+,~-._[]"


class ImageFetchRefused(Exception):
    """Internal reason a URL was not fetched; the caller only ever sees a generic 422."""


def _public_address(text):
    ip = ipaddress.ip_address(text.split("%", 1)[0])
    if ip.version == 6:
        if ip.ipv4_mapped is not None:
            return _public_address(str(ip.ipv4_mapped))
        if ip.sixtofour is not None and not _public_address(str(ip.sixtofour)):
            return False
        if ip.teredo is not None:
            return False
        return ip.is_global and not any(ip in n for n in _BLOCKED_V6)
    return ip.is_global and not any(ip in n for n in _BLOCKED_V4)


def _idna(host):
    """A host name in the form DNS sees (IDNA, so full-width or Unicode spellings compare equal); ImageFetchRefused
    when it has none."""
    try:
        return host.strip().lower().rstrip(".").encode("idna").decode("ascii")
    except UnicodeError:
        raise ImageFetchRefused("host") from None


def _host_list(name):
    out = set()
    for h in os.environ.get(name, "").split(","):
        if h.strip():
            try:
                out.add(_idna(h))
            except ImageFetchRefused:
                out.add(h.strip().lower().rstrip("."))
    return out


def _resolve(host, port, deadline):
    """getaddrinfo within the deadline (it runs in a helper thread; an abandoned lookup ends on its own)."""
    box = {}

    def lookup():
        try:
            box["infos"] = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except (OSError, UnicodeError):
            box["error"] = True

    worker = threading.Thread(target=lookup, name="image-fetch-resolve", daemon=True)
    worker.start()
    worker.join(max(0.0, deadline - time.monotonic()))
    if "infos" not in box:
        raise ImageFetchRefused("resolve" if "error" in box else "time")
    return box["infos"]


def _checked_target(url, deadline):
    """(scheme, host, port, path, pinned_ip) for a URL that may be fetched, or ImageFetchRefused."""
    try:
        u = urllib.parse.urlsplit(url)
        port = u.port
    except ValueError:
        raise ImageFetchRefused("url") from None
    scheme = u.scheme.lower()
    allow_http = os.environ.get("LIGHTNING_IMAGE_URL_ALLOW_HTTP", "false").lower() == "true"
    if scheme != "https" and not (scheme == "http" and allow_http):
        raise ImageFetchRefused("scheme")
    if u.username is not None or u.password is not None or not u.hostname:
        raise ImageFetchRefused("authority")
    host = _idna(u.hostname)
    port = port or (443 if scheme == "https" else 80)
    allow, deny = _host_list("LIGHTNING_IMAGE_URL_HOSTS"), _host_list("LIGHTNING_IMAGE_URL_DENY_HOSTS")
    if host in deny or (allow and host not in allow):
        raise ImageFetchRefused("host list")
    if port != (443 if scheme == "https" else 80) and host not in allow:
        raise ImageFetchRefused("port")
    addresses = sorted({info[4][0] for info in _resolve(host, port, deadline)})
    if not addresses or not all(_public_address(a) for a in addresses):  # one private answer refuses the host
        raise ImageFetchRefused("address")
    path = urllib.parse.quote(u.path or "/", safe=_URL_SAFE)
    if u.query:
        path += "?" + urllib.parse.quote(u.query, safe=_URL_SAFE)
    return scheme, host, port, path, addresses[0]


class _PinnedHTTPS(http.client.HTTPSConnection):
    """HTTPS to an already-checked address, verifying the certificate for the original host name."""

    def __init__(self, host, port, ip, timeout, expired):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._ip, self.expired, self.raw = ip, expired, None

    def connect(self):
        self.raw = socket.create_connection((self._ip, self.port), self.timeout)
        if self.expired.is_set():  # the watchdog fired while connecting
            raise OSError("deadline")
        self.sock = self._context.wrap_socket(self.raw, server_hostname=self.host)


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host, port, ip, timeout, expired):
        super().__init__(host, port, timeout=timeout)
        self._ip, self.expired, self.raw = ip, expired, None

    def connect(self):
        self.raw = self.sock = socket.create_connection((self._ip, self.port), self.timeout)
        if self.expired.is_set():
            raise OSError("deadline")


def _cut(conn, expired):
    """The watchdog: at the deadline, shut the connection's socket so any blocked read, handshake or connect ends."""
    expired.set()
    for sock in (conn.raw, conn.sock):
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _fetch_bytes(url, max_bytes=None):
    """The image bytes behind `url`, under every rule above; ImageFetchRefused otherwise."""
    cap = IMAGE_FETCH_MAX_BYTES if max_bytes is None else min(max_bytes, IMAGE_FETCH_MAX_BYTES)
    deadline = time.monotonic() + IMAGE_FETCH_SECONDS
    if not _FETCH_SLOTS.acquire(timeout=IMAGE_FETCH_SECONDS):
        raise ImageFetchRefused("busy")
    try:
        for _ in range(IMAGE_FETCH_REDIRECTS + 1):
            scheme, host, port, path, ip = _checked_target(url, deadline)
            left = deadline - time.monotonic()
            if left <= 0:
                raise ImageFetchRefused("time")
            expired = threading.Event()
            conn = (_PinnedHTTPS if scheme == "https" else _PinnedHTTP)(host, port, ip, left, expired)
            watchdog = threading.Timer(left, _cut, (conn, expired))
            watchdog.daemon = True
            watchdog.start()
            try:
                authority = f"[{host}]" if ":" in host else host
                conn.request("GET", path, headers={"Host": authority if port in (80, 443) else f"{authority}:{port}",
                                                   "User-Agent": "h2o-lightning-image-fetch/1", "Accept": "image/*"})
                r = conn.getresponse()
                if r.status in (301, 302, 303, 307, 308):
                    location = r.getheader("Location")
                    if not location:
                        raise ImageFetchRefused("redirect")
                    url = urllib.parse.urljoin(url, location)
                    continue
                if r.status != 200:
                    raise ImageFetchRefused("status")
                if not (r.getheader("Content-Type") or "").lower().startswith("image/"):
                    raise ImageFetchRefused("content type")
                declared = r.getheader("Content-Length")
                if declared and declared.isdigit() and int(declared) > cap:
                    raise ImageFetchRefused("size")
                chunks, total = [], 0
                while True:
                    block = r.read(min(65536, cap + 1 - total))
                    if not block:
                        break
                    total += len(block)
                    if total > cap:
                        raise ImageFetchRefused("size")
                    chunks.append(block)
                if expired.is_set():
                    raise ImageFetchRefused("time")
                return b"".join(chunks)
            except (OSError, ValueError, http.client.HTTPException, ssl.SSLError):
                raise ImageFetchRefused("time" if expired.is_set() else "transport") from None
            finally:
                watchdog.cancel()
                conn.close()
        raise ImageFetchRefused("redirects")
    finally:
        _FETCH_SLOTS.release()


def fetch_image_url(url, max_bytes=None):
    """An http(s) image URL as a data URI, fetched here under the rules above (in memory only)."""
    if os.environ.get("LIGHTNING_IMAGE_URLS", "fetch").lower() == "off":
        raise Unprocessable("image URLs are not accepted here: send the image as a data:image/...;base64 URI")
    t0 = time.monotonic()
    try:
        raw = _fetch_bytes(url, max_bytes)
    except ImageFetchRefused as why:
        _FETCH_LOG.info("image URL refused (%s)", why)  # the reason class only: never the URL
        raise Unprocessable("an image URL could not be fetched (only public https images are accepted)") from None
    mime = sniff_image(raw)
    if mime is None:
        _FETCH_LOG.info("image URL refused (not an image)")
        raise Unprocessable("an image URL did not return an image")
    _FETCH_LOG.info("image fetched: %d bytes in %d ms", len(raw), int((time.monotonic() - t0) * 1000))
    return _data_uri(mime, raw)


class _Link(str):
    """An image link found while a request's images are collected: fetched only after they are counted."""


_COLLECTING = threading.local()


def _image_link(url):
    """An explicit image link: fetched now, or, while extract_images counts a request's images, noted for later."""
    if getattr(_COLLECTING, "on", False):
        return _Link(url)
    return fetch_image_url(url)


def image_from_string(s, explicit):
    """A string as an image URL for vLLM, or None when it is not an image.

    A `data:image/...;base64,` URI is always an image (a malformed one is a 422). Bare base64 counts only when it
    decodes to known image bytes; inside `state` it must also be one unbroken token of at least 64 characters that
    decodes to a PNG, JPEG, GIF or WebP, so ordinary text never qualifies. An http(s) URL counts only when `explicit`
    (a top-level image field or an image part): a record may hold ordinary links."""
    s = s.strip()
    m = _DATA_URI.match(s)
    if m:
        raw = _b64_bytes(m.group(2))
        if not raw:
            raise Unprocessable("an image data URI does not carry valid base64")
        return _data_uri(sniff_image(raw) or m.group(1).lower(), raw)
    if explicit:
        if re.match(r"https?://", s, re.I):
            return _image_link(s)
        raw = _b64_bytes(s) if len(s) >= 16 else None
        mime = sniff_image(raw) if raw else None
        if mime:
            return _data_uri(mime, raw)
        raise Unprocessable("an image field holds neither a data URI, base64 image bytes nor an http(s) URL")
    if len(s) < 64 or not s.startswith(_B64_HEADS) or _SPACE.search(s) or not _B64_CHARS.fullmatch(s):
        return None
    raw = _b64_bytes(s)
    mime = sniff_image(raw) if raw else None
    return _data_uri(mime, raw) if mime in ("image/png", "image/jpeg", "image/gif", "image/webp") else None


def image_from_part(obj, in_state=False):
    """A chat/API-style image object as an image URL, or None when `obj` is not one. Inside `state` (`in_state`) an
    object shaped like a part whose value is not an image (say {"type": "image", "image": "a sunset"}) is record
    data and stays; at the top level it is a 422."""
    if not isinstance(obj, dict):
        return None
    typ = obj.get("type")
    if typ == "base64" and isinstance(obj.get("data"), str):              # {"type": "base64", "media_type", "data"}
        v = f"data:{obj.get('media_type') or 'image/png'};base64,{obj['data']}"
    elif typ in _PART_TYPES:
        v = obj.get(typ) if typ != "input_image" else obj.get("image_url", obj.get("image"))
        if isinstance(v, dict):
            v = v.get("url", v.get("data"))
        if not isinstance(v, str):
            if in_state:
                return None
            raise Unprocessable(f"an image part of type {typ!r} has no url or data")
    else:
        return None
    if in_state and not (_DATA_URI.match(v.strip()) or re.match(r"https?://", v.strip(), re.I)):
        return image_from_string(v, False)
    return image_from_string(v, True)


def explicit_image(v):
    """One entry of a top-level image field: a string or an image object ({"url"}, {"image_url": {"url"}}, a part)."""
    if isinstance(v, str):
        return image_from_string(v, True)
    if isinstance(v, dict):
        got = image_from_part(v)
        if got is not None:
            return got
        for k in ("url", "image_url", "data", "image"):
            inner = v.get(k)
            if isinstance(inner, dict):
                inner = inner.get("url", inner.get("data"))
            if isinstance(inner, str):
                return image_from_string(inner, True)
    raise Unprocessable("an image entry must be a string or an object with a url or base64 data")


def lift_images(state, found):
    """`state` with every image inside it replaced by `[image N]` (N counts on from len(found)); the images are
    appended to `found`. Anything that is not an image is returned as is (the same object when nothing changed)."""
    if isinstance(state, str):
        u = image_from_string(state, False)
        if u is None:
            return state
        found.append(u)
        return f"[image {len(found)}]"
    if isinstance(state, dict):
        u = image_from_part(state, in_state=True)
        if u is not None:
            found.append(u)
            return f"[image {len(found)}]"
        out, changed = {}, False
        for k, v in state.items():
            out[k] = lift_images(v, found)
            changed = changed or out[k] is not v
        return out if changed else state
    if isinstance(state, list):
        out = [lift_images(v, found) for v in state]
        return out if any(a is not b for a, b in zip(out, state)) else state
    return state


def extract_images(body, max_images=None):
    """(state with `[image N]` placeholders, [image URLs]) for a request; (the same state, []) when it has none.
    Image links are counted with every other image first and fetched only when the request is within `max_images`
    (and within IMAGE_FETCH_MAX_TOTAL_BYTES together)."""
    found = []
    _COLLECTING.on = True
    try:
        for k in IMAGE_KEYS:
            v = body.get(k)
            if v is None:
                continue
            for item in (v if isinstance(v, list) else [v]):
                found.append(explicit_image(item))
        state = lift_images(body["state"], found)
    finally:
        _COLLECTING.on = False
    if max_images is not None and len(found) > max_images:
        raise Unprocessable(f"{len(found)} images; this deployment reads at most {max_images} per request")
    budget = IMAGE_FETCH_MAX_TOTAL_BYTES
    for i, item in enumerate(found):
        if isinstance(item, _Link):
            if budget <= 0:
                raise Unprocessable("the image links of this request exceed the total size this deployment reads")
            found[i] = fetch_image_url(str(item), budget)
            budget -= len(found[i]) * 3 // 4  # the data URI is base64: about 4/3 of the bytes
    return state, found


def parse_multipart(content_type, raw):
    """A multipart/form-data body as a request object: the JSON from the `request` (or `body`, `json`, `data`) field,
    every file part as an image in the top-level `images` list, after any images the JSON already has."""
    msg = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
        b"Content-Type: " + content_type.encode("latin-1") + b"\r\n\r\n" + raw)
    if not msg.is_multipart():
        raise Unprocessable("a multipart request without parts")
    body, files = None, []
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        data = part.get_payload(decode=True) or b""
        if part.get_filename() is not None or (part.get_content_maintype() == "image"):
            mime = sniff_image(data) or (part.get_content_type() if part.get_content_maintype() == "image" else None)
            if not mime:
                raise Unprocessable(f"file part {name!r} is not a recognised image")
            files.append(_data_uri(mime, data))
        elif name in ("request", "body", "json", "data"):
            try:
                body = json.loads(data.decode("utf-8"))
            except ValueError as e:
                raise Unprocessable(f"multipart field {name!r} is not JSON: {e}") from e
    if not isinstance(body, dict):
        raise Unprocessable("a multipart request needs its JSON in a `request` field")
    if files:
        have = body.get("images")
        body["images"] = (have if isinstance(have, list) else ([] if have is None else [have])) + files
    return body


# ------------------------------------------------------------------------------------------------- the answer
def confidence(p):
    """Normalized maximum: 1 for a point mass, 0 for a uniform distribution."""
    n = len(p)
    if n < 2:
        return 1.0
    return float((max(p) - 1.0 / n) / (1.0 - 1.0 / n))


def probabilities(logprobs, temperature):
    """softmax(log-probabilities / T) over the options."""
    if not logprobs or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                               for v in logprobs):
        raise UpstreamError("vLLM returned an invalid log-probability vector")
    v = [x / max(float(temperature), 1e-3) for x in logprobs]
    m = max(v)
    e = [math.exp(x - m) for x in v]
    s = sum(e)
    if not math.isfinite(s) or s <= 0:
        raise UpstreamError("vLLM returned log-probabilities that cannot be normalized")
    return [x / s for x in e]


def commit_noul(p_yes, floor):
    """A yes/no probability with max(P, 1-P) under the floor moves to the floor on its own side (a tie goes to yes).
    The answer never changes; 0 turns the floor off."""
    if not floor:
        return p_yes
    if max(p_yes, 1.0 - p_yes) >= floor:
        return p_yes
    return floor if p_yes >= 0.5 else 1.0 - floor


def noul_threshold(q):
    """A yes/no question's optional decision threshold in [0, 1], else None."""
    if q.get("type", "choice") != "noul":
        return None
    t = q.get("threshold", q.get("noul_threshold"))
    return float(t) if isinstance(t, (int, float)) and 0.0 <= float(t) <= 1.0 else None


def format_answer(typ, names, descs, logprobs, temperature, noul_floor, threshold=None):
    """One question's answer in the wire shape."""
    p = probabilities(logprobs, temperature)
    if typ == "noul":
        py = commit_noul(float(p[0]), noul_floor)
        answer = {"type": "noul", "noul": float(py)}
        if threshold is not None:
            answer["threshold"] = float(threshold)
            answer["decision"] = bool(py >= float(threshold))
        return answer
    if typ == "score":
        return {
            "type": "score",
            "score": float(sum(i * x for i, x in enumerate(p))),
            "legend": {str(i): d for i, d in enumerate(descs)},
            "probabilities": {str(i): float(x) for i, x in enumerate(p)},
            "confidence": float(max(p)),      # a score's confidence is its most likely level's probability
        }
    k = max(range(len(p)), key=p.__getitem__)          # the first maximum
    return {
        "type": "choice",
        "choice": names[k],
        "probabilities": {name: float(x) for name, x in zip(names, p)},
        "confidence": confidence(p),
    }


MODES = ("causal", "bidirectional")
MODE_ALIASES = {"causal": "causal", "one-way": "causal", "one_way": "causal", "oneway": "causal",
                "bidirectional": "bidirectional", "two-way": "bidirectional", "two_way": "bidirectional",
                "twoway": "bidirectional"}
# the two engines must answer at least one of the probes' questions this differently (max |p| difference at T = 1):
# an engine started without the is_causal override reads one-way and the two readouts agree to bf16 noise (~0.01)
TWO_WAY_MIN_SEPARATION = float(os.environ.get("SHIM_TWO_WAY_MIN_SEPARATION", "0.05"))
TWO_WAY_RETRY_SECONDS = float(os.environ.get("SHIM_TWO_WAY_RETRY_SECONDS", "10"))   # a failed check is kept this long
# three fixed probes (states and questions of no particular meaning; the readouts of the two modes differ on them)
TWO_WAY_PROBES = [
    {"state": {"ticket": "Checkout returns HTTP 500 for every customer since 09:12.", "plan": "enterprise"},
     "questions": {"outage": {"type": "noul", "instructions": "Is this a full outage?",
                              "criteria": {"true": "yes", "false": "no"}},
                   "team": {"type": "choice", "instructions": "Which team should take it?",
                            "criteria": {"payments": "Payments", "web": "Web frontend", "support": "Customer support"}}}},
    {"state": "The parcel left the depot on Monday, was scanned in Lyon on Tuesday and has not moved since.",
     "questions": {"lost": {"type": "noul", "instructions": "Should the parcel be declared lost?",
                            "criteria": {"true": "yes", "false": "no"}},
                   "next": {"type": "choice", "instructions": "What should happen next?",
                            "criteria": {"wait": "Wait two more days", "trace": "Open a trace with the carrier",
                                         "refund": "Refund the customer now"}}}},
    {"state": {"review": "Battery lasts two days, screen is dim outdoors, support replaced it once without fuss.",
               "stars": 3},
     "questions": {"tone": {"type": "score", "instructions": "How positive is the review?",
                            "criteria": ["Negative", "Mixed", "Positive"]},
                   "issue": {"type": "choice", "instructions": "What is the main complaint?",
                             "criteria": {"battery": "Battery", "screen": "Screen", "support": "Support", "none": "No complaint"}}}},
]


def _mode_of(value, default):
    """The attention mode a request asks for: "causal" | "bidirectional" (or one-way / two-way), else the default."""
    if value is None:
        return default
    m = MODE_ALIASES.get(str(value).strip().lower()) if isinstance(value, str) else None
    if m is None:
        raise BadRequest(f"attention_mode must be one of {list(MODE_ALIASES)}")
    return m


class TwoWay:
    """serve_config.json's "two_way" block: the two-way (bidirectional) reading through vLLM's pooling runner (the
    only engine unless the Box pair runs). "label_rows": the lm_head rows of the label tokens (pooled_readout.py's file; a path relative to the
    config); "temperature" / "noul_floor" / "image_temperature": that mode's calibration (the same shapes as the
    one-way ones; a missing one takes the one-way value with a warning); "default": the mode a request without
    `attention_mode` gets once the second engine is configured ("bidirectional" unless set; SHIM_ATTENTION_MODE
    overrides); "endpoint": "/v1/embeddings" (vLLM's pooling runner)."""

    def __init__(self, block, contract, config_dir, env=os.environ):
        path = block.get("label_rows", "label_rows.lightning")
        if not isinstance(path, str) or not path:
            raise ValueError("two_way.label_rows must name the label-row file")
        if not os.path.isabs(path):
            path = os.path.join(config_dir or os.path.dirname(os.path.abspath(__file__)), path)
        self.label_rows_path = path
        self.labels = list(contract.labels)
        self.rows = None                  # read by load_rows() when the two-way engine is configured
        self.endpoint = str(block.get("endpoint", "/v1/embeddings"))
        if self.endpoint not in ("/v1/embeddings", "/pooling"):
            raise ValueError("two_way.endpoint must be /v1/embeddings or /pooling")
        d = env.get("SHIM_ATTENTION_MODE", "").strip() or block.get("default", "bidirectional")
        self.default = MODE_ALIASES.get(str(d).strip().lower())
        if self.default is None:
            raise ValueError(f"two_way.default (or SHIM_ATTENTION_MODE) must be one of {list(MODE_ALIASES)}")
        self.warnings = []
        t_env, f_env = env.get("SHIM_TEMPERATURE", "").strip(), env.get("SHIM_NOUL_FLOOR", "").strip()
        t = block.get("temperature")
        if t_env:                         # the one-way overrides apply to both modes
            self.temperature_by_type = {k: float(t_env) for k in PRIMITIVES}
        elif t is None:
            self.temperature_by_type = dict(contract.temperature_by_type)
            self.warnings.append("two_way.temperature is not set: two-way answers use the one-way temperatures")
        elif isinstance(t, dict):
            if set(t) != set(PRIMITIVES):
                raise ValueError(f"two_way.temperature by type must give exactly {list(PRIMITIVES)}, got {sorted(t)}")
            self.temperature_by_type = {k: float(t[k]) for k in PRIMITIVES}
        else:
            self.temperature_by_type = {k: float(t) for k in PRIMITIVES}
        if not all(0.05 <= x <= 20.0 for x in self.temperature_by_type.values()):
            raise ValueError(f"two_way.temperature {self.temperature_by_type} is outside [0.05, 20]")
        f = block.get("noul_floor")
        if f_env:
            self.noul_floor = float(f_env)
        elif f is None:
            self.noul_floor = contract.noul_floor
            self.warnings.append("two_way.noul_floor is not set: two-way answers use the one-way floor")
        else:
            self.noul_floor = float(f)
            if self.noul_floor and not 0.5 < self.noul_floor < 1.0:
                raise ValueError(f"two_way.noul_floor {self.noul_floor}: must be in (0.5, 1), or 0 to turn it off")
        it = env.get("SHIM_IMAGE_TEMPERATURE", "").strip() or block.get("image_temperature")
        if it is None:
            self.image_temperature = contract.image_temperature
            if contract.images:
                self.warnings.append("two_way.image_temperature is not set: two-way image answers use the one-way one")
        else:
            self.image_temperature = float(it)
            if not 0.05 <= self.image_temperature <= 20.0:
                raise ValueError("two_way.image_temperature must be in [0.05, 20]")
        self.min_separation = TWO_WAY_MIN_SEPARATION
        # the release's recorded two-way answers to TWO_WAY_PROBES at T = 1 (one {qid: {option: p}} per probe) and
        # the tolerance the engine's answers must stay within: the start-up guard of a deployment without the
        # one-way engine rests on them
        ref = block.get("probe_reference")
        self.probe_tolerance = float(block.get("probe_tolerance", 0.05))
        if not 0.0 < self.probe_tolerance < 0.5:
            raise ValueError("two_way.probe_tolerance must be in (0, 0.5)")
        if ref is not None:
            if not isinstance(ref, list) or len(ref) != len(TWO_WAY_PROBES):
                raise ValueError(f"two_way.probe_reference must hold one entry per probe ({len(TWO_WAY_PROBES)})")
            for k, (entry, body) in enumerate(zip(ref, TWO_WAY_PROBES)):
                for qid, q in body["questions"].items():
                    names = options_of(q, len(contract.labels))[0]
                    dist = entry.get(qid) if isinstance(entry, dict) else None
                    if not isinstance(dist, dict) or set(dist) != set(names):
                        raise ValueError(f"two_way.probe_reference[{k}][{qid!r}] must give a probability per option {names}")
                    if not all(isinstance(x, (int, float)) and 0.0 <= float(x) <= 1.0 for x in dist.values()) \
                            or abs(sum(float(x) for x in dist.values()) - 1.0) > 1e-3:
                        raise ValueError(f"two_way.probe_reference[{k}][{qid!r}]: probabilities in [0, 1] summing to 1")
        self.probe_reference = ref

    def load_rows(self):
        """Read the label-row file (a deployment with the two-way engine; a one-way deployment never needs it)."""
        pr = _sibling("pooled_readout")
        self.rows = pr.read_label_rows(self.label_rows_path)
        n = len(self.labels)
        if self.rows.labels[:n] != self.labels:
            raise ValueError(f"two_way.label_rows: the file's labels {self.rows.labels[:6]}... are not this "
                             f"deployment's {self.labels[:6]}...")
        if self.rows.softcap:
            raise ValueError("two_way.label_rows: the file carries a logit softcap; this model has none")
        return self

    def groups(self, labels):
        return [(label, self.rows.group_for(label)) for label in labels]

    def describe(self):
        m = self.rows.metadata if self.rows is not None else {}
        return {"default": self.default, "endpoint": self.endpoint, "temperature_by_type": dict(self.temperature_by_type),
                "noul_floor": self.noul_floor, "image_temperature": self.image_temperature,
                "label_rows": {"path": os.path.basename(self.label_rows_path),
                               **({"labels": len(self.rows.labels), "hidden": self.rows.hidden,
                                   "lm_head_sha256": m.get("lm_head_sha256"), "model_sha256": m.get("model_sha256")}
                                  if self.rows is not None else {})},
                "warnings": list(self.warnings)}


class Contract:
    """The serving settings, from serve_config.json."""

    def __init__(self, cfg, env=os.environ):
        p = cfg["prompt"]
        self.cfg = cfg
        self.model = cfg["model"]
        self.chat = bool(p.get("chat_template", True))
        if p.get("enable_thinking", False):
            raise ValueError("prompt.enable_thinking must be false: the answer is read after a closed think block")
        self.system = p.get("system") or None
        self.layout = p.get("layout", "plain")
        self.state_compact = bool(p.get("state_compact", True))
        self.prefill = p.get("prefill", "Answer:")
        # SHIM_SELECTOR / prompt.selector: v2 (default) or headtail; SHIM_MAX_STATE_TOKENS: under v2 a cap on the record
        # below what the context allows (unset: the context is the limit), under headtail the cut (prompt.max_state_tokens)
        self.selector = (env.get("SHIM_SELECTOR", "").strip().lower() or str(p.get("selector") or "v2").strip().lower())
        if self.selector not in SELECTORS:
            raise ValueError(f"selector {self.selector!r}: one of {list(SELECTORS)}")
        ms = env.get("SHIM_MAX_STATE_TOKENS", "").strip()
        self.state_cap = int(ms) if ms else None
        self.max_state_tokens = int(ms) if ms else int(p.get("max_state_tokens", 32000))
        self.default_instructions = p.get("default_instructions", "Answer the question below.")
        if not isinstance(cfg.get("labels"), list):
            raise ValueError("serve_config.json: `labels` must be the list of option labels, in order")
        self.labels = [str(l) for l in cfg["labels"]][: int(cfg.get("max_options", len(cfg["labels"])))]
        if len(set(self.labels)) != len(self.labels):
            raise ValueError("serve_config.json: the labels are not distinct")
        self.label_ids = None             # each label's token id at the answer slot, read from vLLM's tokenizer
        # SHIM_TEMPERATURE / SHIM_NOUL_FLOOR override the config; SHIM_NOUL_FLOOR=0 turns the floor off
        t_env, f_env = env.get("SHIM_TEMPERATURE", "").strip(), env.get("SHIM_NOUL_FLOOR", "").strip()
        # "temperature" is one number for every type, or {"choice": T, "noul": T, "score": T}; SHIM_TEMPERATURE sets
        # every type to one value
        t_cfg = cfg["temperature"]
        if t_env:
            self.temperature_by_type = {t: float(t_env) for t in PRIMITIVES}
        elif isinstance(t_cfg, dict):
            if set(t_cfg) != set(PRIMITIVES):
                raise ValueError(f"temperature by type must give exactly {list(PRIMITIVES)}, got {sorted(t_cfg)}")
            self.temperature_by_type = {t: float(t_cfg[t]) for t in PRIMITIVES}
        else:
            self.temperature_by_type = {t: float(t_cfg) for t in PRIMITIVES}
        self.temperature = self.temperature_by_type["choice"]      # the image path's default and the start-up line
        self.temperature_source = "SHIM_TEMPERATURE" if t_env else "serve_config.json"
        self.noul_floor = float(f_env) if f_env else float(cfg["noul_floor"])
        self.noul_floor_source = "SHIM_NOUL_FLOOR" if f_env else "serve_config.json"
        if not all(0.05 <= t <= 20.0 for t in self.temperature_by_type.values()):
            raise ValueError(f"temperature {self.temperature_by_type} is outside [0.05, 20]")
        if self.noul_floor and not 0.5 < self.noul_floor < 1.0:
            raise ValueError(f"noul_floor {self.noul_floor}: must be in (0.5, 1), or 0 to turn it off")
        # IMAGES: on only with an "image" block. SHIM_MAX_IMAGES / SHIM_MAX_PIXELS / SHIM_IMAGE_TEMPERATURE override it;
        # max_pixels goes to vLLM's image processor with every image request (0: the server's own setting)
        im = cfg.get("image")
        self.images = isinstance(im, dict)
        im = im if self.images else {}
        mi, mp, it = (env.get(k, "").strip() for k in ("SHIM_MAX_IMAGES", "SHIM_MAX_PIXELS", "SHIM_IMAGE_TEMPERATURE"))
        self.max_images = int(mi) if mi else int(im.get("max_images", 4))
        self.max_pixels = int(mp) if mp else int(im.get("max_pixels", 0) or 0)
        self.image_temperature = float(it) if it else float(im.get("temperature", self.temperature))

        # the Box question (box.py): always answered on an image deployment (no on/off switch; the grounding is a
        # guided generation, refused with BOX_NEEDS_GUIDED by an engine without structured outputs); the grounding
        # convention, the readout temperature
        bx = cfg.get("box") or {}
        old = [k for k in BOX_REMOVED_SWITCHES if os.environ.get(k, "").strip()] + \
              [f"box.{k}" for k in ("enabled", "guided") if k in bx]
        if old:
            sys.stderr.write(f"shim: {', '.join(old)} ignored: box questions are always answered on an image "
                             f"deployment, by guided generation (there is no box on/off setting)\n")
        self.box_convention = os.environ.get("LIGHTNING_BOX_CONVENTION") or bx.get("convention") or "qwen1000"
        self.box_temperature = float(os.environ.get("LIGHTNING_BOX_TEMPERATURE") or bx.get("temperature") or 1.0)
        self.box_max_tokens = int(bx.get("max_tokens") or 64)
        self.box_mode = str(os.environ.get("LIGHTNING_BOX_MODE") or bx.get("mode") or "generate")  # generate | edges | hybrid
        self.box_scheme = str(os.environ.get("LIGHTNING_BOX_SCHEME") or bx.get("scheme") or "flat")  # flat | two_level
        self.box_bins = int(os.environ.get("LIGHTNING_BOX_BINS") or bx.get("bins") or (26 if self.box_scheme == "two_level" else 100))
        self.box_hybrid_threshold = float(os.environ.get("LIGHTNING_BOX_HYBRID_THRESHOLD") or bx.get("hybrid_threshold") or 0.7)
        # the readouts (tightness, presence, edges) may read a smaller image than the grounding; 0 = max_pixels
        self.box_readout_max_pixels = int(os.environ.get("LIGHTNING_BOX_READOUT_MAX_PIXELS") or bx.get("readout_max_pixels") or 0)
        # box.confidence "generation": the box and its confidence from the one generation's own token distributions
        # (no tightness prefill); box.presence off: no presence prefill; generation_temperature sharpens the digit
        # distributions; generation_calibration (a, b) is the Platt map of that confidence, (1, 0) the identity
        self.box_confidence = str(os.environ.get("LIGHTNING_BOX_CONFIDENCE") or bx.get("confidence") or "tightness")
        bp = (os.environ.get("LIGHTNING_BOX_PRESENCE", "") or "").strip().lower()
        self.box_presence = bp in ("1", "true", "yes", "on") if bp else bool(bx.get("presence", True))
        gt = os.environ.get("LIGHTNING_BOX_GENERATION_TEMPERATURE") or bx.get("generation_temperature")
        self.box_generation_temperature = 1.0 if gt in (None, "") else float(gt)
        if not (math.isfinite(self.box_generation_temperature) and self.box_generation_temperature > 0):
            raise ValueError("box.generation_temperature must be a finite number above 0")
        self.box_top_logprobs = int(bx.get("top_logprobs") or 20)
        gc = bx.get("generation_calibration") or {}
        self.box_generation_calibration = (float(os.environ.get("LIGHTNING_BOX_GENERATION_A") or gc.get("a", 1.0)),
                                           float(os.environ.get("LIGHTNING_BOX_GENERATION_B") or gc.get("b", 0.0)))
        a_, b_ = self.box_generation_calibration
        if not (math.isfinite(a_) and math.isfinite(b_) and 0.2 <= a_ <= 3.0 and -5.0 <= b_ <= 5.0):
            raise ValueError("box.generation_calibration: a must be in [0.2, 3] and b in [-5, 5] (the identity is a=1, b=0)")
        if self.box_confidence not in ("tightness", "generation"):
            raise ValueError("box.confidence must be tightness or generation")
        if self.images and self.box_mode in ("generate", "hybrid") and self.box_convention not in _sibling("box").SCHEMAS:
            raise ValueError(f"box convention {self.box_convention!r} has no guided-generation schema (box mode "
                             f"{self.box_mode!r} generates the box): use one of {sorted(_sibling('box').SCHEMAS)}")
        if self.images and _sibling("box").needs_pillow(self.box_mode, self.box_confidence) and not _sibling("box").pillow_available():
            raise ValueError(f"image decisions (box mode {self.box_mode!r}, confidence {self.box_confidence!r}): {_sibling('box').PILLOW_HINT}")
        if self.images and not self.chat:
            raise ValueError("images need prompt.chat_template: the image path renders through the chat template")
        if self.images and not (1 <= self.max_images <= 16 and 0.05 <= self.image_temperature <= 20.0):
            raise ValueError("image.max_images must be in [1, 16] and image.temperature in [0.05, 20]")
        # TWO-WAY ATTENTION: the "two_way" block (TwoWay); its label rows are read here so a wrong file fails at startup
        tw = cfg.get("two_way")
        self.two_way = TwoWay(tw, self, cfg.get("_config_dir"), env) if isinstance(tw, dict) else None

    def question_parts(self, state_text, q, qid="q"):
        """(user text, option names, descriptions, labels) for one question."""
        names, descs = options_of(q, len(self.labels))
        if len(names) > len(self.labels):
            raise Unprocessable(f"question {qid}: {len(names)} options exceeds {len(self.labels)}")
        labels = self.labels[:len(names)]
        instr = render_instr(q.get("instructions", "")).lstrip() or self.default_instructions
        return user_turn(state_text, instr, names, descs, labels, self.layout), names, descs, labels

    def question_prompt(self, state_text, q, qid="q"):
        """(prompt text, option names, descriptions, labels) for one question."""
        user, names, descs, labels = self.question_parts(state_text, q, qid)
        return render_chat(self.system, user, self.prefill, self.chat), names, descs, labels

    def image_prompt(self, state_text, q, image_urls, qid="q"):
        """(chat messages, the same prompt as text with one VISION_SLOT per image, names, descriptions, labels)."""
        user, names, descs, labels = self.question_parts(state_text, q, qid)
        text = render_chat(self.system, VISION_SLOT * len(image_urls) + user.strip(), self.prefill, self.chat)
        return chat_messages(self.system, user, self.prefill, image_urls), text, names, descs, labels


# ------------------------------------------------------------------------------------------------- vLLM client
QUICKACK = getattr(socket, "TCP_QUICKACK", None)   # Linux; reset by the kernel, so set per request


# ------------------------------------------------------------------------------------------------- assets and Box
# The `assets` image-reference format (assets.py), the `box` question type (box.py), the two-way readout
# (pooled_readout.py) and the over-context state selection (selector_v2.py, the 31B's) are shipped beside this file (else the installed package's own are used). All are standard
# library only (box.py draws the box with Pillow, which vLLM installs; without it the shim refuses to start with images on).
# the shipped sha256 of the modules _sibling runs (a file with other bytes is refused)
SIBLING_SHA256 = {'box.py': 'e26ad9d8ea1ac501730d2d770c2aeebda642962bdb1d591c86f0cfb843274301', 'assets.py': 'e30ff2efd7628ade3cdc548c936751db9c433e6ad3a143f4d122b0baddcdc94c', 'pooled_readout.py': 'd59e62ccb3b5af742021e8064a5987ee27291744ea043ad94fbc8baa4eee1199', 'selector_v2.py': 'bd518a2c3bea9167803b6c21e480b37386fa212cf35101093b84e75c5307b7e3'}

# The tokenizer the model was trained with is Qwen2Tokenizer (tokenizer_config.json). From transformers 5.18 a checkpoint
# whose config says qwen3_5 is loaded with Qwen3_5Tokenizer instead, which splits some Devanagari and Arabic text
# differently; serve.sh passes --tokenizer <package>/tokenizer (the same files without a config.json), which keeps
# Qwen2Tokenizer. At start-up vLLM's /tokenize must reproduce tokenizer_contract.json's 24 probes (Qwen2Tokenizer's ids),
# else a 503. TOKENIZER_CONTRACT = None turns the check off (the tests' stand-in engine has its own vocabulary).
TOKENIZER_CONTRACT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokenizer_contract.json")
TOKENIZER_CONTRACT_SHA256 = "7eb96aaea6b7dbb495f0840b42f18014ca5a697697305f76f39d46cae890ccb2"


_SIBLINGS = {}
_SIBLING_LOCK = threading.Lock()


def _sibling(name):
    """The module `name` shipped beside this file (checked against its shipped sha256 first), else the installed
    package's own. Loaded once under a lock and handed out only after it has run, so concurrent first requests never
    see a half-loaded module."""
    import hashlib
    import importlib
    import importlib.util

    key = "_lightning_" + name
    module = _SIBLINGS.get(key)
    if module is not None:
        return module
    with _SIBLING_LOCK:
        if key in _SIBLINGS:
            return _SIBLINGS[key]
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name + ".py")
        if not os.path.exists(path):
            module = importlib.import_module(__name__.rsplit(".native_profiles.", 1)[0] + "." + name)
            _SIBLINGS[key] = module
            return module
        want = SIBLING_SHA256.get(name + ".py")
        with open(path, "rb") as f:
            got = hashlib.sha256(f.read()).hexdigest()
        if want is not None and got != want:
            raise UpstreamError(f"{name}.py beside the shim is not the shipped file (sha256 {got[:16]}, shipped "
                                f"{want[:16]}): restore it from the model repository", 503)
        spec = importlib.util.spec_from_file_location(key, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module  # registered while it runs (its own imports may look it up)
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(key, None)
            raise
        _SIBLINGS[key] = module  # published only now: no thread gets a half-loaded module
        return module


def box_generation_args(c):
    """The grounding call's extra arguments: the reply's token logprobs when box.confidence is "generation"."""
    return {"top_logprobs": c.box_top_logprobs} if c.box_confidence == "generation" else {}


BOX_NEEDS_GUIDED = ("unsupported_question_type: question type `box` (a bounding box) needs guided generation (structured "
                    "outputs, a JSON schema) and this engine refused it; serve vLLM with structured outputs on. Other "
                    "question types are unaffected")
BOX_REMOVED_SWITCHES = ("LIGHTNING_BOX_ENABLED", "LIGHTNING_BOX_GUIDED")   # no longer settings: ignored, said once
BOX_NOUL_TEXTS = {"true": "the statement holds", "false": "it does not"}   # the trained yes/no texts


def bind_assets(body):
    """The request's `assets` bound into the request: every reference becomes an image (assets.py); a bad map is a 400."""
    if not isinstance(body, dict) or ("assets" not in body and "_parts" not in body):
        return body
    _assets = _sibling("assets")
    parts = body.get("_parts")
    try:
        bare = {k: v for k, v in body.items() if k != "_parts"}
        return _assets.bind(bare, parts if isinstance(parts, dict) else None)
    except _assets.AssetError as e:
        raise BadRequest(f"unsupported_assets: {e}") from e


# the Box grounding's constrained decode: an engine refusal naming one of these means it has no structured outputs
GUIDED_UNAVAILABLE = re.compile(r"response_format|structured.?output|guided|grammar|json_schema|xgrammar|outlines", re.I)

_BOX_LOG = logging.getLogger("lightning.box")


class VLLM:
    """A keep-alive HTTP/1.1 connection per thread to one vLLM server."""

    def __init__(self, base, model):
        u = urllib.parse.urlsplit(base if "://" in base else "http://" + base)
        self.base = f"{u.scheme}://{u.netloc}"
        self.https = u.scheme == "https"
        self.host = u.netloc
        self.model = model
        self.local = threading.local()

    def _conn(self, fresh=False):
        c = getattr(self.local, "conn", None)
        if (
            c is not None
            and not fresh
            and c.sock is not None
            and (time.monotonic() - getattr(self.local, "used", 0.0) > IDLE_SECONDS or _peer_closed(c.sock))
        ):
            fresh = True
        if c is None or fresh:
            if c is not None:
                c.close()
            cls = http.client.HTTPSConnection if self.https else http.client.HTTPConnection
            c = self.local.conn = cls(self.host, timeout=TIMEOUT)
        return c

    def call(self, method, path, body=None):
        """(status, parsed JSON or text). A connection the server closed is reopened once."""
        data = None if body is None else json.dumps(body).encode()
        headers = {"Content-Type": "application/json"} if data is not None else {}
        for attempt in (0, 1):
            try:
                c = self._conn(fresh=attempt == 1)
                wait = c.timeout
                c.timeout = min(wait, SEND_SECONDS) if wait else SEND_SECONDS
                if c.sock is not None:
                    c.sock.settimeout(c.timeout)
                c.request(method, path, body=data, headers=headers)
                c.timeout = wait
                if c.sock is not None:
                    c.sock.settimeout(wait)
                if QUICKACK and c.sock is not None:   # ACK vLLM's reply at once: a kept-alive connection would
                    c.sock.setsockopt(socket.IPPROTO_TCP, QUICKACK, 1)   # otherwise delay it (~40 ms with Nagle)
                r = c.getresponse()
                raw = r.read()
                self.local.used = time.monotonic()
                break
            except (http.client.HTTPException, OSError) as e:
                if attempt == 1:
                    raise UpstreamError(f"vLLM at {self.base} unreachable: {type(e).__name__}: {e}") from e
        try:
            return r.status, json.loads(raw)
        except ValueError:
            return r.status, raw.decode("utf-8", "replace")

    def post(self, path, body, item_errors=(400,)):
        status, out = self.call("POST", path, body)
        if status == 200 and isinstance(out, dict):
            return out
        self.refuse(path, status, out, item_errors)

    def refuse(self, path, status, out, item_errors=(400,)):
        """The error for a non-200 answer (never returns): context limit, a refused item, upstream."""
        detail = json.dumps(out)[:500] if isinstance(out, dict) else str(out)[:500]
        if status in (400, 413) and _CONTEXT_ERROR.search(detail):
            raise Unprocessable(f"over the server's context limit: {detail}")
        if status in item_errors:
            raise Unprocessable(f"vLLM refused the request: {detail}")
        raise UpstreamError(f"vLLM {path} HTTP {status}: {detail}", status if status in (401, 403, 429) else 502)

    def tokenize(self, text):
        return self.post("/tokenize", {"model": self.model, "prompt": text, "add_special_tokens": False})["tokens"]

    def detokenize(self, ids):
        return self.post("/detokenize", {"model": self.model, "tokens": ids})["prompt"]

    def label_logprobs(self, prompt, ids, attention_mode=None, cache_write=None):
        """{token id: log-probability} at the answer slot, one completion per LOGPROB_CHUNK labels. attention_mode
        (the one-engine fork): "bidirectional" asks the engine to run this prompt's full-attention layers two-way;
        cache_write False: the read writes nothing to the prefix cache (PREFIX-CACHE WRITES above). usage carries the
        prompt's token ids (prompt_token_ids, from vLLM's return_token_ids), so no /tokenize call is needed."""
        out, usage = {}, None
        xargs = {**({"attention_mode": attention_mode} if attention_mode else {}),
                 **({"prefix_cache_write": False} if cache_write is False else {})}
        for k in range(0, len(ids), LOGPROB_CHUNK):
            chunk = ids[k:k + LOGPROB_CHUNK]
            r = self.post("/v1/completions", {
                **({"vllm_xargs": xargs} if xargs else {}),
                "model": self.model, "prompt": prompt, "max_tokens": 1, "temperature": 0.0,
                "logprobs": len(chunk), "logprob_token_ids": chunk, "return_tokens_as_token_ids": True,
                "add_special_tokens": False, "return_token_ids": usage is None})
            try:
                top = r["choices"][0]["logprobs"]["top_logprobs"][0]
                got = {int(key.split(":", 1)[1]): float(v) for key, v in top.items()}
            except (KeyError, IndexError, TypeError, ValueError) as e:
                raise UpstreamError(f"vLLM returned no label log-probabilities at the answer slot ({e})") from e
            missing = [i for i in chunk if i not in got]
            if missing:
                raise UpstreamError(f"vLLM omitted label tokens {missing[:5]} from logprob_token_ids")
            out.update({i: got[i] for i in chunk})
            if usage is None:
                usage = dict(r.get("usage") or {})
                pids = (r.get("choices") or [{}])[0].get("prompt_token_ids")
                if isinstance(pids, list):
                    usage["prompt_token_ids"] = pids
        return out, usage

    def embed(self, endpoint, token_ids=None, messages=None, max_pixels=0):
        """(the pooled vector as returned, prompt tokens) from the pooling runner: the prompt as token ids (the
        text path: the shim's exact prompt, nothing re-rendered) or as the image path's chat messages (the final
        assistant turn continued, as the one-way image path sends them), fp32 base64, no normalisation."""
        body = {"model": self.model, "use_activation": False, "encoding_format": "base64", "embed_dtype": "float32",
                "endianness": "little"}
        if messages is None:
            body.update({"input": [int(i) for i in token_ids], "add_special_tokens": False})
        else:
            body.update({"messages": messages, "add_generation_prompt": False, "continue_final_message": True,
                         "add_special_tokens": False, "chat_template_kwargs": {"enable_thinking": False}})
            if max_pixels:
                body["mm_processor_kwargs"] = {"max_pixels": int(max_pixels)}
        r = self.post(endpoint, body, item_errors=(400, 422))
        try:
            item = r["data"][0]
            data = item["embedding"] if "embedding" in item else item["data"]
        except (KeyError, IndexError, TypeError) as e:
            raise UpstreamError(f"vLLM {endpoint} returned no pooled vector ({type(e).__name__}: {e})") from e
        return data, int((r.get("usage") or {}).get("prompt_tokens") or 0)

    def tokenize_chat(self, messages):
        """vLLM's token ids for chat messages rendered as the image path renders them (no image parts here)."""
        return self.post("/tokenize", {"model": self.model, "messages": messages, "add_generation_prompt": False,
                                       "continue_final_message": True, "add_special_tokens": False,
                                       "chat_template_kwargs": {"enable_thinking": False}})["tokens"]

    def chat_generate(self, messages, max_tokens=64, max_pixels=0, json_schema=None, top_logprobs=0):
        """(text, prompt_tokens): one chat generation at temperature 0, thinking off (the Box grounding call);
        `json_schema`: the reply constrained to it (vLLM structured outputs, the OpenAI response_format shape). An
        engine that refuses the schema (no structured outputs) refuses the box question: a 422 with BOX_NEEDS_GUIDED,
        never an unguided generation."""
        body = {"model": self.model, "messages": messages, "max_tokens": int(max_tokens), "temperature": 0,
                "chat_template_kwargs": {"enable_thinking": False}}
        if top_logprobs:  # box.confidence "generation": the reply's per-token logprobs
            body["logprobs"] = True
            body["top_logprobs"] = int(top_logprobs)
        if max_pixels:
            body["mm_processor_kwargs"] = {"max_pixels": int(max_pixels)}
        if json_schema is None:
            r = self.post("/v1/chat/completions", body, item_errors=(400, 422))
        else:
            guided = dict(body, response_format={"type": "json_schema",
                                                 "json_schema": {"name": "box", "strict": True, "schema": json_schema}})
            status, r = self.call("POST", "/v1/chat/completions", guided)
            if status != 200 or not isinstance(r, dict):
                detail = json.dumps(r)[:500] if isinstance(r, dict) else str(r)[:500]
                if status in (400, 422) and GUIDED_UNAVAILABLE.search(detail):
                    _BOX_LOG.warning("box question refused: guided decoding unavailable on %s (%s)", self.base, detail[:200])
                    raise Unprocessable(BOX_NEEDS_GUIDED)
                self.refuse("/v1/chat/completions", status, r, (400, 422))
        try:
            text = r["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise UpstreamError(f"vLLM returned no generation ({type(e).__name__}: {e})") from e
        out = ((text if isinstance(text, str) else ""), int((r.get("usage") or {}).get("prompt_tokens") or 0))
        if not top_logprobs:
            return out
        try:
            content = r["choices"][0]["logprobs"]["content"]
            tokens = [(str(c["token"]), float(c["logprob"]), [(str(a["token"]), float(a["logprob"])) for a in c.get("top_logprobs") or []])
                      for c in content]
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise UpstreamError(f"vLLM returned a generation without its logprobs ({type(e).__name__}: {e})") from e
        return out + (tokens,)

    def label_logprobs_chat(self, messages, ids, max_pixels=0, attention_mode=None, cache_write=None):
        """label_logprobs for a chat with images: the final assistant turn (the prefill) is continued, so the answer
        slot is the same position as in the text prompt. One chat completion per LOGPROB_CHUNK labels."""
        out, usage = {}, None
        for k in range(0, len(ids), LOGPROB_CHUNK):
            chunk = ids[k:k + LOGPROB_CHUNK]
            xargs = {**({"attention_mode": attention_mode} if attention_mode else {}),
                     **({"prefix_cache_write": False} if cache_write is False else {})}
            body = {**({"vllm_xargs": xargs} if xargs else {}),
                    "model": self.model, "messages": messages, "max_completion_tokens": 1, "temperature": 0.0,
                    "logprobs": True, "logprob_token_ids": chunk, "return_tokens_as_token_ids": True,
                    "add_generation_prompt": False, "continue_final_message": True, "add_special_tokens": False,
                    "chat_template_kwargs": {"enable_thinking": False}}
            if max_pixels:
                body["mm_processor_kwargs"] = {"max_pixels": int(max_pixels)}
            # an image vLLM cannot load (a URL it cannot fetch, bytes it cannot decode) is a 422 from vLLM: one bad item
            r = self.post("/v1/chat/completions", body, item_errors=(400, 422))
            try:
                top = r["choices"][0]["logprobs"]["content"][0]["top_logprobs"]
                got = {int(e["token"].split(":", 1)[1]): float(e["logprob"]) for e in top}
            except (KeyError, IndexError, TypeError, ValueError, AttributeError) as e:
                raise UpstreamError(f"vLLM returned no label log-probabilities at the answer slot ({e})") from e
            missing = [i for i in chunk if i not in got]
            if missing:
                raise UpstreamError(f"vLLM omitted label tokens {missing[:5]} from logprob_token_ids")
            out.update({i: got[i] for i in chunk})
            usage = usage or r.get("usage") or {}
        return out, usage


def cache_writes(n):
    """Per read of an n-question one-way request: None (vLLM's default, the read writes to the prefix cache) or False
    (it writes nothing), by SHIM_CACHE_WRITE (PREFIX-CACHE WRITES above)."""
    if CACHE_WRITE == "all":
        return [None] * n
    if CACHE_WRITE == "none" or n == 1:
        return [False] * n
    return [None] + [False] * (n - 1)


def common_prefix_len(seqs):
    """The length of the longest common prefix of several token id lists; 0 for fewer than two."""
    if len(seqs) < 2:
        return 0
    n = min(len(x) for x in seqs)
    for i in range(n):
        if any(x[i] != seqs[0][i] for x in seqs[1:]):
            return i
    return n


# ------------------------------------------------------------------------------------------------------ server
class Shim:
    def __init__(self, contract, vllm=None, min_context=4096, two_way_vllm=None, model_dir=None):
        self.c = contract
        self.v = vllm                     # the generate-mode vLLM (one-way readouts, Box), or None
        self.p = two_way_vllm             # the pooling-runner vLLM (two-way attention), or None
        if self.v is None and self.p is None:
            raise ValueError("the shim needs a vLLM: --vllm (one-way) and/or --vllm-two-way (two-way)")
        if self.p is not None and self.c.two_way is None:
            raise ValueError("--vllm-two-way needs a \"two_way\" block in serve_config.json (the label rows)")
        if self.p is not None:
            self.c.two_way.load_rows()    # the label-row file: read (and checked) only when the engine is configured
        self.t = self.v if self.v is not None else self.p   # the engine the tokenizer calls go to (both serve /tokenize)
        # ONE-ENGINE TWO-WAY (the vLLM fork with per-request attention): SHIM_TWO_WAY_FLAG=1 makes the generate engine
        # serve two-way readouts through vllm_xargs attention_mode=bidirectional; no pooling engine, no label rows
        self.two_way_flag = bool(os.environ.get("SHIM_TWO_WAY_FLAG", "").strip() == "1")
        self.model_dir = model_dir        # the served weights (model.safetensors): the label rows' identity check
        self.min_context = min_context
        self.ready = None                 # the backend check, done once at first use (vLLM may start later)
        self.ready_lock = threading.Lock()
        self.max_model_len = None
        self.chat_ok = None               # the image path's template check, done once at the first image request
        self.two_way_ok = None            # the two-way engine's check, done once at the first two-way request
        self.two_way_separation = None    # the probes' measured max |dp| between the two engines (the pair only)
        self.two_way_anchor = None        # the probes' measured max |dp| from the release's recorded two-way answers
        self.two_way_failed = None        # (time, reason) of a failed check: kept TWO_WAY_RETRY_SECONDS, then re-run
        self.pool = ThreadPoolExecutor(max_workers=int(os.environ.get("SHIM_QUESTION_THREADS", "64")))

    # ---- two-way attention
    def default_mode(self):
        """The mode a request without `attention_mode` gets: two_way.default with both engines, else the mode of the
        one engine that runs."""
        if self.two_way_flag:
            return (self.c.two_way.default if self.c.two_way is not None else "bidirectional")
        if self.p is None:
            return "causal"
        return self.c.two_way.default if self.v is not None else "bidirectional"

    def mode(self, body):
        """The attention mode of a request: its `attention_mode`, else the deployment's default. A mode whose engine
        is not running is a 400 (never a silent answer in the other mode)."""
        asked = body.get("attention_mode") if isinstance(body, dict) else None
        m = _mode_of(asked, self.default_mode())
        if self.two_way_flag:
            return m                      # one engine serves both through the per-request flag
        if m == "bidirectional" and self.p is None:
            raise BadRequest("attention_mode bidirectional: two-way attention is not running on this deployment "
                             "(serve.sh with TWO_WAY=1, the default, serves it on one engine of the per-request "
                             "attention build; see the model card)")
        if m == "causal" and self.v is None:
            raise BadRequest("attention_mode causal: one-way attention is not running on this deployment (the two-way "
                             "engine alone is up); start serve.sh with TWO_WAY=0 for one-way only, or with the default one "
                             "engine of the per-request attention build, which serves both")
        return m

    def check_two_way(self):
        """Once, before the first two-way answer: the two-way vLLM serves the model; the label-row file belongs to
        the served weights (its model_sha256 against model.safetensors beside the config) and holds every label's
        token id (the ids check_backend read); the pooled state is not normalised; the engine's answers to the fixed
        probes are within two_way.probe_tolerance of the release's recorded two-way answers (other weights, another
        dtype, or an engine started without the is_causal override are refused); and, when the one-way engine runs
        too, the two engines answer the probes differently. A failure is a 503, kept TWO_WAY_RETRY_SECONDS."""
        if self.two_way_ok:
            return
        with self.ready_lock:
            if self.two_way_ok:
                return
            if self.two_way_failed and time.monotonic() - self.two_way_failed[0] < TWO_WAY_RETRY_SECONDS:
                raise UpstreamError(f"{self.two_way_failed[1]} (checked again every {TWO_WAY_RETRY_SECONDS:.0f} s)", 503)
            try:
                self._check_two_way()
            except UpstreamError as e:
                self.two_way_failed = (time.monotonic(), str(e))
                raise
            self.two_way_failed = None

    def weights_sha256(self):
        """sha256 of model.safetensors in model_dir (the served weights), hashed once and kept in a sidecar
        (.model_sha256.json: size, mtime, sha) beside it; None when there is no such file (served from elsewhere)."""
        if not self.model_dir:
            return None
        path = os.path.join(self.model_dir, "model.safetensors")
        if not os.path.isfile(path):
            return None
        st = os.stat(path)
        side = os.path.join(self.model_dir, ".model_sha256.json")
        try:
            cached = json.load(open(side, encoding="utf-8"))
            if cached.get("size") == st.st_size and cached.get("mtime") == st.st_mtime and len(cached.get("sha256", "")) == 64:
                return cached["sha256"]
        except (OSError, ValueError):
            pass
        import hashlib
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 24), b""):
                h.update(chunk)
        try:
            json.dump({"size": st.st_size, "mtime": st.st_mtime, "sha256": h.hexdigest()}, open(side, "w", encoding="utf-8"))
        except OSError:
            pass
        return h.hexdigest()

    def check_two_way_flag(self):
        """One-engine two-way (the fork): before the first two-way answer, the flagged readout of the fixed probes must
        match the release's recorded two-way answers (two_way.probe_reference) within two_way.probe_tolerance, and
        the unflagged readout must differ from them (an engine that ignores the flag answers one-way)."""
        if self.two_way_ok:
            return
        with self.ready_lock:
            if self.two_way_ok:
                return
            tw = self.c.two_way
            if tw is None or tw.probe_reference is None:
                raise UpstreamError("serve_config.json two_way.probe_reference is missing: the flagged two-way readout "
                                    "cannot be verified", 503)
            anchor, sep, worst = 0.0, 0.0, None
            for k, body in enumerate(TWO_WAY_PROBES):
                state_txt = render_state(body["state"], self.c.state_compact)
                for qid, q in body["questions"].items():
                    text, names, _d, labels = self.c.question_prompt(state_txt, q, qid)
                    p2 = probabilities(self.one(text, labels, "bidirectional")[0], 1.0)
                    p1 = probabilities(self.one(text, labels)[0], 1.0)
                    ref = tw.probe_reference[k][qid]
                    d = max(abs(a - float(ref[n])) for a, n in zip(p2, names))
                    if d > anchor:
                        anchor, worst = d, (k, qid)
                    sep = max(sep, max(abs(a - b) for a, b in zip(p1, p2)))
            self.two_way_anchor, self.two_way_separation = anchor, sep
            if anchor > tw.probe_tolerance:
                raise UpstreamError(f"the engine's flagged two-way readout does not match the release's probe answers "
                                    f"(max |dp| {anchor:.4f} at probe {worst[0]} question {worst[1]!r}, tolerance "
                                    f"{tw.probe_tolerance}): is this the per-request-attention vLLM build?", 503)
            if tw.min_separation and sep < tw.min_separation:
                raise UpstreamError(f"the engine answers flagged and unflagged requests alike (max |dp| {sep:.4f}): "
                                    f"it ignores attention_mode (stock vLLM?)", 503)
            self.two_way_ok = True
            sys.stderr.write(f"shim: one-engine two-way verified (max |dp| {anchor:.4f} from the release's probe "
                             f"answers; flagged vs unflagged {sep:.4f})\n")

    def _check_two_way(self):
        tw, pr = self.c.two_way, _sibling("pooled_readout")
        status, out = self.p.call("GET", "/v1/models")
        models = (out.get("data") or []) if isinstance(out, dict) else []
        if status != 200 or not any(isinstance(m, dict) and m.get("id") == self.c.model for m in models):
            raise UpstreamError(f"the two-way vLLM at {self.p.base} does not serve {self.c.model!r} "
                                f"(start it with --served-model-name {self.c.model})", 503)
        served = self.weights_sha256()
        want = tw.rows.metadata.get("model_sha256")
        if served is None:
            sys.stderr.write("shim: WARNING: no model.safetensors beside the config; the label rows' identity is not checked\n")
        elif want != served:
            raise UpstreamError(f"the label rows in {os.path.basename(tw.label_rows_path)} belong to another checkpoint "
                                f"(model_sha256 {str(want)[:12]}, served model.safetensors {served[:12]})", 503)
        bad = [l for l in self.c.labels if self.c.label_ids[l] not in tw.rows.group_for(l)]
        if bad:
            raise UpstreamError(f"labels {bad[:5]} have a token id outside their row in {os.path.basename(tw.label_rows_path)} "
                                f"(the label rows belong to another model or tokenizer)", 503)
        if tw.probe_reference is None and self.v is None:
            raise UpstreamError("serve_config.json two_way.probe_reference is missing: the two-way engine cannot be "
                                "verified without the release's recorded probe answers", 503)
        # the probes at T = 1: within the tolerance of the release's recorded two-way answers (the anchors), and,
        # with the one-way engine up, apart from its answers
        anchor, sep, first, worst = 0.0, 0.0, None, None
        for k, body in enumerate(TWO_WAY_PROBES):
            state_txt = render_state(body["state"], self.c.state_compact)
            for qid, q in body["questions"].items():
                text, names, _d, labels = self.c.question_prompt(state_txt, q, qid)
                lp_two, _u, h = self.one_pooled(text, labels)
                if first is None:
                    first = h
                p2 = probabilities(lp_two, 1.0)
                if tw.probe_reference is not None:
                    ref = tw.probe_reference[k][qid]
                    d = max(abs(a - float(ref[n])) for a, n in zip(p2, names))
                    if d > anchor:
                        anchor, worst = d, (k, qid)
                if self.v is not None:
                    p1 = probabilities(self.one(text, labels)[0], 1.0)
                    sep = max(sep, max(abs(a - b) for a, b in zip(p1, p2)))
        try:
            pr.check_not_normalised(first)
        except ValueError as e:
            raise UpstreamError(str(e), 503) from e
        self.two_way_anchor, self.two_way_separation = (anchor if tw.probe_reference is not None else None), (sep if self.v is not None else None)
        launch = ("serve.sh TWO_WAY=1 does: --runner pooling --convert embed, --hf-overrides with is_causal false at "
                  "both config levels, prefix caching and chunked prefill off, the same model.safetensors")
        if tw.probe_reference is not None and anchor > tw.probe_tolerance:
            raise UpstreamError(f"the two-way vLLM at {self.p.base} does not answer the probes as the release did (max |dp| "
                                f"{anchor:.4f} at probe {worst[0]} question {worst[1]!r}, tolerance {tw.probe_tolerance}): "
                                f"other weights or dtype, or started without the two-way override? ({launch})", 503)
        if self.v is not None and tw.min_separation and sep < tw.min_separation:
            raise UpstreamError(f"the two-way vLLM at {self.p.base} answers like the one-way one (max |dp| {sep:.4f} "
                                f"over the probes, below {tw.min_separation}): was it started as {launch}?", 503)
        for w in tw.warnings:
            sys.stderr.write(f"shim: WARNING: {w}\n")
        self.two_way_ok = True
        sys.stderr.write(f"shim: two-way vLLM at {self.p.base} verified ({len(tw.rows.ids)} label rows, hidden {tw.rows.hidden}"
                         + (f"; weights {served[:12]}" if served else "")
                         + (f"; max |dp| {anchor:.4f} from the release's probe answers" if tw.probe_reference is not None else "")
                         + (f"; the engines differ by max |dp| {sep:.4f}" if self.v is not None else "") + ")\n")

    def one_pooled(self, prompt, labels):
        """One question's two-way readout: the prompt's token ids through the pooling runner, the label log-probabilities
        from the pooled state and the label rows. (log-probabilities, usage, the pooled vector)."""
        tw, pr = self.c.two_way, _sibling("pooled_readout")
        data, n = self.p.embed(tw.endpoint, token_ids=self.t.tokenize(prompt))
        try:
            lp, h = pr.read_pooled(data, tw.rows, tw.groups(labels))
        except ValueError as e:
            raise UpstreamError(f"two-way vLLM {tw.endpoint}: {e}") from e
        return lp, {"prompt_tokens": n}, h

    def one_chat_pooled(self, messages, labels):
        """The two-way readout of the image path: the chat messages (images ahead of the text, the prefill continued)
        through the pooling runner."""
        tw, pr = self.c.two_way, _sibling("pooled_readout")
        data, n = self.p.embed(tw.endpoint, messages=messages, max_pixels=self.c.max_pixels)
        try:
            lp, _h = pr.read_pooled(data, tw.rows, tw.groups(labels))
        except ValueError as e:
            raise UpstreamError(f"two-way vLLM {tw.endpoint}: {e}") from e
        return lp, {"prompt_tokens": n}

    def check_tokenizer(self):
        """vLLM's /tokenize reproduces the tokenizer contract's probes (Qwen2Tokenizer, the training tokenizer), else a
        503 that names the probes and the fix: a vLLM started without serve.sh's --tokenizer may load Qwen3_5Tokenizer."""
        path = TOKENIZER_CONTRACT
        if not path:
            return
        if not os.path.exists(path):
            sys.stderr.write(f"shim: {path} not found: vLLM's tokenizer is not checked against the training one\n")
            return
        import hashlib
        with open(path, "rb") as f:
            raw = f.read()
        if TOKENIZER_CONTRACT_SHA256 and hashlib.sha256(raw).hexdigest() != TOKENIZER_CONTRACT_SHA256:
            raise UpstreamError(f"{os.path.basename(path)} is not the shipped file: restore it from the model repository", 503)
        probes = json.loads(raw)["probes"]
        bad = [p["id"] for p in probes if self.t.tokenize(p["text"]) != p["token_ids"]]
        if bad:
            raise UpstreamError(f"vLLM's tokenizer splits {len(bad)} of {len(probes)} tokenizer_contract.json probes "
                                f"differently from the training tokenizer (Qwen2Tokenizer): {bad[:6]}; start vLLM with "
                                f"--tokenizer <the model folder>/tokenizer (serve.sh does)", 503)

    def check_backend(self):
        """vLLM serves the configured model with a usable context, and every label is ONE token at the answer slot:
        after a probe prompt with all the labels, appending " <label>" adds exactly one token, whose id is read."""
        if self.ready:
            return
        with self.ready_lock:
            if self.ready:
                return
            status, out = self.t.call("GET", "/v1/models")
            models = (out.get("data") or []) if isinstance(out, dict) else []
            entry = next((m for m in models if isinstance(m, dict) and m.get("id") == self.c.model), None)
            if status != 200 or entry is None:
                raise UpstreamError(f"vLLM at {self.t.base} does not serve {self.c.model!r} "
                                    f"(start it with --served-model-name {self.c.model})", 503)
            self.max_model_len = entry.get("max_model_len")
            if isinstance(self.max_model_len, int) and self.max_model_len < self.min_context:
                raise UpstreamError(f"vLLM's max_model_len {self.max_model_len} is below {self.min_context}", 503)
            n = len(self.c.labels)
            probe = {"type": "choice", "instructions": "Which?", "criteria": {f"o{i}": f"d{i}" for i in range(n)}}
            text = self.c.question_prompt(render_state({"x": 1}, self.c.state_compact), probe)[0]
            base = self.t.tokenize(text)
            ids, bad = {}, []
            for label in self.c.labels:
                full = self.t.tokenize(text + " " + label)
                if len(full) != len(base) + 1 or full[:len(base)] != base:
                    bad.append(label)
                else:
                    ids[label] = full[-1]
            if bad or len(set(ids.values())) != len(ids):
                raise UpstreamError(f"these labels are not one distinct token at the answer slot under vLLM's "
                                    f"tokenizer: {bad[:8]} (is this serve_config.json the one for this model?)", 503)
            self.check_tokenizer()
            self.c.label_ids = ids
            self.ready = True
            sys.stderr.write(f"shim: vLLM serves {self.c.model} (max_model_len {self.max_model_len}); "
                             f"{n} labels verified\n")

    def truncate_state(self, text):
        """Selector headtail (v1.4.1's cut, for comparison): a record over max_state_tokens keeps its head and its tail
        around a "..." line (vLLM's tokenizer)."""
        return self.cut_text(text, self.c.max_state_tokens)

    def cut_text(self, text, mx):
        """`text` cut to `mx` tokens by its head and tail around a "\n...\n" line (unchanged when it fits)."""
        if not mx or len(text.encode("utf-8", "ignore")) <= mx:      # a byte-level BPE never has more tokens than bytes
            return text
        ids = self.t.tokenize(text)
        if len(ids) <= mx:
            return text
        half = max(1, mx // 2)
        return self.t.detokenize(ids[:half]) + "\n...\n" + self.t.detokenize(ids[-half:])

    def image_tokens_bound(self):
        """An upper bound on one image's tokens in the prompt: max_pixels (else the processor's largest image) over
        the pixels per token, plus the vision start / end tokens."""
        return (self.c.max_pixels or 16777216) // PIXELS_PER_IMAGE_TOKEN + 2

    def fit_states(self, raw_state, full_txt, questions, n_images=0):
        """SELECTOR v2: ([(record text, user-turn override or None) per question], notes). A question whose prompt fits
        vLLM's context (and SHIM_MAX_STATE_TOKENS, when set) keeps the whole record, so a request that fits is read
        as before. One that does not gets the record BM25-selected (selector_v2, the 31B's) to the room its own prompt
        leaves: max_model_len less the prompt without the record, the images' tokens (an upper bound) and
        CONTEXT_SLACK; where no part of the record matches the question, its head and tail around a "\n...\n" line.
        A question that does not fit even without the record is answered without it, its instructions, then its
        option descriptions, then (in the prompt only) its option names cut to fit; the options, their order and
        labels never change. NEVER a refusal for length."""
        c, C = self.c, self.max_model_len
        img = n_images * self.image_tokens_bound()
        limit = (C - CONTEXT_SLACK) if isinstance(C, int) and C > 0 else None
        out, notes, n_state = [], [], None
        for qid, q in questions.items():
            if c.state_cap is None and (limit is None or len(c.question_prompt(full_txt, q, qid)[0].encode(
                    "utf-8", "ignore")) + img <= limit):           # bytes bound tokens: fits, no tokenizer call
                out.append((full_txt, None))
                continue
            if n_state is None:
                n_state = len(self.t.tokenize(full_txt))
            overhead = len(self.t.tokenize(c.question_prompt("", q, qid)[0])) + img
            room = None if limit is None else limit - overhead
            budget = room if c.state_cap is None else (c.state_cap if room is None else min(room, c.state_cap))
            if budget is None or n_state <= budget:
                out.append((full_txt, None))
                continue
            if room is not None and room < MIN_STATE_BUDGET:
                notes.append("question over the context; record left out")
                out.append(("", self.fit_question(q, qid, limit, img, notes)))
                continue
            st = self.select_record(raw_state, full_txt, q, budget, notes)
            for _ in range(3):                 # the exact count (the record's seams with the prompt can add a token)
                n = len(self.t.tokenize(c.question_prompt(st, q, qid)[0])) + img
                if limit is None or n <= limit:
                    break
                budget -= (n - limit) + 8
                if budget < MIN_STATE_BUDGET:
                    st = ""
                    break
                st = self.select_record(raw_state, full_txt, q, budget, notes)
            out.append((st, None))
        return out, notes

    def select_record(self, raw_state, full_txt, q, budget, notes):
        """The record cut to `budget` tokens for question q: selector_v2's BM25 on the raw state (its text output is
        the record), else (no matching part, or a record that cannot be split to fit) the head and tail."""
        sv2 = _sibling("selector_v2")
        try:
            st = sv2.select_state(raw_state, render_instr(q.get("instructions", "")), q.get("criteria"), budget,
                                  self.t.tokenize)
        except sv2.EvidenceSelectionUnsupported:
            notes.append("no match; head+tail")
            return self.cut_text(full_txt, budget)
        notes.append("bm25 (selector v2)")
        return st

    def fit_question(self, q, qid, limit, img, notes):
        """The user turn of a question too long for the context without its record: the instructions, then each
        option description, then each option name (in the prompt only; the answer keeps the request's names) cut by
        head and tail until the prompt fits `limit` tokens. None when the question fits with an empty record."""
        c = self.c
        names, descs = options_of(q, len(c.labels))
        labels = c.labels[:len(names)]
        instr = render_instr(q.get("instructions", "")).lstrip() or c.default_instructions
        parts = [instr, list(descs), list(names)]

        def user():
            return user_turn("", parts[0], parts[2], parts[1], labels, c.layout)

        def over():
            return len(self.t.tokenize(render_chat(c.system, user(), c.prefill, c.chat))) + img - limit
        if over() <= 0:
            return None
        for level, what in ((0, "instructions"), (1, "option descriptions"), (2, "option names")):
            ov = over()
            if ov <= 0:
                break
            notes.append(f"{what} cut to fit the context")
            if level == 0:
                k = len(self.t.tokenize(parts[0]))
                parts[0] = self.cut_text(parts[0], max(16, k - ov - 8))
            else:
                total = sum(len(self.t.tokenize(x)) for x in parts[level])
                per = max(4, (total - ov - 8) // max(1, len(parts[level])))
                parts[level] = [self.cut_text(x, per) for x in parts[level]]
        return user()

    def one(self, prompt, labels, attention_mode=None, cache_write=None):
        if self.v is None:
            raise BadRequest("one-way attention is not running on this deployment")
        ids = [self.c.label_ids[l] for l in labels]
        lp, usage = self.v.label_logprobs(prompt, ids, attention_mode, cache_write)
        return [lp[i] for i in ids], usage

    def decide(self, body):
        """The /v1/systemone handler: `assets` bound and box questions answered here (box.py), every other
        question by decide_questions. Raises BadRequest / Unprocessable / UpstreamError."""
        if not isinstance(body, dict) or not isinstance(body.get("questions"), dict):
            return self.decide_questions(body)
        t0 = time.time()
        mode = self.mode(body)
        if "assets" in body and not self.c.images:
            raise BadRequest("unsupported_assets: this model reads text only; image assets are not supported")
        body = bind_assets(body)  # `assets`: references become images (a 400 on a bad map)
        boxes = {qid: q for qid, q in body["questions"].items() if isinstance(q, dict) and q.get("type") == "box"}
        if not boxes:
            return self.decide_questions(body, mode)
        if not self.c.images:
            raise BadRequest("a box question needs an image deployment")
        if self.v is None:
            raise BadRequest("a box question is a generation and needs the one-way (generate-mode) vLLM, which is not "
                             "running: start serve.sh with the default one engine of the per-request attention build "
                             "(it serves both readings), or with TWO_WAY=0")
        if "state" not in body:
            raise Unprocessable("expected a JSON object with `state` and a `questions` object")
        self.check_backend()
        state, images = extract_images(body, self.c.max_images)
        box_answers, box_tokens = self.decide_boxes(boxes, state, images)
        rest = {qid: q for qid, q in body["questions"].items() if qid not in boxes}
        if not rest:
            return {"model": self.c.model, "answers": box_answers, "probability_source": "native",
                    "effort_used": {"tier": "fast", "passes_per_decision": 1},
                    "usage": {"input_tokens": box_tokens, "processed_input_tokens": box_tokens,
                              "output_tokens": len(box_answers), "latency_ms": round((time.time() - t0) * 1000, 1),
                              "images": len(images)},
                    "attention_mode": "causal"}   # a box is always a one-way generation
        out = self.decide_questions(dict(body, questions=rest), mode)
        out["answers"].update(box_answers)
        for key, n in (("input_tokens", box_tokens), ("output_tokens", len(box_answers))):
            out["usage"][key] = out["usage"].get(key, 0) + n
        if "processed_input_tokens" in out["usage"]:
            out["usage"]["processed_input_tokens"] += box_tokens
        return out

    def decide_boxes(self, boxes, state, images):
        """({qid: box answer}, input tokens): box.py's runner per question: the grounding through chat_generate under
        box.SYSTEM, the two yes/no readouts through the image path at the box temperature."""
        _box = _sibling("box")
        c = self.c
        self.check_chat()

        def generate(image_uri, prompt):
            system = _box.SYSTEM_BY_CONVENTION.get(c.box_convention, _box.SYSTEM)
            messages = chat_messages(system, prompt, "", [image_uri])[:-1]  # no prefill: a free generation
            schema = _box.SCHEMAS[c.box_convention]       # always guided (the Contract checked the convention)
            n = min(c.box_max_tokens, _box.GUIDED_MAX_TOKENS)
            return self.v.chat_generate(messages, n, c.max_pixels, json_schema=schema, **box_generation_args(c))

        def read_noul(image_uri, question_text):
            q = {"type": "noul", "instructions": question_text, "criteria": {"true": "yes", "false": "no"}}
            msgs, _text, _names, _descs, labels = c.image_prompt(
                render_state({"image": "[image 1]"}, c.state_compact), q, [image_uri], "box")
            ids = [c.label_ids[label] for label in labels]
            lp, usage = self.v.label_logprobs_chat(msgs, ids, c.box_readout_max_pixels or c.max_pixels)
            return (float(probabilities([lp[i] for i in ids], c.box_temperature)[0]),
                    int(usage.get("prompt_tokens") or 0))

        two_level = c.box_bins if c.box_scheme == "two_level" else None

        def read_edge(image_uri, question_text, n):
            """an edge readout: a choice over n ordinal options ("0".."n-1", rendered in order, never permuted), the
            full distribution at the box temperature (every label one token: check_backend)"""
            options = _box.band_options(n, "sub-band" in question_text) if two_level else _box.edge_options(n)
            q = {"type": "choice", "instructions": question_text, "criteria": options}
            msgs, _text, _names, _descs, labels = c.image_prompt(
                render_state({"image": "[image 1]"}, c.state_compact), q, [image_uri], "box")
            ids = [c.label_ids[label] for label in labels]
            lp, usage = self.v.label_logprobs_chat(msgs, ids, c.box_readout_max_pixels or c.max_pixels)
            return list(probabilities([lp[i] for i in ids], c.box_temperature)), int(usage.get("prompt_tokens") or 0)

        if c.box_mode != "generate" and c.box_bins > len(c.labels):
            raise BadRequest(f"box mode {c.box_mode!r} needs {c.box_bins} option labels; this deployment has "
                             f"{len(c.labels)} (set box.scheme two_level with box.bins <= labels)")
        answers, tokens = {}, 0
        for qid, q in boxes.items():
            try:
                answer, used = _box.run(q, state, images, generate=generate, read_noul=read_noul,
                                        convention=c.box_convention, mode=c.box_mode, read_edge=read_edge,
                                        bins=c.box_bins, two_level=two_level, submit=self.pool.submit,
                                        hybrid_threshold=c.box_hybrid_threshold,  # the independent calls concurrent
                                        confidence=c.box_confidence, presence=c.box_presence,
                                        generation_temperature=c.box_generation_temperature,
                                        generation_calibration=c.box_generation_calibration)
            except _box.PillowMissing as e:  # Pillow removed after start-up: a broken install stops the run
                raise UpstreamError(f"question {qid}: {e}", 503) from e
            except _box.BoxError as e:
                raise BadRequest(f"question {qid}: {e}") from e
            answers[qid] = answer
            tokens += used
        return answers, tokens

    def decide_questions(self, body, mode=None):
        """The /v1/systemone handler. Raises BadRequest / Unprocessable / UpstreamError."""
        t0 = time.time()
        if not isinstance(body, dict) or "state" not in body or not isinstance(body.get("questions"), dict):
            raise Unprocessable("expected a JSON object with `state` and a `questions` object")
        questions = body["questions"]
        if not questions:
            raise BadRequest("no questions")
        if not all(isinstance(q, dict) for q in questions.values()):
            raise Unprocessable("every question must be an object")
        effort = body.get("effort")
        if effort is not None and not isinstance(effort, (str, dict)):
            raise Unprocessable("effort must be a tier name or an object")
        asked = effort if isinstance(effort, str) or effort is None else effort.get("tier", "fast")
        if asked is not None and asked not in EFFORT_TIERS:
            raise BadRequest(f"effort tier {asked!r} is not one of {list(EFFORT_TIERS)}")
        mode = mode or self.mode(body)
        self.check_backend()
        if mode == "bidirectional":
            self.check_two_way_flag() if self.two_way_flag else self.check_two_way()
        if self.c.images:                  # an image deployment: a request that carries an image takes the image path
            state, images = extract_images(body, self.c.max_images)
            if images:
                return self.decide_images(questions, state, images, asked, t0, mode)
        full_txt = render_state(body["state"], self.c.state_compact)
        fits, notes = self.fit_request(body["state"], full_txt, questions)
        work = []
        for (qid, q), (state_txt, user) in zip(questions.items(), fits):
            text, names, descs, labels = self.c.question_prompt(state_txt, q, qid)
            if user is not None:           # the question itself cut to fit the context (the answer keeps its names)
                text = render_chat(self.c.system, user, self.c.prefill, self.c.chat)
            work.append((qid, q.get("type", "choice"), names, descs, text, labels, noul_threshold(q)))
        full = None
        if any(st != full_txt or u is not None for st, u in fits):   # a cut record is billed as if read whole
            full = self.full_input([self.c.question_prompt(full_txt, q, qid)[0] for qid, q in questions.items()])
        shared = 0
        writes = cache_writes(len(work)) if mode == "causal" else [None] * len(work)
        read = (lambda text, labels, w=None: self.one(text, labels, None, w)) if mode == "causal" else (
            (lambda text, labels, w=None: self.one(text, labels, "bidirectional")) if self.two_way_flag
            else (lambda text, labels, w=None: self.one_pooled(text, labels)[:2]))
        if len(work) == 1:
            reads = [read(work[0][4], work[0][5], writes[0])]
        else:                              # concurrently: vLLM batches them and its prefix cache shares the state
            futs = [self.pool.submit(read, w[4], w[5], c) for w, c in zip(work, writes)]
            reads = [f.result() for f in futs]
            # COUNT THE SHARED HEAD ONCE: the system prompt and the record are computed once by vLLM's prefix
            # cache, so N whole prompts would bill the record N times (the two-way engine has no prefix cache and
            # reads it N times: processed_input_tokens says so; input_tokens is the same count in both modes). The
            # prompts' token ids come back with the reads (prompt_token_ids); /tokenize only when they do not.
            toks = [r[1].get("prompt_token_ids") for r in reads]
            if not all(isinstance(t, list) for t in toks):
                toks = [self.t.tokenize(w[4]) for w in work]
            shared = common_prefix_len(toks)
        return self.respond(work, reads, shared, asked, t0, self.temperatures(mode), full_input=full, mode=mode,
                            notes=notes)

    def fit_request(self, raw_state, full_txt, questions, n_images=0):
        """[(record text, user-turn override) per question], notes: selector headtail cuts the record once (v1.4.1);
        selector v2 fits each question to the context (fit_states)."""
        if self.c.selector == "headtail":
            st = self.truncate_state(full_txt)
            return [(st, None)] * len(questions), (["head+tail (selector headtail)"] if st != full_txt else [])
        return self.fit_states(raw_state, full_txt, questions, n_images)

    def full_input(self, prompts, image_tokens=0):
        """Input tokens as if the whole record had been read: the full prompts, their shared head once, plus the
        image tokens (BILLING = THE FULL INPUT: a cut record gains speed, not a lower count)."""
        ids = [self.t.tokenize(p) for p in prompts]
        return sum(len(i) for i in ids) - common_prefix_len(ids) * (len(ids) - 1) + image_tokens

    def check_chat(self):
        """Once, before the first image request: vLLM's chat template renders our messages (with no image) to exactly
        the tokens of the text prompt, so the image path differs from the trained prompt only by the image tokens."""
        if self.chat_ok:
            return
        with self.ready_lock:
            if self.chat_ok:
                return
            probe = {"type": "choice", "instructions": "Which?", "criteria": {"a": "first", "b": "second"}}
            user, _n, _d, _l = self.c.question_parts(render_state({"x": 1}, self.c.state_compact), probe)
            want = self.t.tokenize(render_chat(self.c.system, user, self.c.prefill, self.c.chat))
            got = self.t.tokenize_chat(chat_messages(self.c.system, user, self.c.prefill, []))
            if got != want:
                k = common_prefix_len([got, want]) if got and want else 0
                raise UpstreamError(f"vLLM's chat template does not render the trained prompt (tokens differ from "
                                    f"position {k} of {len(want)}); is this the model's chat_template.jinja?", 503)
            self.chat_ok = True
            sys.stderr.write("shim: image path verified (chat template renders the trained prompt)\n")

    def one_chat(self, messages, labels, attention_mode=None, cache_write=None):
        if self.v is None:
            raise BadRequest("one-way attention is not running on this deployment")
        ids = [self.c.label_ids[l] for l in labels]
        lp, usage = self.v.label_logprobs_chat(messages, ids, self.c.max_pixels, attention_mode, cache_write)
        return [lp[i] for i in ids], usage

    def temperatures(self, mode):
        """(temperature by type, image temperature, yes/no floor) of a mode."""
        if mode == "bidirectional":
            tw = self.c.two_way
            return tw.temperature_by_type, tw.image_temperature, tw.noul_floor
        return self.c.temperature_by_type, self.c.image_temperature, self.c.noul_floor

    def decide_images(self, questions, state, images, asked, t0, mode="causal"):
        """The image path: the same record and question text, the images ahead of it, read through chat completions."""
        if len(images) > self.c.max_images:
            raise Unprocessable(f"{len(images)} images; this deployment reads at most {self.c.max_images} per request")
        self.check_chat()
        full_txt = render_state(state, self.c.state_compact)
        fits, notes = self.fit_request(state, full_txt, questions, len(images))
        work, msgs = [], []
        for (qid, q), (state_txt, user) in zip(questions.items(), fits):
            m, text, names, descs, labels = self.c.image_prompt(state_txt, q, images, qid)
            if user is not None:           # the question itself cut to fit the context (the answer keeps its names)
                m = chat_messages(self.c.system, user, self.c.prefill, images)
                text = render_chat(self.c.system, VISION_SLOT * len(images) + user.strip(), self.c.prefill, self.c.chat)
            msgs.append(m)
            work.append((qid, q.get("type", "choice"), names, descs, text, labels, noul_threshold(q)))
        shared = 0
        writes = cache_writes(len(work)) if mode == "causal" else [None] * len(work)
        read = (lambda m_, labels, w=None: self.one_chat(m_, labels, None, w)) if mode == "causal" else (
            (lambda m_, labels, w=None: self.one_chat(m_, labels, "bidirectional")) if self.two_way_flag
            else (lambda m_, labels, w=None: self.one_chat_pooled(m_, labels)))
        if len(work) == 1:
            reads = [read(msgs[0], work[0][5], writes[0])]
        else:
            futs = [self.pool.submit(read, m, w[5], c) for m, w, c in zip(msgs, work, writes)]
            toks = [self.pool.submit(self.t.tokenize, w[4]) for w in work]
            reads = [f.result() for f in futs]
            toks = [f.result() for f in toks]
            # the shared head holds the images: their tokens are what vLLM counted beyond the one-slot text prompt
            extra = max(0, int(reads[0][1].get("prompt_tokens") or 0) - len(toks[0]))
            shared = common_prefix_len(toks) + extra
        full = None
        if any(st != full_txt or u is not None for st, u in fits):   # billed as if read whole, images included
            extra = max(0, int(reads[0][1].get("prompt_tokens") or 0) - len(self.t.tokenize(work[0][4])))
            full = self.full_input([self.c.image_prompt(full_txt, q, images, qid)[1] for qid, q in questions.items()],
                                   extra)
        _t, image_t, floor = self.temperatures(mode)
        return self.respond(work, reads, shared, asked, t0, (image_t, None, floor), len(images), full, mode, notes)

    def respond(self, work, reads, shared, asked, t0, temperature, n_images=0, full_input=None, mode="causal",
                notes=None):
        """The response: each answer at `temperature` (one value, {type: T}, or the (by type, image, floor) triple of
        a mode; then the yes/no floor), and usage with the shared head once."""
        floor = self.c.noul_floor
        if isinstance(temperature, tuple):
            temperature, _it, floor = temperature
        answers, ntok, processed = {}, 0, 0
        for (qid, typ, names, descs, _t, _l, thr), (lp, usage) in zip(work, reads):
            t = temperature[typ] if isinstance(temperature, dict) else temperature
            answers[qid] = format_answer(typ, names, descs, lp, t, floor, thr)
            ntok += int(usage.get("prompt_tokens") or 0)
        processed = ntok                   # what the engine read (the two-way engine reads every prompt whole)
        ntok -= shared * (len(work) - 1)   # = the shared head + each question's tail
        used = {"tier": "fast", "passes_per_decision": 1}
        if asked and asked != "fast":
            used["requested"] = asked
            used["note"] = (f"tier {asked!r} is accepted for API compatibility but not implemented; this response "
                            f"was produced at tier 'fast' with one forward pass per decision")
        if notes:                          # only when a record or question was cut to fit (a request that fits: absent)
            used["state_selection"] = "; ".join(sorted(set(notes)))
        out = {"model": self.c.model, "answers": answers, "probability_source": "native", "effort_used": used,
               # input_tokens: the full input (processed_input_tokens: what vLLM read, less when a long record was
               # cut); output_tokens: one label token read per answered question
               "usage": {"input_tokens": ntok if full_input is None else full_input,
                         "processed_input_tokens": processed if mode == "bidirectional" else ntok,
                         "output_tokens": len(work), "latency_ms": round((time.time() - t0) * 1000, 1)}}
        if n_images:
            out["usage"]["images"] = n_images
        out["attention_mode"] = mode       # always: the mode the answers were read in
        return out

    def health(self):
        c = self.c
        return {"ok": bool(self.ready), "model": c.model, "shim": SHIM_VERSION,
                "backend": f"vllm {self.v.base}" if self.v is not None else None,
                "layout": c.layout, "chat_template": c.chat, "state_compact": c.state_compact, "prefill": c.prefill,
                "max_state_tokens": c.max_state_tokens, "selector": c.selector, "state_cap": c.state_cap,
                "noul_floor": {"value": c.noul_floor, "source": c.noul_floor_source},
                "temperature_by_type": dict(c.temperature_by_type),
                "temperature_source": c.temperature_source, "max_options": len(c.labels),
                "vllm_max_model_len": self.max_model_len,
                **({"images": {"max_images": c.max_images, "max_pixels": c.max_pixels or None,
                               "temperature": c.image_temperature, "verified": bool(self.chat_ok)}}
                   if c.images else {}),
                "attention_mode": self.default_mode(),
                "modes": ([m for m, e in (("causal", self.v), ("bidirectional", self.p)) if e is not None]
                          + (["bidirectional"] if self.two_way_flag and self.p is None else [])),
                **({"two_way": {**c.two_way.describe(), "backend": f"vllm {self.p.base}", "verified": bool(self.two_way_ok),
                                "probe_anchor_distance": self.two_way_anchor, "probe_separation": self.two_way_separation}}
                   if self.p is not None else {})}


# ------------------------------------------------------------------------------------------------- OpenAI Decisions
# POST /v1/decisions speaks OpenAI's Decisions API (client.decisions.create in the `openai` Python package): `input` (a
# string, or user messages with input_text / input_image parts) and an ordered `questions` list of predicate / choice
# / score questions. Each request is mapped onto the /v1/systemone decision above (the same readout and calibration),
# in the option format the model was trained on: a choice's string value is the option's name and its description the
# option's text, a score level is its label (with ": description" when given), a predicate is a yes/no question with
# the default wording. The answers come back in OpenAI's shape. `model` must be the served model (or its name without
# the organisation prefix, e.g. "h2o-lightning-4b"). An image's `detail` is accepted and not used (the deployment's own
# image cap applies).
def _oai_fail(text):
    raise BadRequest(text)


def _oai_fields(value, allowed, required=(), path="body"):
    if not isinstance(value, dict):
        _oai_fail(path + " must be an object")
    if set(value) - set(allowed):
        _oai_fail(path + " unknown fields: " + ", ".join(sorted(set(value) - set(allowed))))
    if set(required) - set(value):
        _oai_fail(path + " missing fields: " + ", ".join(sorted(set(required) - set(value))))


def _oai_string(value, path):
    if not isinstance(value, str):
        _oai_fail(path + " must be a string")


def openai_request(body, served):
    """(a /v1/systemone body, the answer mapping) for an OpenAI Decisions request; BadRequest when it is not one."""
    _oai_fields(body, {"model", "input", "questions", "safety_identifier", "attention_mode"}, ("model", "input", "questions"))
    _oai_string(body["model"], "model")
    if body["model"] not in (served, served.rsplit("/", 1)[-1]):
        _oai_fail(f"model must be the served model {served!r}")
    if body.get("safety_identifier") is not None:
        _oai_string(body["safety_identifier"], "safety_identifier")
    inp, images = body["input"], []
    if isinstance(inp, str):
        state = inp
    elif isinstance(inp, list) and inp:
        parts = []
        for message in inp:
            _oai_fields(message, {"role", "type", "content"}, ("role", "content"), "input message")
            if message["role"] != "user" or message.get("type", "message") != "message":
                _oai_fail("only user messages are supported")
            content = message["content"]
            if isinstance(content, str):
                parts.append({"role": "user", "content": [{"type": "input_text", "text": content}]})
                continue
            if not isinstance(content, list):
                _oai_fail("message content must be a string or ordered parts")
            ordered = []
            for part in content:
                if not isinstance(part, dict):
                    _oai_fail("an input part must be an object")
                if part.get("type") == "input_text":
                    _oai_fields(part, {"type", "text"}, ("type", "text"), "input_text")
                    _oai_string(part["text"], "input_text.text")
                    ordered.append(dict(part))
                elif part.get("type") == "input_image":
                    _oai_fields(part, {"type", "image_url", "detail"}, ("type", "image_url"), "input_image")
                    _oai_string(part["image_url"], "image_url")
                    url = part["image_url"]   # a data URI, or an http(s) link fetched by the safe fetch above
                    if not url.startswith("data:image/") and not (
                            url.lower().startswith(("https://", "http://"))
                            and os.environ.get("LIGHTNING_IMAGE_URLS", "fetch").lower() != "off"):
                        _oai_fail("image_url must be a data:image/... URI or an https image link")
                    if part.get("detail", "auto") not in ("auto", "low", "high", "original", None):
                        _oai_fail("image detail must be auto, low, high or original")
                    images.append(url)
                    ordered.append({"type": "input_image", "image_index": len(images) - 1})
                else:
                    _oai_fail("unsupported input part; only input_text and input_image are supported")
            parts.append({"role": "user", "content": ordered})
        state = {"messages": parts}
    else:
        _oai_fail("input must be a string or a non-empty array of user messages")
    if not isinstance(body["questions"], list) or not body["questions"]:
        _oai_fail("questions must be a non-empty ordered array")
    questions, mapping = {}, []
    for index, q in enumerate(body["questions"]):
        if not isinstance(q, dict):
            _oai_fail("a question must be an object")
        typ = q.get("type")
        _oai_fields(q, {"type", "instructions", "name"} | ({"choices"} if typ == "choice" else {"levels"}
                                                          if typ == "score" else set()), ("type", "instructions"),
                    "question")
        _oai_string(q["instructions"], "question.instructions")
        if "name" in q:
            _oai_string(q["name"], "question.name")
        internal, entry = {"instructions": q["instructions"]}, {"type": typ, "name": q.get("name")}
        if typ == "predicate":
            internal["type"] = "noul"
        elif typ == "choice":
            choices = q.get("choices")
            if not isinstance(choices, list) or not 2 <= len(choices) <= 255:
                _oai_fail("choices must contain 2..255 unique typed options")
            seen, values, descs = set(), [], []
            for number, choice in enumerate(choices):
                _oai_fields(choice, {"value", "description"}, ("value",), "choice")
                value = choice["value"]
                if type(value) not in (str, bool):
                    _oai_fail("a choice value must be a string or a boolean")
                if (type(value).__name__, value) in seen:
                    _oai_fail("choice values must be unique by type and value")
                seen.add((type(value).__name__, value))
                if "description" in choice:
                    _oai_string(choice["description"], "choice.description")
                values.append(value)
                descs.append(choice.get("description") or None)
            # the option names the model reads: the string values themselves (a boolean as true / false); option_N
            # for every option when two would read the same
            names = [v if isinstance(v, str) else ("true" if v else "false") for v in values]
            if len(set(names)) < len(names) or not all(n.strip() for n in names):
                names = ["option_" + str(j) for j in range(len(values))]
                descs = [d if d is not None else json.dumps(v) for d, v in zip(descs, values)]
            internal.update(type="choice", criteria=dict(zip(names, descs)))
            entry["values"], entry["names"] = values, names
        elif typ == "score":
            levels = q.get("levels")
            if not isinstance(levels, list) or not 1 <= len(levels) <= 255:
                _oai_fail("levels must contain 1..255 ordered levels")
            for level in levels:
                _oai_fields(level, {"label", "description"}, ("label",), "level")
                _oai_string(level["label"], "level.label")
                if "description" in level:
                    _oai_string(level["description"], "level.description")
            internal.update(type="score", criteria=[x["label"] + (": " + x["description"] if x.get("description") else "")
                                                    for x in levels])
            entry["labels"] = [x["label"] for x in levels]
        else:
            _oai_fail("question type must be predicate, choice or score")
        questions["q_" + str(index)] = internal
        mapping.append(entry)
    return {"state": state, "questions": questions, **({"images": images} if images else {}),
            **({"attention_mode": body["attention_mode"]} if body.get("attention_mode") is not None else {})}, mapping


def openai_response(core, mapping):
    """A /v1/systemone response in OpenAI's Decisions shape."""
    answers = []
    for i, meta in enumerate(mapping):
        a = core["answers"]["q_" + str(i)]
        common = {"type": meta["type"], "name": meta["name"]}
        if meta["type"] == "predicate":
            answers.append({**common, "probability": a["noul"]})
        elif meta["type"] == "choice":
            p = a["probabilities"]
            answers.append({**common, "choice": meta["values"][meta["names"].index(a["choice"])],
                            "confidence": a["confidence"],
                            "probabilities": [{"value": v, "probability": p[n]}
                                              for v, n in zip(meta["values"], meta["names"])]})
        else:
            answers.append({**common, "score": a["score"], "confidence": a["confidence"],
                            "probabilities": [{"label": label, "value": j, "probability": a["probabilities"][str(j)]}
                                              for j, label in enumerate(meta["labels"])]})
    usage = core["usage"]
    return {"model": core["model"], "answers": answers,
            "usage": {"input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"],
                      "total_tokens": usage["input_tokens"] + usage["output_tokens"],
                      "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                      "processed_input_tokens": usage["processed_input_tokens"],
                      "output_tokens_details": {"reasoning_tokens": 0}}}


def make_handler(shim):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        # TCP_NODELAY on each client connection: the headers and the body go out as two writes, and on a kept-alive
        # connection Nagle would hold the body until the client's (delayed, ~40 ms) ACK of the headers
        disable_nagle_algorithm = True

        def log_message(self, fmt, *args):
            if os.environ.get("SHIM_ACCESS_LOG", "") == "1":
                sys.stderr.write("shim %s\n" % (fmt % args))

        def _send(self, code, obj):
            payload = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path.startswith("/health"):
                try:
                    shim.check_backend()
                except (UpstreamError, Unprocessable) as e:
                    return self._send(503, {**shim.health(), "error": str(e)})
                # SHIM_READY_FILE (set by serve.sh): not ready until that file exists, i.e. until the launcher's warm-up
                # has passed; "/health?live=1" answers meanwhile (the launcher's own check)
                flag = os.environ.get("SHIM_READY_FILE", "").strip()
                live = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("live") == ["1"]
                if flag and not os.path.exists(flag) and not live:
                    return self._send(503, {**shim.health(), "ok": False, "warming": True})
                return self._send(200, shim.health())
            if self.path.startswith("/v1/models"):
                return self._send(200, {"object": "list", "data": [{"id": shim.c.model, "readout": "native label "
                                                                    "log-probabilities over vLLM"}]})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            openai = self.path.startswith("/v1/decisions")
            if not openai and not self.path.startswith(("/v1/systemone", "/api/alpha/decisions")):
                return self._send(404, {"error": "not found"})
            ctype = self.headers.get("Content-Type") or ""
            try:
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n)
                if shim.c.images and ctype.lower().startswith("multipart/form-data"):
                    body = parse_multipart(ctype, raw)
                else:
                    body = json.loads(raw or b"null")
            except Unprocessable as e:
                return self._send(422, {"detail": str(e)})
            except (ValueError, OSError) as e:
                return self._send(422, {"detail": f"request body is not JSON: {e}"})
            try:
                if openai:
                    request, mapping = openai_request(body, shim.c.model)
                    return self._send(200, openai_response(shim.decide(request), mapping))
                return self._send(200, shim.decide(body))
            except BadRequest as e:
                return self._send(400, {"detail": str(e)})
            except Unprocessable as e:
                return self._send(422, {"detail": str(e)})
            except UpstreamError as e:
                return self._send(e.status, {"detail": str(e)})
            except Exception as e:   # one item's failure is a 422, never a 500
                import traceback
                traceback.print_exc()
                return self._send(422, {"detail": f"{type(e).__name__}: {str(e)[:300]}"})

    return Handler


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 512      # the standard library's listen backlog of 5 resets concurrent clients


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", default=os.environ.get("SHIM_CONFIG", os.path.join(here, "serve_config.json")))
    ap.add_argument("--vllm", default=os.environ.get("SHIM_VLLM") or None,
                    help="the generate-mode vLLM (one-way readouts, Box); default http://127.0.0.1:8000 unless only --vllm-two-way is given")
    ap.add_argument("--vllm-two-way", default=os.environ.get("SHIM_VLLM_TWO_WAY") or None,
                    help="the pooling-runner vLLM (is_causal false) that serves two-way attention")
    ap.add_argument("--model-dir", default=os.environ.get("SHIM_MODEL_DIR") or None,
                    help="the served weights' folder (model.safetensors), for the label rows' identity check; default: the config's folder")
    ap.add_argument("--model", default=os.environ.get("SHIM_MODEL"),
                    help="vLLM's --served-model-name (default: serve_config.json's `model`)")
    ap.add_argument("--host", default=os.environ.get("SHIM_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("SHIM_PORT", "8741")))
    ap.add_argument("--min-context", type=int, default=int(os.environ.get("SHIM_MIN_CONTEXT", "4096")))
    a = ap.parse_args(argv)
    cfg = json.load(open(a.config))
    cfg.setdefault("_config_dir", os.path.dirname(os.path.abspath(a.config)))   # two_way.label_rows is relative to it
    if a.model:
        cfg["model"] = a.model
    contract = Contract(cfg)
    if a.vllm is None and a.vllm_two_way is None:
        a.vllm = "http://127.0.0.1:8000"
    one = VLLM(a.vllm, contract.model) if a.vllm else None
    two = VLLM(a.vllm_two_way, contract.model) if a.vllm_two_way else None
    shim = Shim(contract, one, a.min_context, two, a.model_dir or cfg["_config_dir"])
    srv = Server((a.host, a.port), make_handler(shim))
    print(f"shim on {a.host}:{a.port} (model {contract.model}, {len(contract.labels)} labels; default mode {shim.default_mode()}"
          + (f"; one-way -> {a.vllm}, T {contract.temperature_by_type}, yes/no floor {contract.noul_floor}" if one else "")
          + (f"; two-way -> {a.vllm_two_way}, T {contract.two_way.temperature_by_type}, yes/no floor "
             f"{contract.two_way.noul_floor}" if two else "")
          + ")", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
