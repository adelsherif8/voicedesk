"""ADMIN_TOKEN on the demo write endpoints and the dashboard button (temp database)."""

import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from app import db, main

TOKEN = "s3cret-admin"
RETELL_KEY = "retell-test-key"
GOOD = {"Authorization": f"Bearer {TOKEN}"}
WRITES = [("/reset", None), ("/simulate/dental", {}), ("/ingest/dental", {"name": "Test Caller"})]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "admin.db"))
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("VAPI_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("RETELL_API_KEY", RETELL_KEY)
    db.init()
    return TestClient(main.app)


@pytest.mark.parametrize("path,body", WRITES)
@pytest.mark.parametrize("value", [None, "", "   "])
def test_refused_with_403_when_token_unset_or_blank(client, monkeypatch, path, body, value):
    if value is not None:
        monkeypatch.setenv("ADMIN_TOKEN", value)
    before = db.count()
    for headers in ({}, GOOD, {"Authorization": "Bearer "}):
        assert client.post(path, json=body, headers=headers).status_code == 403
    assert db.count() == before


@pytest.mark.parametrize("path,body", WRITES)
@pytest.mark.parametrize("auth", [None, "Bearer nope", "Bearer ", TOKEN, f"Basic {TOKEN}", "Bearer sécret"])
def test_wrong_token_gets_401_and_changes_nothing(client, monkeypatch, path, body, auth):
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    client.post("/simulate/dental", json={}, headers=GOOD)
    before = db.count()
    headers = {"Authorization": auth.encode()} if auth else {}
    assert client.post(path, json=body, headers=headers).status_code == 401
    assert db.count() == before


def test_right_token_allows_each_write(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    seeded = db.count()
    assert client.post("/simulate/dental", json={}, headers=GOOD).json()["ok"]
    assert client.post("/ingest/dental", json={"name": "Test Caller"}, headers=GOOD).json()["ok"]
    assert db.count() == seeded + 2
    assert client.post("/reset", headers=GOOD).json() == {"ok": True, "records": seeded}


def test_token_is_compared_in_constant_time(client, monkeypatch):
    seen = []
    monkeypatch.setattr(main.hmac, "compare_digest", lambda a, b: seen.append((a, b)) or True)
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    assert client.post("/reset", headers=GOOD).status_code == 200
    assert seen == [(TOKEN.encode(), TOKEN.encode())]


def retell_post(client, path, payload, key=RETELL_KEY, age_ms=0):
    raw = json.dumps(payload).encode()
    ts = str(int(time.time() * 1000) - age_ms)
    digest = hmac.new(key.encode(), raw + ts.encode(), hashlib.sha256).hexdigest()
    return client.post(path, content=raw, headers={"Content-Type": "application/json",
                                                   "X-Retell-Signature": f"v={ts},d={digest}"})


def test_retell_webhook_needs_a_valid_fresh_signature(client):
    args = {"name": "save_lead", "args": {"name": "Test Caller"}, "call": {}}
    before = db.count("dental")
    assert client.post("/retell/dental", json=args).status_code == 401
    assert retell_post(client, "/retell/dental", args, key="wrong").status_code == 401
    assert retell_post(client, "/retell/dental", args, age_ms=6 * 60 * 1000).status_code == 401
    assert db.count("dental") == before
    assert retell_post(client, "/retell/dental", args).status_code == 200
    assert db.count("dental") == before + 1


def test_retell_webhook_refused_without_a_key(client, monkeypatch):
    monkeypatch.delenv("RETELL_API_KEY")
    assert retell_post(client, "/retell/dental", {"name": "x", "args": {}}).status_code == 401


def test_vapi_webhook_needs_the_secret(client, monkeypatch):
    body = {"message": {"type": "status-update"}}
    assert client.post("/vapi/dental", json=body, headers={"X-Vapi-Secret": ""}).status_code == 401
    monkeypatch.setenv("VAPI_WEBHOOK_SECRET", "vapi-secret")
    assert client.post("/vapi/dental", json=body).status_code == 401
    assert client.post("/vapi/dental", json=body, headers={"X-Vapi-Secret": "wrong"}).status_code == 401
    assert client.post("/vapi/dental", json=body, headers={"X-Vapi-Secret": "vapi-secret"}).status_code == 200


@pytest.mark.parametrize("value", [None, TOKEN])
def test_public_page_has_no_simulate_button(client, monkeypatch, value):
    if value:
        monkeypatch.setenv("ADMIN_TOKEN", value)
    r = client.get("/")
    assert r.status_code == 200
    assert "simulate" not in r.text.lower()
    assert TOKEN not in r.text


def test_authorised_page_has_button_without_the_token(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    r = client.get("/", headers=GOOD)
    assert "Simulate a call" in r.text and "async function simulate" in r.text
    assert TOKEN not in r.text
    assert r.headers["cache-control"] == "no-store"


def test_real_callers_are_hidden_from_the_public_but_not_the_admin(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    retell_post(client, "/retell/sales", {"name": "save_lead", "call": {"from_number": "+15125550199"},
                                       "args": {"name": "Jane Roe", "email": "jane@example.com", "notes": "Kitchen sink backed up",
                                                "address": "12 Oak St", "kind": "order", "total": 40}})
    retell_post(client, "/retell/sales", {"event": "call_analyzed",
                                       "call": {"transcript": "my card is 4242", "from_number": "+15125550199",
                                                "call_analysis": {"call_summary": "Jane at 12 Oak St"}}})
    for path in ("/records?agent=sales", "/records"):
        public = client.get(path).text
        for secret in ("Roe", "5550199", "jane@example.com", "4242"):
            assert secret not in public
    row = next(r for r in client.get("/records?agent=sales").json()["records"] if r["name"] == "Jane")
    assert row["meta"]["kind"] == "order" and row["meta"]["total"] == 40
    assert "Jane Roe" in client.get("/records?agent=sales", headers=GOOD).text
    assert "Sarah Johnson" in client.get("/records?agent=receptionist").text    # seed data stays whole
    assert "5550199" not in client.get("/agent/sales").text


def test_saved_calls_come_back_from_retell_after_a_restart(client, monkeypatch):
    from app import web_call
    monkeypatch.setattr(web_call, "agent_ids", lambda: {"recovery": "agent_x"})
    listing = {"items": [{"call_id": "call_1", "tool_calls": [{"name": "log_outcome"}, {"name": "end_call"}]},
                         {"call_id": "call_2", "tool_calls": [{"name": "end_call"}]}]}
    full = {"start_timestamp": 1_700_000_000_000, "transcript_with_tool_calls": [
        {"role": "tool_call_invocation", "name": "log_outcome", "time_sec": 30.4,
         "arguments": '{"name":"Sam Tester","intent":"Sink backed up","outcome":"booked","appointment":"Tomorrow 10am","execution_message":"Bye"}'},
        {"role": "tool_call_invocation", "name": "end_call", "arguments": "{}"}]}
    monkeypatch.setattr(web_call, "retell", lambda path, body=None, timeout=10.0: listing if "list-calls" in path else full)
    before = db.count("recovery")
    assert main.replay_from_retell() == 1
    assert main.replay_from_retell() == 0          # no duplicates on the next boot
    assert db.count("recovery") == before + 1
    row = next(r for r in client.get("/records?agent=recovery").json()["records"] if r["name"] == "Sam")
    assert row["intent"] == "Sink backed up" and row["outcome"] == "booked" and "execution_message" not in row["meta"]
