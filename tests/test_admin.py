"""ADMIN_TOKEN on the demo write endpoints and the dashboard button (temp database)."""

import pytest
from fastapi.testclient import TestClient

from app import db, main

TOKEN = "s3cret-admin"
GOOD = {"Authorization": f"Bearer {TOKEN}"}
WRITES = [("/reset", None), ("/simulate/dental", {}), ("/ingest/dental", {"name": "Test Caller"})]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "admin.db"))
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
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


def test_agent_webhooks_stay_open(client):
    args = {"name": "save_lead", "args": {"name": "Test Caller"}, "call": {}}
    assert client.post("/retell/dental", json=args).status_code == 200
    assert client.post("/vapi/dental", json={"message": {"type": "status-update"}}).status_code == 200


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
