"""The confirmation re-run in `python -m evals run` (no network: runner is faked)."""

from types import SimpleNamespace

from evals import baseline, cli, metrics
from evals.scenario import Scenario


def res(scenario, attempt, passed):
    return {"agent": "dental", "scenario": scenario, "category": "happy_path", "attempt": attempt,
            "passed": passed, "contained": passed, "transferred": False, "handoff_ok": True,
            "missed_handoff": False, "unnecessary_handoff": False, "task_success": passed,
            "hallucinated": False, "cost_usd": 0.0}


def make_run(results):
    return {"k": 1, "cost_usd": 0.0, "aborted": None, "results": results, "summary": metrics.summarize(results)}


def setup(monkeypatch, retry_passes):
    sc = Scenario(id="s1", agent="dental", title="", category="happy_path", persona={}, goal="", hidden_facts={},
                  friction=[], stop="", max_turns=1, expect={})
    spec_ = SimpleNamespace(id="dental")
    base = {"run_id": "b", "k": 3, "scenarios": {"s1": {"status": "pass", "passes": 3, "runs": 3,
                                                        "contained": 3, "missed_handoffs": 0}}}
    monkeypatch.setattr(baseline, "load", lambda agent, model: base)
    calls = []

    def fake_run_suite(jobs, k, *rest):
        calls.append((jobs, k))
        return make_run([res("s1", i + 1, p) for i, p in enumerate(retry_passes)])

    monkeypatch.setattr(cli.runner, "run_suite", fake_run_suite)
    run = make_run([res("s1", 1, False)])
    args = SimpleNamespace(confirm=len(retry_passes), threshold=0.1, max_cost=1.0, backend="openai-text", workers=1)
    cli._confirm_failures(run, [(spec_, [sc])], "gpt-4o-mini", args)
    return run, calls, base


def test_confirmed_failure_stays_a_regression(monkeypatch):
    run, calls, base = setup(monkeypatch, [False, False])
    assert calls and calls[0][1] == 2
    st = run["summary"]["dental"]["scenarios"]["s1"]
    assert (st["passes"], st["runs"], st["status"]) == (0, 3, "fail")
    assert baseline.compare(base, run["summary"]["dental"])["regressions"]


def test_flake_becomes_a_warning_not_a_regression(monkeypatch):
    run, _, base = setup(monkeypatch, [True, True])
    st = run["summary"]["dental"]["scenarios"]["s1"]
    assert st["status"] == "flaky"
    cmp = baseline.compare(base, run["summary"]["dental"])
    assert not cmp["regressions"] and any("flaky" in w for w in cmp["warnings"])
    assert [r["attempt"] for r in run["results"]] == [1, 2, 3]
