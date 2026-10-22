"""/evals ingest rules, page rendering and the boot snapshot (no network, temp database)."""

import json

import pytest
from fastapi.testclient import TestClient

from app import db, main


def run_doc(run_id="r1", created=1000.0, passed=True, selection=None):
    chk = {"id": "fields", "kind": "code", "passed": passed, "advisory": False, "detail": "x", "turn": 2}
    result = {"agent": "dental", "scenario": "s1", "title": "Scenario one", "category": "happy_path", "attempt": 1,
              "passed": passed, "contained": passed, "transferred": False, "handoff": "none",
              "handoff_expected": "none", "missed_handoff": False, "unnecessary_handoff": False,
              "task_success": passed, "hallucinated": False, "turns": 2, "end_reason": "agent_end", "error": None,
              "checks": [chk], "events": [], "cost_usd": 0.001,
              "transcript": [{"turn": 0, "role": "agent", "text": "Hi", "tool_calls": []},
                             {"turn": 1, "role": "caller", "text": "<script>alert(1)</script>"},
                             {"turn": 1, "role": "agent", "text": "Booked.", "tool_calls": []}]}
    scen = {"s1": {"runs": 1, "passes": int(passed), "contained": int(passed), "missed_handoffs": 0,
                   "category": "happy_path", "status": "pass" if passed else "fail"}}
    summary = {"dental": {"calls": 1, "containment_rate": float(passed), "transfer_rate": 0.0, "correct_transfers": 0,
                          "unnecessary_transfers": 0, "missed_handoffs": 0, "missed_handoff_rate": 0.0,
                          "task_success_rate": float(passed), "hallucination_rate": 0.0, "call_pass_rate": float(passed),
                          "pass_k": float(passed), "flaky": [], "failing": [], "scenarios": scen, "cost_usd": 0.001}}
    return {"id": run_id, "created": created, "git_sha": "abc123", "backend": "openai-text", "agent_model": "gpt-4o-mini",
            "k": 1, "cost_usd": 0.001, "aborted": None, "planned_calls": 1, "patches": [],
            "selection": selection or {}, "summary": summary, "results": [result]}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "evals.db"))
    db.init_evals()
    return TestClient(main.app)


def test_local_ingest_without_token_is_accepted(client):
    r = client.post("/evals/ingest", json=run_doc())
    assert r.status_code == 200 and r.json() == {"ok": True, "run": "r1", "results": 1}


def test_remote_ingest_without_token_configured_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "evals.db"))
    db.init_evals()
    remote = TestClient(main.app, client=("203.0.113.9", 5000))
    assert remote.post("/evals/ingest", json=run_doc()).status_code == 403
    assert db.eval_run_count() == 0


def test_token_is_required_when_configured(client, monkeypatch):
    monkeypatch.setenv("EVALS_INGEST_TOKEN", "s3cret")
    assert client.post("/evals/ingest", json=run_doc()).status_code == 401
    assert client.post("/evals/ingest", json=run_doc(), headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.post("/evals/ingest", json=run_doc(), headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_bad_body_rejected(client):
    assert client.post("/evals/ingest", json={"x": 1}).status_code == 400


def test_reingesting_a_run_replaces_it(client):
    client.post("/evals/ingest", json=run_doc(passed=True))
    client.post("/evals/ingest", json=run_doc(passed=False))
    assert db.eval_run_count() == 1
    assert [r["passed"] for r in db.eval_results("r1")] == [0]


def test_page_renders_cards_grid_and_escapes_transcripts(client):
    client.post("/evals/ingest", json=run_doc())
    page = client.get("/evals")
    assert page.status_code == 200
    assert "Brightside Dental Front Desk" in page.text and 'class="cell p' in page.text
    assert "Containment rate" in page.text                       # definitions are on the page
    rid = db.eval_results("r1")[0]["id"]
    tr = client.get(f"/evals/result/{rid}")
    assert tr.status_code == 200
    assert "<script>alert(1)</script>" not in tr.text and "&lt;script&gt;" in tr.text


def test_failing_turn_is_highlighted(client):
    client.post("/evals/ingest", json=run_doc(passed=False))
    rid = db.eval_results("r1")[0]["id"]
    html = client.get(f"/evals/result/{rid}").text
    import re
    classes = re.search(r'<div class="([^"]*)" id="t2">', html).group(1).split()
    assert {"turn", "agent", "flag", "focus"} <= set(classes)


def test_trend_uses_only_full_runs_on_the_same_model(client):
    client.post("/evals/ingest", json=run_doc("old", 1000.0))
    client.post("/evals/ingest", json=run_doc("smoke", 1500.0, selection={"tag": "smoke"}))
    client.post("/evals/ingest", json=run_doc("new", 2000.0))
    view = main._evals_view(None, None)
    assert view["run"]["id"] == "new"
    assert [p["id"] for p in view["agents"][0]["trend"]] == ["old", "new"]


def test_empty_state(client):
    assert "No eval runs published yet" in client.get("/evals").text


def test_boot_loads_committed_snapshot_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "boot.db"))
    snap = tmp_path / "published.json"
    hist = {k: v for k, v in run_doc("h1", 500.0).items() if k != "results"}
    snap.write_text(json.dumps({"history": [hist], "latest": {"gpt-4o-mini": run_doc("r9", 900.0)}}))
    monkeypatch.setattr(main, "_SNAPSHOT", str(snap))
    main._load_eval_snapshot()
    assert db.eval_run_count() == 2 and len(db.eval_results("r9")) == 1 and db.eval_results("h1") == []
    main._load_eval_snapshot()                                   # not reloaded once data exists
    assert db.eval_run_count() == 2
