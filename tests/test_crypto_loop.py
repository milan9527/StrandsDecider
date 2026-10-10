import json

import pytest
from fastapi.testclient import TestClient

from app import crypto_loop
from app.crypto import payload_for
from app.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("BEDROCK_ENABLED", raising=False)
    with TestClient(app, headers={"X-Decider-Client": "web"}) as client:
        assert (
            client.post(
                "/api/auth/login",
                json={"username": "tester", "password": "test-password-with-entropy"},
            ).status_code
            == 200
        )
        yield client


def initial(client, scenario="pending", **changes):
    s = next(
        c["snapshot"]
        for c in client.get("/api/crypto/catalog").json()["cases"]
        if c["id"] == scenario
    )
    return {"snapshot": {**s, **changes}}


def advance(client, state, auto=True, provider="decider"):
    response = client.post(
        "/api/crypto/loop/tick",
        json={"state": state, "provider": provider, "mode": "replay", "auto_events": auto},
    )
    assert response.status_code == 200, response.text
    return response.json()


def finish(client, state, auto=True, provider="decider"):
    rows = []
    for _ in range(35):
        row = advance(client, state, auto, provider)
        rows.append(row)
        state = row["state"]
        if state["status"] in ("complete", "handoff") or (
            state["status"] == "waiting" and (not auto or "clear_risk" in state["waiting_events"])
        ):
            return state, rows
    pytest.fail("Unbounded loop")


@pytest.mark.parametrize("provider", ["decider", "bedrock"])
@pytest.mark.parametrize(
    ("scenario", "events", "order"),
    [
        ("pending", ["confirm"], "paid"),
        ("underpaid", ["topup"], "paid"),
        ("refund", ["verify_address", "approve"], "refunded"),
        ("settlement", ["settle"], "settled"),
    ],
)
def test_autonomous_sandbox_completes_from_real_execution_feedback(
    client, provider, scenario, events, order
):
    state, rows = finish(client, initial(client, scenario), provider=provider)
    assert state["status"] == "complete"
    assert state["snapshot"]["order_status"] == order
    assert state["snapshot"]["ticket_status"] == "resolved"
    assert [r["event"]["name"] for r in rows if r["event"]] == events
    entries = [
        r["record"]["ledger_entry"] for r in rows if r["record"] and r["record"]["ledger_entry"]
    ]
    assert len(entries) == 1
    assert entries[0]["operation_id"].startswith(state["run_id"])
    assert all(not row["external_action_executed"] for row in rows)
    assert all(row["decision"]["source"] == "rule_replay" for row in rows if row["decision"])
    repeated = advance(client, state)
    assert repeated["record"] is None and repeated["decision"] is None
    assert repeated["state"] == state


def test_manual_event_wait_does_not_repeatedly_call_model(client):
    state, _ = finish(client, initial(client), auto=False)
    assert state["status"] == "waiting"
    assert state["waiting_events"] == ["confirm"]
    again = advance(client, state, auto=False)
    assert again["decision"] is None and again["event"] is None
    assert again["state"] == state
    resumed, _ = finish(client, state, auto=True)
    assert resumed["status"] == "complete"


def test_automatic_simulator_never_clears_risk(client):
    state, rows = finish(client, initial(client, risk_flag=True))
    assert state["status"] == "waiting" and state["waiting_events"] == ["clear_risk"]
    assert state["snapshot"]["risk_flag"] is True
    assert all(r["event"] is None for r in rows)


@pytest.mark.parametrize(
    ("stage", "wrong"), [("approve", "await_approval"), ("execute", "hold"), ("close", "follow_up")]
)
def test_replans_after_bad_choice_and_never_duplicates_funds(client, monkeypatch, stage, wrong):
    original = crypto_loop.decision
    calls = []
    corrupted = False

    async def choose(body, request):
        nonlocal corrupted
        calls.append(body)
        answer = await original(body, request)
        if body.stage == stage and not corrupted:
            corrupted = True
            answer.update(choice=wrong, matches_reference=False)
        return answer

    monkeypatch.setattr(crypto_loop, "decision", choose)
    state, rows = finish(client, initial(client, confirmations=12))
    assert state["status"] == "complete"
    retries = [c for c in calls if c.stage == stage]
    assert len(retries) == 2
    feedback = json.loads(
        payload_for(retries[1].snapshot, stage, retries[1].execution_feedback)["state"]
    )
    assert feedback["execution"]["recent_feedback"][-1]["requested_action"] == wrong
    assert feedback["execution"]["recent_feedback"][-1]["status"] == "retry"
    assert len([r for r in rows if r["record"] and r["record"]["ledger_entry"]]) == 1


def test_no_progress_hands_off_instead_of_substituting_rule_answer(client, monkeypatch):
    original = crypto_loop.decision

    async def choose(body, request):
        answer = await original(body, request)
        if body.stage == "execute":
            answer.update(choice="hold", matches_reference=False)
        return answer

    monkeypatch.setattr(crypto_loop, "decision", choose)
    state, rows = finish(client, initial(client, confirmations=12))
    assert state["status"] == "handoff" and state["no_progress"] == 2
    assert state["ledger"] is None
    assert "转人工" in state["reason"]
    assert [r["record"]["action"] for r in rows if r["record"]][-2:] == ["hold", "hold"]


def test_budget_prevents_extra_model_calls(client):
    state = {**initial(client), "decisions": 20}
    row = advance(client, state)
    assert row["state"]["status"] == "handoff" and row["decision"] is None


def test_loop_requires_authentication():
    with TestClient(app) as client:
        assert client.post("/api/crypto/loop/tick", json={}).status_code == 401
