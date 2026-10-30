"""Provider transport only; the frozen AC task and candidates remain unchanged."""

import json
import re

from run_ablation import choices

JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-latest"
GPT_MODEL = "us.openai.gpt-6.1-sol"
GPT_SYSTEM = (
    "Answer the supplied decision questions using the supplied state, including its task rules, "
    "and each question's instructions and candidate criteria. "
    "Return exactly one JSON object with the single key answers. Its value must be an object "
    "mapping EVERY supplied question ID to its selected candidate ID as a JSON string, "
    "including questions whose selected candidate is omit. "
    'Output shape: {"answers":{"QUESTION_ID":"CANDIDATE_ID"}}. '
    "Use only the supplied candidate IDs. Do not add explanations, probabilities, "
    "confidence estimates or Markdown."
)


def gpt_request(payload):
    return {
        "modelId": GPT_MODEL,
        "system": [{"text": GPT_SYSTEM}],
        "messages": [{"role": "user", "content": [
            {"text": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
        ]}],
        "inferenceConfig": {"maxTokens": 8192},
        "additionalModelRequestFields": {"reasoning": {"effort": "low"}},
    }


def jev_request(payload):
    return {**payload, "model": JEV_MODEL}


def decode_gpt(response, payload):
    if response.get("stopReason") != "end_turn":
        raise ValueError("GPT response did not complete with end_turn")
    text = "".join(p.get("text", "") for p in response["output"]["message"]["content"]).strip()
    fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    decoded = json.loads(fenced[1] if fenced else text)
    if not isinstance(decoded, dict) or set(decoded) != {"answers"}:
        raise ValueError("Expected exactly one answers object")
    answers = decoded["answers"]
    if not isinstance(answers, dict):
        raise ValueError("Expected an answer mapping")
    normalized = {
        "model": GPT_MODEL,
        "answers": {k: {"type": "choice", "choice": v} for k, v in answers.items()},
    }
    return choices(normalized, payload, GPT_MODEL)


def decode_jev(response, payload, expected_model=None):
    model = response.get("model")
    if not isinstance(model, str) or not model.startswith("jev-"):
        raise ValueError("Unexpected Jev model identity")
    if expected_model and model != expected_model:
        raise ValueError("Jev model changed from the preflight version")
    return choices(response, payload, model)
